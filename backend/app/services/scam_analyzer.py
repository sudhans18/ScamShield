def analyze_message(text: str):

    scam_keywords = [
        "registration fee",
        "processing fee",
        "urgent vacancy",
        "limited seats",
        "send money",
        "visa fee"
    ]

    risk = 0
    reasons = []

    for word in scam_keywords:
        if word in text.lower():
            risk += 0.2
            reasons.append(word)

    if risk > 1:
        risk = 1

    return {
        "risk_score": risk,
        "risk_level": "HIGH" if risk > 0.6 else "MEDIUM" if risk > 0.3 else "LOW",
        "reasons": reasons
    }
