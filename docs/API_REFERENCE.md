# NaukariSaathi (ScamShield) - API Reference

Last updated: 2026-03-17

This documents the APIs implemented in this repo:
- Backend API (FastAPI): `backend/app`
- AI Service (FastAPI): `ai-services`
- Messaging (Twilio WhatsApp/SMS) webhook server: `whatsapp-bot`

## Conventions

- Backend JSON endpoints live under `/api`.
- Media endpoints use `multipart/form-data` with a single file field named `file`.
- Error responses follow standard FastAPI shapes unless otherwise noted:
  - `{ "detail": "..." }`

## Backend API (FastAPI)

Default local base URL: `http://127.0.0.1:8000`

Health:
- `GET /` -> `{ "message": "NaukariSaathi backend running" }`
- `GET /health` -> `{ "status": "ok" }`
- `GET /ai-health` -> `{ "ai_service": "online" | "offline" }`
- `GET /health/redis` -> `{ "redis": "ok" | "down" }`

### Analysis

Router: `backend/app/routes/analyze.py`

`POST /api/analyze`
- Body:
```json
{
  "text": "string",
  "source": "whatsapp | extension | browser_extension | dashboard | ... (optional)",
  "phone_number": "string (optional, used for Redis rate-limit key)"
}
```
- Behavior:
  - Rate limited (`10/minute` via SlowAPI + Redis limiter).
  - Caches identical text payloads for 24 hours using Redis key `analysis:{sha256(text)}`.

`POST /api/analyze/image`
- Upload: `file` (image/*)

`POST /api/analyze/audio`
- Upload: `file` (audio/* or video/*)

`POST /api/analyze/document`
- Upload: `file` (PDF/DOCX)

All analysis endpoints return normalized payload:
```json
{
  "risk_score": 0.82,
  "risk_level": "HIGH",
  "reasons": ["registration fee requested", "urgency language detected"],
  "entities": {
    "phone": ["9876543210"],
    "salary": ["80000"],
    "fee": ["8000"],
    "company": "Example Co",
    "location": "Bihar",
    "upi": ["upi@bank"]
  },
  "source": "ai-services | backend-rules"
}
```

Notes:
- High-risk results (`risk_score > 0.6`) are stored in Supabase (`scam_reports`) and graph edges are added to `scam_network_edges`.

### Dashboard / Reports

Router: `backend/app/routes/scam_routes.py`

- `POST /api/reports`
- `GET /api/dashboard/stats`
- `GET /api/dashboard/reports?limit=10`
- `GET /api/dashboard/heatmap`
- `GET /api/dashboard/trends?days=7`
- `GET /api/dashboard/network`
- `GET /api/lookup/phone/{phone}`
- `GET /api/check-phone/{phone}`

## AI Service (FastAPI)

Default local base URL: `http://127.0.0.1:8001`

- `GET /health`
- `POST /analyse/text`
- `POST /analyse/image`
- `POST /analyse/audio`
- `POST /analyse/document`

Notes:
- Backend calls AI service using `AI_SERVICE_URL` (default `http://localhost:8001`) in `backend/app/services/intelligence/ai_bridge.py`.

## Messaging Server (Twilio WhatsApp/SMS)

Run separately from backend (different process), usually on its own port.

`POST /whatsapp`
- Caller: Twilio WhatsApp webhook.
- Form fields: `Body`, `From`, `NumMedia`, `MediaUrl0`, `MediaContentType0`.
- Security: validates `X-Twilio-Signature` using `TWILIO_AUTH_TOKEN`.
- Behavior:
  - Enqueues payload to Redis queue `message_queue`.
  - Returns immediately: `{ "status": "queued" }`.

## Backend Webhook Compatibility

`POST /whatsapp`
- Caller: Twilio WhatsApp webhook (legacy/backend-compatible entrypoint).
- Behavior: same queueing behavior as messaging service endpoint.

`POST /sms`
- Caller: Twilio SMS webhook.
- Form fields: `Body`, `From`.
- Behavior: calls backend `/api/analyze` and replies with a short SMS verdict.

## Environment Variables

Backend:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `REDIS_URL`
- `AI_SERVICE_URL` (default `http://localhost:8001`)
- `AI_MEDIA_TIMEOUT` (default `30`)
- `GROQ_API_KEY` (required only where LLM classifier is enabled)
- `GROQ_MODEL` (optional; default `llama3-70b-8192`)

WhatsApp/SMS server:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER`
- `TWILIO_PHONE_NUMBER`
- `BACKEND_API_BASE_URL` (default `http://127.0.0.1:8000`)
