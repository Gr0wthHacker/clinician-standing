-- =============================================================================
-- 60_clock_anchors.sql -- controlled-substance-registration clocks that do not
-- track the professional licence (BUILD_PLAN WP0.6).
--
-- The engine anchors a duty to the credential's own date by default (0004 rules
-- plane + engine.resolve_anchor). A csr_anchor row overrides that where a state
-- runs its controlled-substance registration on a fixed calendar of its own.
-- Researched from primary sources, September 2026; each row cites the source and
-- lands as review_status = 'needs_human_review' for a human to confirm.
--
--   CONNECTICUT -- CSR expires biennially on 28 February of ODD years.
--     Source: CT DCP, "When does it expire" (controlled substance practitioner).
--     Anchor: fixed 02-28, parity odd.
--
--   DELAWARE -- CSR expires biennially on 30 June of ODD years.
--     Source: DE Division of Professional Regulation, Controlled Substances FAQ.
--     Anchor: fixed 06-30, parity odd.
--
--   RHODE ISLAND -- NO anchor row. The brief guessed RI runs an offset clock;
--     the RI DOH says the CSR "is renewed at the same time as the professional
--     license", i.e. it TRACKS the licence, which is the engine's default. A
--     csr_anchor would be wrong here, so none is written. (Documented so the
--     next author does not re-add one.)
--
-- Idempotent: ON CONFLICT refreshes the value and the citation.
-- =============================================================================

insert into requirements (
  state, license_type, field_key,
  value_text, value_num, value_bool, value_json,
  citation, citation_url, verified_at, verified_by, version, is_current, review_status
)
select
  src.state, lt.license_type, v.field_key,
  null, null, v.value_bool, v.value_json,
  src.citation, src.citation_url, now(), 'wp0.6-clock-anchors', 1, true, 'needs_human_review'
from (values
  ('CT',
   'CT DCP: controlled-substance practitioner registration expires biennially on 28 February of odd years',
   'https://portal.ct.gov/dcp/knowledge-base/articles/drug-control/licenses/csp-faqs/when-does-it-expire',
   '{"basis":"fixed","month_day":"02-28","parity":"odd"}'::jsonb),
  ('DE',
   'DE Division of Professional Regulation: controlled-substance registrations expire on 30 June of odd years',
   'https://dpr.delaware.gov/boards/controlledsubstances/faqs/',
   '{"basis":"fixed","month_day":"06-30","parity":"odd"}'::jsonb)
) as src(state, citation, citation_url, anchor_json)
cross join (values ('MD'), ('DO'), ('APRN'), ('PA')) as lt(license_type)
cross join lateral (values
  ('csr_required', true, null::jsonb),
  ('csr_anchor', null::boolean, src.anchor_json)
) as v(field_key, value_bool, value_json)
on conflict (state, license_type, field_key, version) do update set
  value_bool     = excluded.value_bool,
  value_json     = excluded.value_json,
  citation       = excluded.citation,
  citation_url   = excluded.citation_url,
  verified_at    = excluded.verified_at,
  verified_by    = excluded.verified_by,
  is_current     = excluded.is_current,
  review_status  = excluded.review_status;
