# ScamShield — Setup and Configuration

Last updated: 2026-04-15

---

## Architecture Overview

ScamShield runs as **two processes** — all heavy intelligence work merged into the backend (no separate `ai-services` process):

| Process | Directory | Port | Purpose |
|---------|-----------|------|---------|
| Backend API | `backend/` | 8000 | 4-layer intelligence pipeline + REST API |
| WhatsApp Bot | `whatsapp-bot/` | 9000 | Twilio webhook receiver + message dispatcher |
| Message Worker | `backend/workers/` | — | Background job consumer (Redis queue) |
| Dashboard | `dashboard/` | 5173 | Frontend UI |
| Browser Extension | `browser-extension/` | — | Chrome/Edge extension |

---

## Prerequisites

| Tool | Version | Required For |
|------|---------|-------------|
| Python | ≥ 3.11 | Backend, bot, worker |
| Tesseract OCR | ≥ 5.x | Image text extraction |
| Poppler | any | `pdf2image` (PDF rendering) |
| Redis | any | Queue + cache (Upstash recommended) |
| Supabase | pgvector enabled | Database |
| Groq API Key | free tier | Layer 4 LLM (required) |
| Twilio account | sandbox OK | WhatsApp webhook (optional for dev) |

---

## One-Time Database Setup

### 1. Enable pgvector in Supabase
Supabase Dashboard → Database → Extensions → search `vector` → Enable.

### 2. Run the schema SQL
In the Supabase SQL editor, paste and run:
```
backend/sql/intelligence_layer_tables.sql
```
This creates all tables needed by the 4-layer pipeline:
- `job_postings_legitimate`, `job_postings_scam`, `cluster_centroids` (Layer 1)
- `company_registry`, `phone_prefix_location` (Layer 2)
- `message_fingerprints` (Layer 3)

### 3. Seed mock reference data
```bash
# From repo root
python scripts/seed_mock_data.py
```
Inserts ~50 company registry rows and ~45 phone prefix rows into Supabase.

### 4. Compute LaBSE cluster centroids
```bash
# From repo root (first run downloads ~500 MB LaBSE model — takes ~5 min)
python scripts/compute_centroids.py
```
Embeds all seed job postings and writes centroid vectors to `cluster_centroids`. **Run once only.**

---

## Environment Variables

Create a single `.env` file in the **repo root**:

```env
# Supabase
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<anon or service role key>

# Redis
REDIS_URL=redis://localhost:6379
# Upstash TLS example: rediss://default:<password>@<host>:6379

# Groq (Layer 4 — required)
GROQ_API_KEY=gsk_...

# Twilio (optional for local dev, required for WhatsApp bot)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Tesseract (Windows only — default path used if unset)
# TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe

# Optional: LaBSE model override
# GROQ_INVESTIGATOR_MODEL=llama-3.3-70b-versatile
```

`whatsapp-bot/.env` should contain **the same** Twilio credentials as the root `.env`. Duplicate them there so the bot process can load them independently.

> ⚠️ The `AI_SERVICE_URL` variable is **no longer used**. The backend runs all intelligence in-process. Remove it if present.

---

## Running the Services

### 1. Backend API (port 8000)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- LaBSE warms up in the background on startup (non-blocking log: `LaBSE model preloaded`).
- No second process needed. The old `ai-services/` directory no longer exists.

### 2. Message Worker (background job consumer)

```bash
# Separate terminal — stays running alongside the backend
cd backend
python workers/message_worker.py
```

The worker dequeues jobs from Redis, runs the full AI analysis pipeline, and sends the WhatsApp reply. It is **not** part of the FastAPI app — it's a standalone loop.

### 3. WhatsApp Bot (port 9000)

```bash
cd whatsapp-bot
pip install -r requirements.txt
uvicorn bot:app --port 9000
```

Expose it via ngrok or Cloudflare Tunnel and set the Twilio webhook to:
```
https://<your-tunnel>/whatsapp
```

> The bot only enqueues jobs to Redis and acks Twilio immediately. Heavy analysis runs in the worker.

### 4. Dashboard (Vite)

```bash
cd dashboard
npm install
npm run dev
```

Set `VITE_API_BASE_URL=http://127.0.0.1:8000/api` if not using a proxy.

### 5. Browser Extension

Load `browser-extension/` as an unpacked extension in Chrome/Edge (Developer Mode).  
The extension calls `http://localhost:8000/api/analyze` by default — update `manifest.json` host permissions if pointing to a remote backend.

---

## Twilio Signature Validation

The bot validates every inbound webhook with `X-Twilio-Signature`. Common failure causes:

| Symptom | Cause | Fix |
|---------|-------|-----|
| 403 Forbidden | Wrong `TWILIO_AUTH_TOKEN` in `whatsapp-bot/.env` | Match the token from root `.env` / Twilio console |
| 403 Forbidden | URL mismatch (ngrok http vs https) | Bot now reconstructs public URL from `X-Forwarded-Proto` + `Host` headers automatically |
| 403 Forbidden (sandbox) | Auth token from a different Twilio sub-account | Use the primary account's auth token |
