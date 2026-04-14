# ScamShield — API Reference

Last updated: 2026-04-15

---

## Backend API (FastAPI)

Base URL (local): `http://127.0.0.1:8000`

### Health

| Method | Endpoint | Response |
|--------|----------|----------|
| `GET` | `/` | `{"message": "NaukariSaathi backend running"}` |
| `GET` | `/health` | `{"status": "ok"}` |
| `GET` | `/health/redis` | `{"redis": "ok" \| "down"}` |

> The `/ai-health` endpoint has been removed. The backend no longer calls an external AI service.

---

### Analysis

Router: `backend/app/routes/analyze.py`

#### `POST /api/analyze`

Body (`application/json`):
```json
{
  "text": "string",
  "source": "dashboard | extension | whatsapp (optional)",
  "phone_number": "string (optional, used for rate-limit key)"
}
```

- Rate limited: `10/minute` via SlowAPI + Redis.
- Identical text payloads cached in Redis for 24 hours.

#### `POST /api/analyze/image`
- `multipart/form-data`, field: `file` (`image/*`)
- OCR via Tesseract + OpenCV → text → pipeline

#### `POST /api/analyze/audio`
- `multipart/form-data`, field: `file` (`audio/*` or `video/*`)
- Transcription via Whisper → text → pipeline

#### `POST /api/analyze/document`
- `multipart/form-data`, field: `file` (PDF/DOCX)
- Extraction via pdfplumber/python-docx + forgery scoring → text → pipeline

#### Unified Analysis Response

All four analysis endpoints return the same schema:

```json
{
  "risk_score": 0.92,
  "risk_level": "HIGH",
  "is_scam": true,
  "verdict": "HIGH_RISK",
  "confidence": 94,
  "reasons": [
    "Fee of ₹8,000 requested — illegal under eMigrate Act.",
    "Company 'Global Career Solutions' is blacklisted in registry.",
    "Claimed location Dubai does not match registered city Kolkata."
  ],
  "key_contradiction": "string | null",
  "hindi_worker_message": "Yeh offer bilkul fraud hai — koi bhi paisa mat bhejiye.",
  "english_summary": "string",
  "entities": {
    "phones": ["9876543210"],
    "salary": 80000,
    "fee": 8000,
    "role": "Security Guard",
    "location": "Dubai",
    "company": "Global Career Solutions",
    "upi_ids": ["glbljobs@paytm"],
    "urgency_flags": ["urgent", "apply today"],
    "has_fee": true,
    "has_urgency": true
  },
  "layer_scores": {
    "embedding": 0.83,
    "consistency_contradictions": 4,
    "propagation": 0.65,
    "llm_confidence": 94
  },
  "source": "dashboard",
  "input_text": "string"
}
```

**`risk_level` thresholds:**
- `< 0.35` → `"LOW"`
- `0.35 – 0.65` → `"MEDIUM"`
- `> 0.65` → `"HIGH"`

**`verdict` is set by the LLM (Layer 4):**
| Verdict | `risk_score` |
|---------|-------------|
| `LEGITIMATE` | 0.12 |
| `SUSPICIOUS` | 0.52 |
| `HIGH_RISK` | 0.92 |

**High-risk storage:** results with `risk_score > 0.6` are automatically stored to `scam_reports` and network edges written to `scam_network_edges`.

---

### Dashboard & Reports

Router: `backend/app/routes/scam_routes.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/reports` | Submit a manual scam report |
| `GET` | `/api/dashboard/stats` | Aggregate statistics |
| `GET` | `/api/dashboard/reports?limit=10` | Paginated recent reports |
| `GET` | `/api/dashboard/heatmap` | Location-based heatmap data |
| `GET` | `/api/dashboard/trends?days=7` | Report trend over time |
| `GET` | `/api/dashboard/network` | Fraud network graph (nodes + edges) |
| `GET` | `/api/lookup/phone/{phone}` | Phone reputation lookup |
| `GET` | `/api/check-phone/{phone}` | Quick phone risk check |

---

### Webhook (Backend-side)

Router: `backend/app/routes/webhook_routes.py`

#### `POST /whatsapp`

Receives Twilio WhatsApp webhooks directly at the backend layer (used when the backend is exposed directly or by the message worker). Validates `X-Twilio-Signature`.

Form fields:
- `Body` — message text
- `From` — sender WhatsApp number
- `NumMedia` — number of media attachments
- `MediaUrl0` — first media URL
- `MediaContentType0` — MIME type of first media
- `ForwardedManyTimes` — Twilio forwarding flag (used by Layer 3)

---

## WhatsApp Bot Server

Base URL: `http://localhost:9000` (or your ngrok tunnel)

#### `POST /whatsapp`

Same form fields as backend webhook above. The bot:
1. Validates `X-Twilio-Signature`.
2. Sends an immediate "analyzing..." reply to the user.
3. Enqueues job to Redis.
4. Returns `{"status": "queued"}` to Twilio.

The background `message_worker.py` process picks up the job, runs analysis, and sends the final verdict reply.

#### `POST /sms`

Form fields: `Body`, `From`.  
Synchronously calls `POST /api/analyze` on the backend and replies with a short SMS verdict.

---

## Environment Variables Reference

### Backend (`backend/.env` or root `.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPABASE_URL` | ✅ | — | Supabase project URL |
| `SUPABASE_KEY` | ✅ | — | Supabase anon or service key |
| `REDIS_URL` | ✅ | — | Redis connection string |
| `GROQ_API_KEY` | ✅ | — | Groq API key for Layer 4 LLM |
| `TWILIO_ACCOUNT_SID` | ⚡ webhook | — | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | ⚡ webhook | — | Twilio auth token (signature validation) |
| `TWILIO_WHATSAPP_NUMBER` | ⚡ webhook | — | Sender, e.g. `whatsapp:+14155238886` |
| `GROQ_INVESTIGATOR_MODEL` | ❌ | `llama-3.3-70b-versatile` | Override LLM model |
| `TESSERACT_CMD` | ❌ | System default | Path to Tesseract binary (Windows) |

### WhatsApp Bot (`whatsapp-bot/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `TWILIO_ACCOUNT_SID` | ✅ | Must match root `.env` |
| `TWILIO_AUTH_TOKEN` | ✅ | Must match root `.env` |
| `TWILIO_WHATSAPP_NUMBER` | ✅ | Sender number |
| `BACKEND_API_BASE_URL` | ❌ | Default: `http://127.0.0.1:8000` |

> `AI_SERVICE_URL` is **deprecated and removed**. Do not set it.
