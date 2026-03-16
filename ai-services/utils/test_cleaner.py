from text_cleaner import clean_text, extract_english_text, extract_hindi_text


if __name__ == "__main__":
    samples = [
        ("ocr", "Forwarded many times\nURGENT VACANCY- 5ecurity Guard Dubai\nSalary Rs 80,000 | Registration Fee Rs 8,000\nCall +91-9876543210 Limited 5eats"),
        ("whatsapp", "Gulf mein 1.5 lakh salary milega. Registration ke liye 8,000 bhejo. Jaldi karo!"),
        ("whatsapp", "Salary: 1 crore per annum. No fee."),
    ]

    for source, text in samples:
        print(f"\nSource: {source}")
        print(f"Before: {text}")
        print(f"After:  {clean_text(text, source)}")
