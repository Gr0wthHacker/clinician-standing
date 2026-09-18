-- =============================================================================
-- 0012_enrollment_status_view.sql -- derive enrollment status at read time.
--
-- WHAT THIS FIXES
-- -----------------------------------------------------------------------------
-- connectors/cms_revalidation.py computed enrollments.status with
--
--     case when individual_due_date < current_date then 'revalidation_due'
--          else 'approved' end
--
-- at LOAD time and stored the answer. current_date moves; a stored answer does
-- not. The revalidation file is monthly, and a row only reaches the change set
-- when CMS changes something in it. A clinician whose due date passes during a
-- month in which CMS changed nothing about their row therefore keeps
-- status = 'approved' while being past due, and keeps it until CMS happens to
-- touch the row again. PRD section 7 calls a past-due Medicare revalidation on
-- a billing clinician critical severity, so the one row that most needs to be
-- right is the one that silently rots.
--
-- The rule: a fact derived from a date and "today" is computed when it is read,
-- never stored. enrollments.revalidation_due is the fact CMS publishes and is
-- what the connector now writes. Everything downstream reads status from here.
--
-- WHY A VIEW AND NOT A GENERATED COLUMN
-- -----------------------------------------------------------------------------
-- A stored generated column must be IMMUTABLE. current_date is STABLE, not
-- IMMUTABLE -- its value depends on the transaction -- so Postgres rejects it
-- in a generated column, and rightly: a stored column would have exactly the
-- staleness problem this migration exists to remove. A view is the mechanism
-- that fits, and it costs nothing: the expression is evaluated per row at read
-- time against an already-indexed column.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. STOP THE BASE COLUMN CARRYING A DERIVED VALUE
--
-- Rows written by earlier runs hold a status that was derived from a date, and
-- the connector no longer maintains it. Reset those to 'approved' -- the fact a
-- live reassignment in the CMS file actually asserts -- and let the view derive
-- the rest from revalidation_due. Scoped to payer = 'medicare' because that is
-- the only payer the revalidation connector writes; a manually entered
-- enrollment for another payer is nobody's derived value and is left alone.
--
-- Nothing is lost: revalidation_due is the input the old status was computed
-- from, and it is still there.
-- ---------------------------------------------------------------------------
update enrollments
   set status = 'approved'
 where payer = 'medicare'
   and status = 'revalidation_due';

comment on column enrollments.status is
  'Enrollment decision as asserted by the source, NOT a date comparison. Anything derived from revalidation_due and today is computed at read time -- query the enrollments_current view, not this column (0012).';

-- ---------------------------------------------------------------------------
-- 2. THE VIEW
--
-- security_invoker = true (PG15+) makes the view run with the privileges and
-- the RLS context of the caller, not of the view owner. Without it the view
-- would be a hole straight through the row-level security in 0008: any role
-- granted SELECT on it would see every enrollment in the database. With it, the
-- enrollments policies apply exactly as they do to the base table.
--
-- status_current is the column to read. It is the source's own decision where
-- the source made one, and the date comparison where it did not:
--
--   rejected / terminated  -- a decision CMS or the payer made. A due date does
--                             not override it, and the clinician is not
--                             "revalidation due", they are out.
--   pending                -- likewise a real state; the enrolment is not yet
--                             live, so a due date is not yet meaningful.
--   otherwise              -- 'revalidation_due' when the published due date is
--                             in the past, else 'approved'. This covers both
--                             rows the connector writes today and any legacy
--                             row still carrying the old derived value.
-- ---------------------------------------------------------------------------
drop view if exists enrollments_current;

create view enrollments_current
  with (security_invoker = true)
as
select
  e.*,
  case
    when e.status in ('rejected', 'terminated', 'pending') then e.status
    when e.revalidation_due is not null and e.revalidation_due < current_date
      then 'revalidation_due'
    else 'approved'
  end                                                        as status_current,
  (e.revalidation_due is not null and e.revalidation_due < current_date)
                                                             as revalidation_overdue,
  case
    when e.revalidation_due is not null and e.revalidation_due < current_date
      then (current_date - e.revalidation_due)
  end                                                        as days_overdue
from enrollments e;

comment on view enrollments_current is
  'enrollments with status evaluated as of today (0012). Read status_current, not enrollments.status: the stored column is what the source asserted, this one folds in the revalidation_due date comparison that must never be frozen at write time. security_invoker, so the RLS policies on enrollments apply unchanged.';

-- ---------------------------------------------------------------------------
-- 3. GRANTS
--
-- Mirror the base table exactly (0008): internal everything, delivery and the
-- client portal read-only. security_invoker means the policies still decide
-- which rows each of them actually gets, so this is a privilege decision only.
-- ---------------------------------------------------------------------------
revoke all on enrollments_current from public;
grant select on enrollments_current to app_internal, app_delivery, app_client_portal;

-- ---------------------------------------------------------------------------
-- 4. SELF-CHECK -- security_invoker really is on.
--
-- If this view were ever recreated without it, every role with SELECT would
-- read every practice's enrollments. Fail the migration instead.
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (
    select 1 from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'enrollments_current'
      and c.reloptions @> array['security_invoker=true']
  ) then
    raise exception
      'enrollments_current must be created with security_invoker = true, or it bypasses the RLS policies on enrollments';
  end if;
end $$;
