from image_pipeline import process_image
from entity_extractor import extract_entities

# run OCR
result = process_image("sample_inputs/test-image 1.png")

# extract entities
entities = extract_entities(result["extracted_text"])

print("\nOCR TEXT:\n")
print(result["extracted_text"])

print("\nEXTRACTED ENTITIES:\n")
print(entities)