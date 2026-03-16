# NaukariSaathi (ScamShield) - API Reference

Last updated: 2026-03-16

This documents the APIs implemented in this repo:
- Backend API (FastAPI): `backend/app`
- AI Service (FastAPI): `ai-services`
- Messaging (Twilio WhatsApp/SMS) webhook server: `whatsapp-bot`

## Conventions

- Backend JSON endpoints live under `/api`.
- Media endpoints use `multipart/form-data` with a single file field named `file`.
- Risk scoring conventions in this repo:
  - `risk_score` is typically a float in `[0, 1]` (backend normalizes upstream values).
  - Some DB fields store `risk_score` as an integer `0-100`.
- Error responses are standard FastAPI error shapes unless otherwise noted:
  - `{ "detail": "..." }`

## Service Endpoints

### Backend API (FastAPI)

Default local base URL (typical dev): `http://127.0.0.1:8000`

Health:
- `GET /` -> `{ "message": "NaukariSaathi backend running" }`
- `GET /health` -> `{ "status": "ok" }`
- `GET /ai-health` -> `{ "ai_service": "online" | "offline" }`

#### Analysis

Router: `backend/app/routes/analyze.py`

`POST /api/analyze`
- Rate limit: `10/minute` (SlowAPI)
- Body:
```json
{
  "text": "string",
  "source": "whatsapp | extension | browser_extension | dashboard | ... (optional)"
}
```
- Response (normalized):
```json
{
  "risk_score": 0.82,
  "risk_level": "HIGH",
  "reasons": ["registration fee requested", "urgency language detected"],
  "entities": {
    "phone": ["9876543210"],
    "salary": ["80000"],
    "fee": ["8000"],
    "company": "Tata Projects Ltd",
    "location": "Dubai",
    "upi": ["rajubhai@okicici"]
  },
  "source": "ai-services | backend-rules"
}
```

`POST /api/analyze/image`
- Upload: `file` (image/*)
- Response: same shape as `/api/analyze`

`POST /api/analyze/audio`
- Upload: `file` (audio/* or video/*)
- Response: same shape as `/api/analyze`

`POST /api/analyze/document`
- Upload: `file` (PDF/DOCX)
- Response: same shape as `/api/analyze`

Notes:
- The backend will store high-risk results (`risk_score > 0.6`) into Supabase (`scam_reports`) and attempt to add graph edges (`scam_network_edges`).

#### Dashboard / Reports

Router: `backend/app/routes/scam_routes.py`

`POST /api/reports`
- Purpose: manually create a scam report row in Supabase.
- Body:
```json
{
  "reporter_hash": "string (optional)",
  "scam_phone": "string (optional)",
  "upi_id": "string (optional)",
  "company_name": "string (optional)",
  "job_role": "string (optional)",
  "salary": 80000,
  "fee": 8000,
  "location": "Bihar",
  "risk_score": 80,
  "trust_weight": 1.0
}
```
- Response:
```json
{
  "id": "uuid",
  "scam_phone": "9876543210",
  "company_name": "Example Co",
  "risk_score": 80,
  "trust_weight": 1.0,
  "report_time": "2026-03-16T12:34:56.000000+00:00"
}
```

`GET /api/dashboard/stats`
- Response:
```json
{
  "totalReports": 123,
  "suspiciousNumbers": 45,
  "detectedSyndicates": 7,
  "verifiedCompanies": 10
}
```

`GET /api/dashboard/reports?limit=10`
- Response:
```json
[
  {
    "id": "uuid",
    "phone": "9876543210",
    "message": "Company | Job role | Salary 80000 | Fee 8000 | upi@bank",
    "riskScore": "High Risk | Suspicious | Safe",
    "location": "Bihar",
    "timestamp": "2026-03-16 06:12 PM"
  }
]
```

`GET /api/dashboard/heatmap`
- Response:
```json
[
  { "state": "Bihar", "count": 12 },
  { "state": "UP", "count": 8 }
]
```

`GET /api/dashboard/trends?days=7`
- Response:
```json
[
  { "date": "03-10", "count": 1 },
  { "date": "03-11", "count": 3 }
]
```

`GET /api/dashboard/network`
- Response:
```json
{
  "nodes": [
    { "id": "9876543210", "group": 1, "label": "Phone Number" },
    { "id": "upi@bank", "group": 2, "label": "UPI ID" }
  ],
  "links": [
    { "source": "9876543210", "target": "upi@bank", "value": 1 }
  ]
}
```

`GET /api/lookup/phone/{phone}`
- Response:
```json
{
  "number": "+91 98765 43210",
  "normalizedNumber": "919876543210",
  "riskScore": "Safe | Suspicious | High Risk",
  "reportCount": 2,
  "trustScore": 0.2,
  "companies": ["Example Co"],
  "upiIds": ["upi@bank"],
  "lastSeen": "2026-03-16 06:12 PM",
  "recentReports": [
    {
      "id": "uuid",
      "company": "Example Co",
      "jobRole": "Helper",
      "riskScore": "Suspicious",
      "location": "UP",
      "reportedAt": "2026-03-16T12:34:56+00:00"
    }
  ]
}
```

`GET /api/check-phone/{phone}`
- Response:
  - If reported: `{ "status": "reported", "data": [...], "summary": { ... } }`
  - Otherwise: `{ "status": "not_reported", "summary": { ... } }`

### AI Service (FastAPI)

Default local base URL: `http://127.0.0.1:8001`

`GET /health`
- Response: `{ "status": "ok" }` (health check for backend)

`POST /analyse/text`
- Body:
```json
{
  "text": "string",
  "source_channel": "whatsapp | sms | telegram | browser_extension (optional)"
}
```
- Response: AI service returns an `AnalysisResult` (backend will normalize to its own stable schema).

`POST /analyse/image`
- Upload: `file`
- Response: `AnalysisResult`

`POST /analyse/audio`
- Upload: `file`
- Response: `AnalysisResult`

`POST /analyse/document`
- Upload: `file`
- Response: `AnalysisResult`

Notes:
- The backend calls the AI service at `AI_SERVICE_BASE_URL` (default `http://127.0.0.1:8001`) via `backend/app/services/intelligence/ai_bridge.py`.

### Messaging Server (Twilio WhatsApp/SMS)

Default base URL: wherever you host `whatsapp-bot/bot.py`.

`POST /whatsapp`
- Intended caller: Twilio WhatsApp webhook.
- Form fields (Twilio sends `application/x-www-form-urlencoded`):
  - `Body` (text message)
  - `From` (sender WhatsApp number)
  - `NumMedia` (count, string integer)
  - `MediaUrl0` (first media URL)
  - `MediaContentType0` (media MIME type)
- Security:
  - Validates `X-Twilio-Signature` using `TWILIO_AUTH_TOKEN`.
- Behavior:
  - Immediately sends “Analyzing...” then performs analysis in a background task and sends the final Hindi verdict.

`POST /sms`
- Intended caller: Twilio SMS webhook.
- Form fields:
  - `Body`
  - `From`
- Behavior:
  - Parses `CHECK ...` style content, calls backend `/api/analyze`, and replies with a short SMS verdict.

## Environment Variables (Observed in Code)

Backend:
- `AI_SERVICE_BASE_URL` (default `http://127.0.0.1:8001`)
- `AI_MEDIA_TIMEOUT` (default `30`)
- `GROQ_API_KEY` (required if using backend LLM classifier)
- `GROQ_MODEL` (optional; default `llama3-70b-8192`)

AI service:
- Depends on several model/provider env vars (see `ai-services/models/*`), plus optional Supabase env vars referenced in `ai-services/validator.py`.

WhatsApp/SMS server:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_NUMBER`
- `TWILIO_PHONE_NUMBER` (for SMS sending)
- `BACKEND_API_BASE_URL` (default `http://127.0.0.1:8000`)

