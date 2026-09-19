-- =============================================================================
-- 0017_requirement_review_status.sql -- a review gate on rules-plane rows.
--
-- BUILD_PLAN WP0.6 authors clock-anchor rows (renewal_anchor, csr_anchor,
-- ce_anchor) from primary sources, and every such row must carry
-- review_status = 'needs_human_review' until a human confirms the reading of
-- the statute. This adds the column so that flag has somewhere to live, and so
-- the rules-admin screen can surface what still needs review.
--
-- Existing rows default to 'accepted': they were seeded deliberately before this
-- gate existed. New anchor rows set 'needs_human_review' explicitly. Enum-like
-- column is text + named CHECK; see header of 0001.
-- =============================================================================

alter table requirements
  add column if not exists review_status text not null default 'accepted';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'requirements_review_status_chk'
  ) then
    alter table requirements
      add constraint requirements_review_status_chk
      check (review_status in ('accepted', 'needs_human_review', 'rejected'));
  end if;
end $$;

comment on column requirements.review_status is
  'accepted (confirmed) | needs_human_review (authored from a source, awaiting a human) | rejected. Clock-anchor rows (WP0.6) land as needs_human_review; the auto-clear path should treat a needs_human_review rule as not yet current when it matters (see the rules-admin screen, PRD 10).';
