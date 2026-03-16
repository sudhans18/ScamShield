from image_pipeline import process_image
from entity_extractor import extract_entities
from models.scam_classifier import classify

IMAGE_PATH = "sample_inputs/test-image 1.png"


def run_pipeline(image_path):
    print("\n========== SCAMSHIELD PIPELINE TEST ==========\n")

    # STEP 1 — OCR
    ocr_result = process_image(image_path)

    if not ocr_result.get("success"):
        print("OCR FAILED:", ocr_result.get("error"))
        return

    text = ocr_result["extracted_text"]

    print("OCR TEXT:\n")
    print(text[:800])
    print("\n-----------------------------------\n")

    # STEP 2 — Entity extraction
    entities = extract_entities(text)

    print("EXTRACTED ENTITIES:\n")
    print(entities)
    print("\n-----------------------------------\n")

    # STEP 3 — Scam classification
    result = classify(text, entities=entities)

    print("SCAM CLASSIFICATION RESULT:\n")
    print(result)

    print("\n========== END ==========\n")


if __name__ == "__main__":
    run_pipeline(IMAGE_PATH)