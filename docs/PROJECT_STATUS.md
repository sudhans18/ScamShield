# NaukariSaathi (ScamShield) - Project Status Report

Assessment date: 2026-03-16

This report is based on:
- Project spec: `docs/NaukariSaathi_Full_Report.pdf` (Hackathon Project Report 2025-26)
- Codebase snapshot under `C:\Projects\ScamShield`

## Executive Summary

You have a working end-to-end core of the platform:
- A FastAPI backend exposing analysis + dashboard APIs (and persisting high-risk cases to Supabase).
- A separate FastAPI AI service handling text/image/audio/document analysis (OCR + Whisper + LLM classification + entity extraction).
- A Twilio WhatsApp webhook service that forwards text/media to the backend and replies in Hindi.
- A React dashboard that visualizes Supabase-backed stats, recent reports, heatmap, trends, and a D3 network graph.

The major remaining work (to fully match the PDF) is around:
- Browser extension “auto-badge” UX and channel-specific DOM integrations (Facebook/OLX/Indeed/etc).
- Proactive pattern detection + district broadcast alerts.
- QR Trust Verification System (signed QR issuance + verification endpoints + UI workflow).
- Field Worker PWA (offline-first case management and bulk verification).
- Hardening/security/config (secrets in env, CORS tightening, rate limiting parity, caching).

## Completion By Spec Component (PDF “Nine Functional Components”)

Percentages are pragmatic: “is there an end-to-end demo that matches the spec intent?”.

1. WhatsApp Bot (Twilio webhook, Hindi response): **~80%**
   - Implemented: `whatsapp-bot/bot.py` webhook (`POST /whatsapp`), Twilio signature validation, async background analysis, Hindi response formatting, supports media (image/audio/document) and text.
   - Gaps: multi-language responses beyond Hindi; richer “verified agency” messaging; opt-in onboarding UX; structured conversation flows (buttons/quick replies).

2. SMS / IVR Gateway: **~40%**
   - Implemented: `whatsapp-bot/bot.py` includes `POST /sms` webhook that returns a short risk summary.
   - Gaps: IVR/call flow not implemented; “CHECK <number>” shortcode workflow not productized; sender verification and throttling aligned to spec.

3. Browser Extension: **~30%**
   - Implemented: `browser-extension/content.js` + `popup.js` send page text to backend `/api/analyze`; alerts on high risk.
   - Important: `browser-extension/background.js` is currently JSON (not JavaScript). With manifest v3 this will break the service worker load. Either delete the background worker reference or replace it with valid JS.
   - Gaps: real-time page badges (“verified / risky”) and post-level highlighting; channel-specific selectors for Facebook/OLX/Indeed; URL/domain intelligence pipeline; performance (avoid sending entire page text); configurable backend URL; safe UX (no blocking alerts).

4. Scam NLP Classifier (multilingual): **~70%**
   - Implemented:
     - AI service classifier + entity extraction pipeline (`ai-services/main_service.py`, `ai-services/models/scam_classifier.py`, `ai-services/entity_extractor.py`).
     - Backend fallback rules + optional Groq LLM classifier for ambiguous cases (`backend/app/services/intelligence/*`).
   - Gaps: explicit evaluation harness / “30 test scam messages” benchmark; robust language normalization/translation layer (PDF references IndicTrans2).

5. Document Forgery Detector: **~70%**
   - Implemented: `ai-services/doc_pipeline.py` + backend `POST /api/analyze/document` + WhatsApp bot media forwarding.
   - Gaps: stable MCA/eMigrate integrations in production; clearer “forgery reasons” surfaced consistently; stronger doc-type coverage; production dependencies (Poppler/Tesseract) verification.

6. Voice Note Analyser (Whisper): **~70%**
   - Implemented: `ai-services/audio_pipeline.py` (Whisper), backend `POST /api/analyze/audio`, WhatsApp bot forwards audio/video.
   - Gaps: reliability/perf (model size selection, caching strategy, hardware considerations), more “tone/urgency” features as spec suggests.

7. Intelligence Dashboard: **~75%**
   - Implemented:
     - UI: `dashboard/src/pages/Dashboard.jsx` + components (heatmap, trends, network graph, reports table).
     - APIs: `backend/app/routes/scam_routes.py` and `backend/app/services/dashboard_service.py`.
     - Phone lookup page: `dashboard/src/pages/PhoneLookup.jsx`.
   - Gaps: “FIR export” (PDF mentions PDF/API export); “district risk index”; real-time feed; admin moderation/appeal workflow; verified agency registry UI.

8. QR Trust Verification System: **~0-10%**
   - Implemented: only incidental QR masking to improve OCR (not trust system).
   - Missing: QR signing (HMAC/private key), issuance for verified agencies, verify endpoint + verification UI, badge display across bot/extension.

9. Field Worker PWA: **~0%**
   - Missing: offline-first PWA for NGOs, bulk verification workflows, case management, district alert feed.

## What’s Implemented Today (Concrete Inventory)

### Backend (FastAPI) - `backend/app`
- Entrypoint: `backend/app/main.py`
- Routers:
  - `backend/app/routes/analyze.py`
  - `backend/app/routes/scam_routes.py`
- Key endpoints (high level):
  - `POST /api/analyze` (text)
  - `POST /api/analyze/image` (multipart upload)
  - `POST /api/analyze/audio` (multipart upload)
  - `POST /api/analyze/document` (multipart upload)
  - `POST /api/reports` (manual report insert)
  - `GET /api/dashboard/*` (stats/reports/heatmap/trends/network)
  - `GET /api/lookup/phone/{phone}` and `GET /api/check-phone/{phone}`
- Persistence:
  - High-risk analysis gets stored to Supabase via `store_analysis_report()` and edges via `store_report_edges()`.
  - Phone reputation table is updated on insert/upsert (`backend/app/services/reputation/phone_reputation.py`).
- Rate limiting:
  - `POST /api/analyze` has a SlowAPI limit of `10/minute` (other endpoints currently do not).

### AI Services (FastAPI) - `ai-services`
- Entrypoint: `ai-services/main_service.py`
- Endpoints:
  - `POST /analyse/text`
  - `POST /analyse/image`
  - `POST /analyse/audio`
  - `POST /analyse/document`
  - `GET /health`
- Capabilities:
  - OCR/image processing pipeline (large, multi-step) in `ai-services/image_pipeline.py`
  - Document pipeline with extraction + verification hooks in `ai-services/doc_pipeline.py`
  - Whisper-based transcription in `ai-services/audio_pipeline.py`
  - Entity extraction in `ai-services/entity_extractor.py`
  - Validation module (`ai-services/validator.py`) contains trust/decay/rate-limit logic from the PDF spec, but it is not clearly wired into the backend persistence model yet.

### WhatsApp Bot (Twilio) - `whatsapp-bot`
- FastAPI app: `whatsapp-bot/bot.py`
- Endpoints:
  - `POST /whatsapp` Twilio WhatsApp webhook (signature validated)
  - `POST /sms` Twilio SMS webhook (basic demo)
- Forwards user content to backend analysis endpoints and sends a Hindi verdict back.

### Browser Extension - `browser-extension`
- Manifest v3 content script that extracts page text and calls backend `POST /api/analyze`.
- Current UX is alert-based; no DOM badges/highlighting yet.

### Dashboard - `dashboard`
- React + Vite + Tailwind UI
- Talks to backend via `VITE_API_BASE_URL` (default `/api`).

## Key Gaps To Close (Prioritized)

### P0 (Must fix for a reliable demo / security hygiene)
- Move Supabase credentials out of source code:
  - `backend/app/services/supabase_client.py` hardcodes `SUPABASE_URL` and `SUPABASE_KEY`.
- Tighten CORS and origins (backend + AI service currently allow all origins).
- Align rate limiting to the PDF security layer:
  - Apply consistent limits to analysis + reporting endpoints; add per-number/per-IP protections.
- Standardize response schemas and error handling between backend and AI service.

### P1 (To match the PDF “wow moments”)
- Browser extension auto-badging per job post (Facebook/OLX/Indeed) instead of a page-level alert.
- FIR/PDF export from dashboard (PDF mentions export for cyber cells).
- Proactive pattern detection + scheduled alerts (PDF “cron every 6h” + district broadcast).
- Seed/demo data tooling: one command to seed Supabase with realistic reports and edges.

### P2 (Big features not yet started)
- QR Trust Verification System (issuance + verification + badges across surfaces).
- Field Worker PWA (offline-first bulk verify + case management).
- Telegram bot channel (PDF lists it; not present in this repo).

## Notes / Risks

- There is duplicated intelligence logic across backend (`backend/app/services/intelligence/*`) and AI service (`ai-services/*`). That’s fine for a hackathon, but long-term you likely want “one source of truth” for scoring and entity schemas.
- Some AI-service files contain non-ASCII mojibake sequences (for example “â€””). It does not break Python execution, but it makes diffs/reviews harder and can indicate encoding mismatches.
