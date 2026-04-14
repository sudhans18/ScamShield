# ScamShield — Project Status

Last updated: 2026-04-15

---

## What Changed: Intelligence Architecture Overhaul

The entire intelligence layer was replaced in April 2026. The old dual-process architecture (`backend` + `ai-services`) has been consolidated into a single backend process running a 4-layer AI pipeline.

### Before → After

| | Before | After |
|-|--------|-------|
| **Processes** | 2 (backend:8000 + ai-services:8001) | 1 (backend:8000 only) |
| **Intelligence** | Rule-based (`scam_rules.py`) + optional Groq LLM | 4-layer pipeline (Embedding + Graph + Propagation + LLM) |
| **OCR/Audio/Doc** | `ai-services/` microservice | `backend/app/services/media/` (in-process) |
| **Entity extraction** | Two separate extractors (backend + ai-services) | Single upgraded `entity_extractor.py` |
| **Company checks** | MCA API stubs (never worked) | Supabase mock eMigrate registry (seeded, works) |
| **Propagation** | Not implemented | SHA-256 fingerprinting + Supabase `message_fingerprints` |
| **LLM role** | Feature-matcher fallback | Chain-of-thought investigator with full evidence bundle |

### Old files deleted
- `ai-services/` — entire directory removed
- `backend/app/services/intelligence/scam_rules.py`
- `backend/app/services/intelligence/risk_scorer.py`
- `backend/app/services/intelligence/analyzer.py`
- `backend/app/services/intelligence/llm_classifier.py`

---

## Component Completion Status

### 1. WhatsApp Bot — **~85%**

✅ Implemented:
- Twilio webhook (`POST /whatsapp`) with signature validation + ngrok-aware URL reconstruction
- Full bilingual responses (Hindi + English), auto-language detection (Devanagari + Romanized Hindi tokens)
- Media forwarding: image, audio, document all wired through pipeline
- `ForwardedManyTimes` Twilio flag passed to Layer 3 propagation scorer
- Redis queue: bot enqueues, `message_worker.py` dequeues + replies
- "Please wait..." immediate ack before analysis begins

🔲 Remaining:
- Structured conversation flows (WhatsApp buttons / quick-reply templates)
- Opt-in onboarding UX for new users
- Multi-language beyond Hindi/English

---

### 2. SMS / IVR Gateway — **~40%**

✅ Implemented:
- `POST /sms` endpoint in `whatsapp-bot/bot.py` — returns short risk summary

🔲 Remaining:
- IVR/call flow not implemented
- Outbound shortcode "CHECK <number>" workflow

---

### 3. Browser Extension — **~30%**

✅ Implemented:
- Content script sends page text to `POST /api/analyze`
- Popup shows risk verdict

🔲 Remaining:
- Per-post DOM badges (Facebook/OLX/Indeed selectors)
- URL/domain intelligence
- Non-blocking UX (currently uses `alert()`)

---

### 4. Scam NLP Classifier — **~90%** *(was ~70%)*

✅ Implemented (new):
- **Layer 1 — Semantic Embedding (LaBSE):** `embedding_scorer.py` — measures geometric distance from scam/legitimate centroids in 768-dim vector space
- **Layer 2 — Cross-Reference Consistency Graph:** `db_cross_checker.py` — 7 checks against mock eMigrate registry (fuzzy match, blacklist, typosquatting, location, role, Gulf placement, phone prefix)
- **Layer 3 — Propagation Analysis:** `propagation_analyzer.py` — SHA-256 fingerprinting, seen count tracking, Twilio forwarded flag scoring
- **Layer 4 — LLM Chain-of-Thought Investigator:** `llm_investigator.py` — 5-step investigative prompt with full structured evidence bundle; Groq LLaMA-3.3-70B
- Entity extractor upgraded: UPI IDs, urgency flags, `has_fee`, `has_urgency`

🔲 Remaining:
- Formal evaluation harness (benchmark on 30+ real scam messages)
- IndicTrans2 translation layer for regional Indian languages

---

### 5. Document Forgery Detector — **~75%** *(was ~70%)*

✅ Implemented:
- `backend/app/services/media/doc_pipeline.py` — PDF/DOCX extraction, forgery scoring, typosquatting detection against known company names
- MCA stubs fully removed — replaced by Layer 2 DB registry lookup
- Forgery reasons and typosquatting results passed as `media_context` to Layer 4 LLM

🔲 Remaining:
- Broader document type coverage (image-scanned PDFs at low resolution)
- Production Tesseract/Poppler verification on non-Windows

---

### 6. Voice Note Analyser — **~70%**

✅ Implemented:
- `backend/app/services/media/audio_pipeline.py` + `whisper_transcriber.py` (lazy-loaded)
- Whisper model loaded on first use, not at startup (avoids slow boot)

🔲 Remaining:
- Audio model size selection (currently defaults to `base`)
- Tone/urgency prosody features

---

### 7. Intelligence Dashboard — **~75%**

✅ Implemented:
- Stats, recent reports, heatmap, trends, D3 network graph
- Phone lookup page
- All APIs backed by Supabase

🔲 Remaining:
- FIR/PDF export
- Real-time feed (currently polling)
- District risk index
- Admin moderation workflow

---

### 8. QR Trust Verification — **~0%**

🔲 Not started.
- QR signing (HMAC/private key), issuance for verified agencies, verify endpoint + UI

---

### 9. Field Worker PWA — **~0%**

🔲 Not started.
- Offline-first PWA, bulk verification, case management

---

## Infrastructure Status

| Item | Status |
|------|--------|
| Single-process backend | ✅ Done — no ai-services process |
| pgvector extension | ✅ Enabled in Supabase |
| Intelligence layer tables | ✅ In `backend/sql/intelligence_layer_tables.sql` |
| Seed mock data script | ✅ `scripts/seed_mock_data.py` — ~50 companies, ~45 prefixes |
| Centroid builder script | ✅ `scripts/compute_centroids.py` |
| Redis queue for async analysis | ✅ `message_worker.py` consumes jobs |
| Twilio 403 fix (ngrok) | ✅ URL reconstructed from forwarded headers |
| WhatsApp bot env credentials | ✅ Aligned to root `.env` |
| Syndicate detector | ✅ Runs fire-and-forget after each analysis |
| Graph service | ✅ Stores entity co-occurrence edges |

---

## Known Limitations

- **LaBSE centroids must be pre-seeded.** If `cluster_centroids` table is empty, Layer 1 returns `embedding_score: 0.5` (neutral) until `compute_centroids.py` has been run.
- **Company registry is mock data.** Real eMigrate API integration is out of scope (API is not publicly accessible). The 50-row seed covers demo scenarios well.
- **Groq API key required.** The system degrades gracefully if Groq fails (returns `SUSPICIOUS` at 0.52 with error logged), but Layer 4 is the verdict authority — without it the pipeline is significantly weaker.
- **Whisper + LaBSE are large models.** First startup after fresh install will download ~500 MB (LaBSE) + Whisper model. Subsequent starts use disk cache.
