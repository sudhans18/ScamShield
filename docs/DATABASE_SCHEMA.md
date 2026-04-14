# ScamShield — Database Schema

Last updated: 2026-04-15

The backend uses Supabase (PostgreSQL + pgvector) as its primary persistence layer.

**Run `backend/sql/intelligence_layer_tables.sql` to create all tables before starting the backend.**

---

## Intelligence Layer Tables (New — 4-Layer Pipeline)

### `job_postings_legitimate`

Seed corpus for Layer 1 embedding cluster (legitimate job postings).

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid PK | Auto-generated |
| `text` | text | Job posting text |
| `embedding` | vector(768) | LaBSE embedding (populated by `scripts/compute_centroids.py`) |
| `source` | text | Default: `'mock'` |
| `created_at` | timestamptz | Auto |

Written by: `scripts/seed_mock_data.py`, `scripts/compute_centroids.py`

---

### `job_postings_scam`

Seed corpus for Layer 1 embedding cluster (known scam postings).

Same schema as `job_postings_legitimate`.

Written by: `scripts/seed_mock_data.py`, `scripts/compute_centroids.py`

---

### `cluster_centroids`

Stores the mean LaBSE embeddings for the `legitimate` and `scam` clusters.

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid PK | Auto-generated |
| `cluster_name` | text UNIQUE | `'legitimate'` or `'scam'` |
| `centroid` | vector(768) | Mean embedding, L2-normalized |
| `sample_count` | integer | Number of samples used |
| `updated_at` | timestamptz | Auto |

Written by: `scripts/compute_centroids.py`  
Read by: `backend/app/services/intelligence/embedding_scorer.py` (Layer 1)

---

### `company_registry`

Mock eMigrate-registered agency registry. Used by Layer 2 for cross-reference checks.

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid PK | Auto-generated |
| `name` | text | Full company name |
| `name_normalized` | text UNIQUE | Lowercase, stripped (for fuzzy match) |
| `registered_city` | text | City of registration |
| `registered_state` | text | State of registration |
| `country` | text | Default: `'India'` |
| `emigrate_registered` | boolean | Whether eMigrate-registered |
| `emigrate_raps_id` | text | eMigrate RAPS number (e.g. `R1234567`) |
| `placement_countries` | text[] | Countries company can place workers in |
| `allowed_job_categories` | text[] | Permitted job roles |
| `primary_phone` | text | Office contact |
| `website` | text | Company website |
| `is_blacklisted` | boolean | Flagged by authorities |
| `created_at` | timestamptz | Auto |

Index: `idx_company_registry_name` on `name_normalized`.

Written by: `scripts/seed_mock_data.py`  
Read by: `backend/app/services/graph/db_cross_checker.py` (Layer 2)

**Checks performed against this table:**
1. Company name fuzzy-match (Levenshtein ≤ 2 = found)
2. Blacklist flag (`is_blacklisted=true` → +2 contradictions)
3. Typosquatting detection (distance 1–3 from any registry entry)
4. Location consistency (`registered_city`/`registered_state` vs claimed location)
5. Role consistency (`allowed_job_categories` vs claimed role)
6. Gulf placement eligibility (`placement_countries` vs claimed work country)

---

### `phone_prefix_location`

Maps phone number prefixes to countries/regions. Used by Layer 2 to detect phone-vs-location mismatches.

| Column | Type | Description |
|--------|------|-------------|
| `prefix` | text PK | E.g. `'+971-4'`, `'+91-98'` |
| `country` | text | Country name |
| `region` | text | Region/city |
| `is_mobile` | boolean | Whether mobile or landline |

Written by: `scripts/seed_mock_data.py`  
Read by: `backend/app/services/graph/db_cross_checker.py` (Layer 2)

---

### `message_fingerprints`

Tracks SHA-256 hashes of normalized message text for propagation behavior analysis (Layer 3).

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid PK | Auto-generated |
| `message_hash` | text UNIQUE | SHA-256 of normalized (lowercased, whitespace-collapsed) text |
| `first_seen_at` | timestamptz | When first received |
| `last_seen_at` | timestamptz | Most recent occurrence |
| `seen_count` | integer | Number of times seen |
| `forwarded_flag` | boolean | `true` if Twilio `ForwardedManyTimes` ever seen |
| `source_channels` | text[] | Channels seen on: `whatsapp`, `dashboard`, `extension` |

Index: `idx_fingerprints_hash` on `message_hash`.

Written + read by: `backend/app/services/propagation/propagation_analyzer.py` (Layer 3)

**Propagation score formula:**

| Signal | Score Added |
|--------|------------|
| `forwarded_flag = true` | +0.30 |
| `seen_count ≥ 3` | +0.20 |
| `seen_count ≥ 10` | +0.20 (additional) |
| Seen on 2+ channels | +0.15 |
| Message length < 180 chars | +0.15 |

Score clamped to `[0.0, 1.0]`. `is_broadcast = score ≥ 0.5`.

---

## Operational Tables (Pre-existing)

### `scam_reports`

Stores high-risk analysis results (auto-inserted when `risk_score > 0.6`).

| Column | Type | Description |
|--------|------|-------------|
| `id` | uuid PK | Auto-generated |
| `scam_phone` | text | Extracted phone number |
| `company_name` | text | Extracted company |
| `job_role` | text | Extracted role |
| `salary` | int | Extracted salary (INR) |
| `fee` | int | Extracted fee amount (INR) |
| `location` | text | Extracted location |
| `risk_score` | int | 0–100 (normalised from 0.0–1.0) |
| `report_time` | timestamptz | When stored |
| `source` | text | `whatsapp`, `dashboard`, or `extension` |

Written by: `backend/app/services/scam_report_store.py`  
Read by: `backend/app/services/dashboard_service.py`

---

### `scam_network_edges`

Graph edges between co-occurring entities (phones, UPI IDs, agents) across reports. Used for syndicate detection.

| Column | Type | Description |
|--------|------|-------------|
| `entity_a` | text | Normalized key, e.g. `phone:9876543210` |
| `entity_b` | text | Normalized key |
| `entity_a_type` | text | `phone`, `upi`, or `agent` |
| `entity_b_type` | text | Same |
| `weight` | int | Co-occurrence count |
| `last_seen` | timestamptz | Most recent co-occurrence |

Written by: `backend/app/services/scam_report_store.py` (`store_report_edges`)  
Read by: `backend/app/services/dashboard_service.py` (network graph)  
Read by: `backend/app/services/graph/syndicate_detector.py`

> Edge writes are best-effort — failures are swallowed to avoid blocking analysis.

---

### `phone_reputation`

Aggregated reputation score per phone number.

| Column | Type | Description |
|--------|------|-------------|
| `phone_number` | text UNIQUE | Phone number |
| `report_count` | int | Number of reports |
| `trust_score` | float | Computed trust score (lower = more suspicious) |
| `last_reported` | timestamptz | Most recent report time |

Written by: `backend/app/services/reputation/phone_reputation.py` (upserted on every `scam_reports` insert)
