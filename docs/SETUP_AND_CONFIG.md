# NaukariSaathi (ScamShield) - Setup and Config

Last updated: 2026-03-16

This repo is a multi-service prototype. At minimum, the “happy path” demo involves:
1. AI Service (`ai-services/`) on port `8001`
2. Backend API (`backend/`) on port `8000`
3. Dashboard UI (`dashboard/`) (typically Vite dev server)
4. Optional: Twilio WhatsApp/SMS webhook server (`whatsapp-bot/`)
5. Optional: Browser extension (`browser-extension/`)

## 1) AI Service (port 8001)

Code: `ai-services/main_service.py`

Run (example, if Python + deps are installed):
- `uvicorn main_service:app --reload --port 8001`

Notes:
- Audio transcription uses Whisper and can be heavy (startup preloads the model).
- OCR/document pipelines may require system dependencies (Tesseract/Poppler) depending on platform.

## 2) Backend (port 8000)

Code: `backend/app/main.py`

Run (example):
- from `backend/` directory, make sure `backend` is on the Python path so imports like `from app...` work.
- `uvicorn app.main:app --reload --port 8000`

Backend configuration:
- `AI_SERVICE_URL` (default `http://localhost:8001`)
- `AI_MEDIA_TIMEOUT` (default `30`)

LLM configuration (only used for “medium” ambiguity in backend fallback pipeline):
- `GROQ_API_KEY` (required to call Groq)
- `GROQ_MODEL` (optional)

Important security note:
- `backend/app/services/supabase_client.py` currently hardcodes Supabase URL/key. This should be moved to environment variables before any real deployment.

## 3) Dashboard (Vite)

Code: `dashboard/`

The dashboard expects the backend API under `/api` by default. Configure:
- `VITE_API_BASE_URL` to point to the backend (e.g. `http://127.0.0.1:8000/api`) if not proxying.

## 4) WhatsApp / SMS Webhooks (Twilio)

Code: `whatsapp-bot/bot.py`

Key env vars:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER` (sender, `whatsapp:+...`)
- `TWILIO_PHONE_NUMBER` (sender for SMS)
- `BACKEND_API_BASE_URL` (default `http://127.0.0.1:8000`)

Twilio should send webhooks to the WhatsApp bot service URL (not backend):
- `POST /whatsapp`
- `POST /sms`

If Twilio points to backend (`:8000/whatsapp`), you will get `404 Not Found` because these routes live in `whatsapp-bot/bot.py`.

The webhook handler validates the `X-Twilio-Signature` header against your Auth Token.

## 5) Browser Extension

Code: `browser-extension/`

Current behavior:
- Extracts page text and posts to `http://localhost:8000/api/analyze`.

To use against a non-local backend you’ll need to update:
- `browser-extension/content.js`
- `browser-extension/popup.js`
- `browser-extension/manifest.json` host permissions
