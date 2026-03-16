# NaukariSaathi (ScamShield) - Database Notes (Supabase)

Last updated: 2026-03-16

The backend uses Supabase as its primary persistence layer.

This doc is based on how the code reads/writes tables. It is not a formal migration.

## Tables Used By Backend

### `scam_reports`

Written by:
- `backend/app/services/scam_report_store.py` (`create_scam_report`, `store_analysis_report`)

Read by:
- `backend/app/services/dashboard_service.py`
- `backend/app/services/reputation/phone_reputation.py`

Observed fields (from selects/inserts):
- `id` (uuid, returned by Supabase)
- `reporter_hash` (text, optional)
- `scam_phone` (text, optional)
- `upi_id` (text, optional)
- `company_name` (text, optional)
- `job_role` (text, optional)
- `salary` (int, optional)
- `fee` (int, optional)
- `location` (text, optional)
- `risk_score` (int, 0-100)
- `trust_weight` (float, default varies)
- `report_time` (timestamp / ISO string)
- `source` (text, optional; backend tries to include this, with fallback if column missing)

Notes:
- Backend normalizes `risk_score` to an integer 0-100 for DB inserts.
- High-risk analyses (`risk_score > 0.6` float upstream) are inserted automatically.

### `scam_network_edges`

Written by:
- `backend/app/services/scam_report_store.py` (`store_report_edges`)

Read by:
- `backend/app/services/dashboard_service.py` (`get_network_graph`, best-effort)

Observed fields (from inserts / selects):
- `entity_a` (text, a normalized key like `phone:987...`)
- `entity_b` (text)
- `entity_a_type` (text: `phone` | `upi` | `agent`)
- `entity_b_type` (text)
- `weight` (int)
- `last_seen` (timestamp / ISO string)

Notes:
- Edge persistence is best-effort: failures are swallowed to avoid blocking analysis responses.
- The dashboard network graph will fall back to building a graph directly from `scam_reports` if this table is missing.

### `phone_reputation`

Written by:
- `backend/app/services/reputation/phone_reputation.py` (`upsert_phone_reputation`)

Observed fields (from upsert payload):
- `phone_number` (text, unique key)
- `report_count` (int)
- `trust_score` (float)
- `last_reported` (timestamp / ISO string)

## Tables Referenced In AI Service (Not Clearly Wired End-to-End Yet)

The AI service’s `validator.py` references Supabase REST endpoints and includes:
- trust-weight logic
- temporal decay
- rate limiting (in-memory)

It references `SUPABASE_URL` and `SUPABASE_ANON_KEY` environment variables, and it appears designed to query or insert into `scam_reports`.

