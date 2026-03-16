from fastapi import FastAPI, Form, Request, Response, HTTPException
from twilio.rest import Client
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv
import os, re

load_dotenv()

app = FastAPI()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

client    = Client(ACCOUNT_SID, AUTH_TOKEN)
validator = RequestValidator(AUTH_TOKEN)

# ── Fake intelligence engine (swap this out when Person 2 is ready) ──────────
def check_scam(text: str) -> dict:
    text_lower = text.lower()
    score = 0
    reasons = []

    fee_words = ["fee", "registration", "advance", "deposit", "bhejo", "paisa", "rs.", "₹"]
    urgent_words = ["urgent", "limited", "aaj", "kal", "abhi", "jaldi", "tonight", "today"]
    salary_pattern = re.search(r'(\d{4,6})', text)

    for word in fee_words:
        if word in text_lower:
            score += 30
            reasons.append("Fee maanga ja raha hai")
            break

    for word in urgent_words:
        if word in text_lower:
            score += 20
            reasons.append("Urgency dikhaya ja raha hai")
            break

    if salary_pattern:
        salary = int(salary_pattern.group())
        if salary > 50000:
            score += 25
            reasons.append(f"Salary {salary} — bahut zyada lagti hai")

    phone_match = re.search(r'[6-9]\d{9}', text)
    if phone_match:
        score += 10
        reasons.append(f"Phone number mila: {phone_match.group()}")

    score = min(score, 99)
    return {"score": score, "reasons": reasons, "phone": phone_match.group() if phone_match else None}

# ── Hindi response builder ────────────────────────────────────────────────────
def build_hindi_response(result: dict, original_msg: str) -> str:
    score   = result["score"]
    reasons = result["reasons"]
    phone   = result["phone"]

    reason_text = "\n".join(f"• {r}" for r in reasons) if reasons else "• Koi clear signal nahi mila"

    if score >= 60:
        verdict = "🚨 KHATRE KI BAAT"
        summary = f"Yeh message {score}% sambhavna se FARZI hai."
        advice  = "⛔ PAISE MAT BHEJO. Koi bhi fee genuine naukri mein pehle nahi maangi jaati."
    elif score >= 30:
        verdict = "⚠️ SAVDHAAN RAHEIN"
        summary = f"Yeh message thoda suspicious lagta hai ({score}% risk)."
        advice  = "🔍 Pehle company ka naam Google karein. Koi bhi paise dene se pehle verify karein."
    else:
        verdict = "✅ THEEK LAGTA HAI"
        summary = "Is message mein koi bada red flag nahi mila."
        advice  = "Phir bhi: koi bhi registered company pehle fee nahi maangti. Savdhan rahein."

    phone_line = f"\n📞 Number found: {phone} — verify karein is number ko" if phone else ""

    return (
        f"*NaukariSaathi — Job Safety Check*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"*{verdict}*\n\n"
        f"{summary}\n\n"
        f"*Kya dikha:*\n{reason_text}"
        f"{phone_line}\n\n"
        f"{advice}\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"_Hum kabhi paise, OTP ya Aadhaar nahi maangte._\n"
        f"_Verify: naukrisaathi.in/verify_"
    )

# ── WhatsApp webhook ──────────────────────────────────────────────────────────
@app.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
    NumMedia: str = Form(default="0"),
):
    # Twilio signature validation (security)
    url       = str(request.url)
    signature = request.headers.get("X-Twilio-Signature", "")
    form_data = dict(await request.form())

    if not validator.validate(url, form_data, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    print(f"[WhatsApp] From: {From} | Message: {Body[:80]}")

    if not Body.strip():
        reply = (
            "*NaukariSaathi mein aapka swagat hai!* 🙏\n\n"
            "Koi bhi suspicious naukri ka message yahan forward karein.\n"
            "Hum 30 seconds mein batayenge — safe hai ya nahi.\n\n"
            "_Hum kabhi paise nahi maangte._"
        )
    else:
        result = check_scam(Body)
        reply  = build_hindi_response(result, Body)

    client.messages.create(
        from_=FROM_NUMBER,
        to=From,
        body=reply
    )

    return Response(content="", media_type="text/xml")

# ── SMS webhook ───────────────────────────────────────────────────────────────
@app.post("/sms")
async def sms_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(default=""),
):
    print(f"[SMS] From: {From} | Message: {Body[:80]}")

    # SMS messages are shorter — strip "CHECK " prefix if present
    text = Body.replace("CHECK", "").strip()

    result = check_scam(text)
    score  = result["score"]

    if score >= 60:
        reply = f"KHATRE KI BAAT! {score}% risk. Paise mat bhejo. NaukariSaathi"
    elif score >= 30:
        reply = f"Savdhaan! {score}% risk. Pehle verify karein. NaukariSaathi"
    else:
        reply = f"Zyada risk nahi dikh raha ({score}%). Phir bhi savdhan rahein. NaukariSaathi"

    client.messages.create(
        from_=os.getenv("TWILIO_PHONE_NUMBER", FROM_NUMBER),
        to=From,
        body=reply
    )
    return Response(content="", media_type="text/xml")

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "NaukariSaathi messaging server is running"}