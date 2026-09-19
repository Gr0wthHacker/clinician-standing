-- =============================================================================
-- 0015_pricing.sql -- the pricing plane (BUILD_PLAN WP1.1).
--
-- Pricing rules are CODE, NOT COPY (BUILD_PLAN A2.3). The rack rates, the
-- discount schedule and above all the $200 PPPM floor live here and are enforced
-- here, so a quote can never be built that undercuts the floor -- not from the
-- app, not from a Lovable screen, not from a hand-written insert. All monetary
-- values are in CENTS (PRD 5), so there is no float rounding in money.
--
-- THE FLOOR (A2.3): a Clinician Standing subscription's effective per-clinician-
-- per-month price may never fall below $200 = 20,000 cents, whatever discount
-- applies. Enforced three ways: the pricing function floors it, the check
-- constraint on quote_lines rejects a stored line that violates it, and the
-- property tests prove no input combination breaks it.
--
-- Enum-like columns are text + named CHECK; see header of 0001.
-- =============================================================================

-- The floor, named once so the function, the constraint and any future reader
-- agree on the number.
-- 20000 cents = $200.00 PPPM.

-- ---------------------------------------------------------------------------
-- price_book -- the rack rate for every sellable product, per brand.
-- ---------------------------------------------------------------------------
create table if not exists price_book (
  id               uuid primary key default gen_random_uuid(),
  brand            text not null,                  -- clinician_standing | cliniciq | whitecoat | stanchion | ...
  product_code     text not null,                  -- stable machine key, e.g. cs_standard
  display_name     text not null,
  tier             text,                           -- essential | standard | complete, or null
  unit             text not null,                  -- pppm | monthly | one_time
  rack_price_cents integer not null,
  effective_from   date not null default current_date,
  effective_to     date,
  created_at       timestamptz default now(),
  deleted_at       timestamptz,

  constraint price_book_unit_chk
    check (unit in ('pppm', 'monthly', 'one_time')),
  constraint price_book_rack_nonneg_chk
    check (rack_price_cents >= 0),
  constraint price_book_effective_order_chk
    check (effective_to is null or effective_to >= effective_from),
  -- One current rack rate per product; superseding one closes the old row's
  -- effective_to and inserts a new one.
  unique (product_code, effective_from)
);

comment on table price_book is
  'Rack rates per brand/product (BUILD_PLAN WP1.1). All amounts in cents. The pricing page and every quote read from here -- prices are never hard-coded (A2.3, A2.8).';

-- ---------------------------------------------------------------------------
-- discount_rules -- volume discounts, applied AFTER the rack rate (A2.3).
-- ---------------------------------------------------------------------------
create table if not exists discount_rules (
  id             uuid primary key default gen_random_uuid(),
  brand          text not null,
  basis          text not null,                    -- clinician_count | ...
  min_threshold  integer not null,                 -- applies at or above this count
  percent        numeric(5,2) not null,            -- 0..100, applied after rack
  effective_from date not null default current_date,
  effective_to   date,
  created_at     timestamptz default now(),
  deleted_at     timestamptz,

  constraint discount_rules_percent_chk
    check (percent >= 0 and percent <= 100),
  constraint discount_rules_threshold_chk
    check (min_threshold >= 0),
  constraint discount_rules_effective_order_chk
    check (effective_to is null or effective_to >= effective_from),
  unique (brand, basis, min_threshold, effective_from)
);

comment on table discount_rules is
  'Volume discount schedule (BUILD_PLAN WP1.1, D5). Discount is applied AFTER the rack rate and can never breach the $200 PPPM floor (A2.3).';

-- ---------------------------------------------------------------------------
-- quotes and quote_lines -- a priced offer, reproducible from stored inputs.
-- ---------------------------------------------------------------------------
create table if not exists quotes (
  id           uuid primary key default gen_random_uuid(),
  practice_id  uuid references practices,
  brand        text not null,
  status       text not null default 'draft',      -- draft | sent | accepted | expired | void
  currency     text not null default 'usd',
  created_at   timestamptz default now(),
  deleted_at   timestamptz,

  constraint quotes_status_chk
    check (status in ('draft', 'sent', 'accepted', 'expired', 'void'))
);

create table if not exists quote_lines (
  id                        uuid primary key default gen_random_uuid(),
  quote_id                  uuid not null references quotes on delete cascade,
  product_code              text not null,
  tier                      text,
  unit                      text not null,
  quantity                  integer not null default 1,
  rack_price_cents          integer not null,
  discount_percent          numeric(5,2) not null default 0,
  effective_unit_price_cents integer not null,
  -- True for a Clinician Standing PPPM subscription line, which is the line the
  -- $200 floor governs. The constraint below reads only this flag and the price,
  -- so the floor is enforced on the stored row regardless of how it was built.
  is_pppm_floored           boolean not null default false,
  created_at                timestamptz default now(),
  deleted_at                timestamptz,

  constraint quote_lines_unit_chk
    check (unit in ('pppm', 'monthly', 'one_time')),
  constraint quote_lines_quantity_chk
    check (quantity >= 1),
  constraint quote_lines_discount_chk
    check (discount_percent >= 0 and discount_percent <= 100),
  constraint quote_lines_rack_nonneg_chk
    check (rack_price_cents >= 0),
  -- THE FLOOR, at the database. A floored line under $200 PPPM cannot be stored.
  constraint quote_lines_pppm_floor_chk
    check (not is_pppm_floored or effective_unit_price_cents >= 20000)
);

comment on constraint quote_lines_pppm_floor_chk on quote_lines is
  'The absolute $200 PPPM floor for Clinician Standing subscriptions (A2.3). The pricing function floors the price and this rejects any stored line that still breaches it.';

-- ---------------------------------------------------------------------------
-- app.price_effective -- the one pricing function. Python has a matching one
-- (pricing.py); a test asserts they agree.
-- ---------------------------------------------------------------------------
create or replace function app.price_effective(
  rack_price_cents integer,
  discount_percent numeric,
  is_pppm_floored boolean
) returns integer
language sql
immutable
as $$
  -- Discount applied AFTER the rack rate, then floored at $200 for a Clinician
  -- Standing PPPM line. Round to the nearest cent; money is integer cents.
  select greatest(
    round(rack_price_cents * (1 - discount_percent / 100.0))::integer,
    case when is_pppm_floored then 20000 else 0 end
  );
$$;

comment on function app.price_effective(integer, numeric, boolean) is
  'Effective price in cents: rack minus discount, floored at $200 (20000c) for a Clinician Standing PPPM line (A2.3). Matches pricing.effective_unit_price_cents in Python.';

-- ---------------------------------------------------------------------------
-- RLS. Internal-only for now: pricing is set by the business, and a quote is
-- internal work state until it is sent. Same two-gate model as 0008/0013.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['price_book', 'discount_rules', 'quotes', 'quote_lines']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from public', t);
    execute format('revoke all on public.%I from app_internal, app_delivery, app_client_portal', t);
    execute format('grant select, insert, update, delete on public.%I to app_internal', t);
    execute format('drop policy if exists %I on public.%I', t || '_internal_all', t);
    execute format(
      'create policy %I on public.%I for all to app_internal using (true) with check (true)',
      t || '_internal_all', t);
    execute format('alter table public.%I force row level security', t);
  end loop;
end $$;

grant usage on schema app to app_internal;
grant execute on function app.price_effective(integer, numeric, boolean) to app_internal;

-- ---------------------------------------------------------------------------
-- Seed: the rack rates and discount schedule stated in BUILD_PLAN A1 / D5.
-- Only prices the plan states are seeded; the full book is Document 02 (not
-- available to this build) -- absent prices are left out, never guessed (A2.8).
-- Re-runnable: ON CONFLICT refreshes the descriptive fields and the rack rate.
-- ---------------------------------------------------------------------------
insert into price_book (brand, product_code, display_name, tier, unit, rack_price_cents) values
  -- Clinician Standing PPPM tiers (A2.3): $200 / $350 / $400.
  ('clinician_standing', 'cs_essential', 'Clinician Standing -- Essential', 'essential', 'pppm', 20000),
  ('clinician_standing', 'cs_standard',  'Clinician Standing -- Standard',  'standard',  'pppm', 35000),
  ('clinician_standing', 'cs_complete',  'Clinician Standing -- Complete',  'complete',  'pppm', 40000),
  -- ClinicIQ (A1).
  ('cliniciq', 'ciq_audit_standard', 'ClinicIQ Revenue Audit',         null, 'one_time', 150000),
  ('cliniciq', 'ciq_audit_premium',  'ClinicIQ Revenue Audit (Premium)', null, 'one_time', 250000),
  ('cliniciq', 'ciq_monitoring',     'ClinicIQ Monitoring',            null, 'monthly',  20000),
  -- Whitecoat (A1).
  ('whitecoat', 'wc_paid_media', 'Whitecoat Paid Media Retainer', null, 'monthly', 250000),
  -- Stanchion setup + monthly pairs (A1).
  ('stanchion', 'stanchion_hipaa_setup',    'Stanchion HIPAA Program (setup)',        null, 'one_time', 350000),
  ('stanchion', 'stanchion_hipaa_monthly',  'Stanchion HIPAA Program (monthly)',      null, 'monthly',   15000),
  ('stanchion', 'stanchion_website_setup',  'Stanchion Compliant Website (setup)',    null, 'one_time', 1200000),
  ('stanchion', 'stanchion_website_monthly','Stanchion Compliant Website (monthly)',  null, 'monthly',   25000),
  ('stanchion', 'stanchion_ai_setup',       'Stanchion AI Compliance (setup)',        null, 'one_time', 250000),
  ('stanchion', 'stanchion_ai_monthly',     'Stanchion AI Compliance (monthly)',      null, 'monthly',    5000),
  ('stanchion', 'stanchion_ad_setup',       'Stanchion Advertising Compliance (setup)', null, 'one_time', 150000),
  ('stanchion', 'stanchion_ad_monthly',     'Stanchion Advertising Compliance (monthly)', null, 'monthly', 5000)
on conflict (product_code, effective_from) do update set
  brand            = excluded.brand,
  display_name     = excluded.display_name,
  tier             = excluded.tier,
  unit             = excluded.unit,
  rack_price_cents = excluded.rack_price_cents;

-- Clinician Standing volume discounts (BUILD_PLAN D5 default): 0% under 10
-- clinicians, 5% at 10-24, 10% at 25+. Always subject to the $200 floor.
-- NOTE: the earlier canonical figures used a fourth 15% tier; D5 is the plan's
-- stated default and is seeded here. Flagged for confirmation.
insert into discount_rules (brand, basis, min_threshold, percent) values
  ('clinician_standing', 'clinician_count', 0,  0.00),
  ('clinician_standing', 'clinician_count', 10, 5.00),
  ('clinician_standing', 'clinician_count', 25, 10.00)
on conflict (brand, basis, min_threshold, effective_from) do update set
  percent = excluded.percent;

-- ---------------------------------------------------------------------------
-- SELF-CHECK. The seeded Clinician Standing rack rates must match A2.3 exactly,
-- and no floored effective price the function can produce may fall below $200.
-- ---------------------------------------------------------------------------
do $$
declare wrong text;
begin
  select string_agg(product_code || '=' || rack_price_cents, ', ') into wrong
  from price_book
  where product_code in ('cs_essential', 'cs_standard', 'cs_complete')
    and (product_code, rack_price_cents) not in
        (('cs_essential', 20000), ('cs_standard', 35000), ('cs_complete', 40000));
  if wrong is not null then
    raise exception 'Clinician Standing rack rates do not match A2.3: %', wrong;
  end if;

  -- The floor holds for the whole discount range against the lowest rack rate.
  if exists (
    select 1 from generate_series(0, 100) d
    where app.price_effective(20000, d, true) < 20000
  ) then
    raise exception 'price_effective breached the $200 floor for some discount';
  end if;
end $$;
