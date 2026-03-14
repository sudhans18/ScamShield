from app.services.intelligence.analyzer import analyze_text

def analyze_message(text: str):

    result = analyze_text(text)

    return result
