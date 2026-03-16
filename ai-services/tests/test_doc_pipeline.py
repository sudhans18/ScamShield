import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from doc_pipeline import process_document
from doc_pipeline import process_document
from entity_extractor import extract_entities
from models.scam_classifier import classify


# change this to your file
FILE_PATH = "sample_inputs/test_joboff.docx"


print("\n========== DOCUMENT PIPELINE TEST ==========\n")

# Step 1 — Extract document text
doc_result = process_document(FILE_PATH)

if not doc_result.get("success"):
    print("DOCUMENT PROCESSING FAILED:")
    print(doc_result)
    exit()

print("DOCUMENT FORMAT:", doc_result.get("doc_format"))
print("PAGES:", doc_result.get("page_count"))
print("COMPANY:", doc_result.get("company_name"))
print("GST:", doc_result.get("gst_number"))
print("FORGERY RISK:", doc_result.get("forgery_risk"))

print("\n-----------------------------------\n")

# Step 2 — Show extracted text
text = doc_result.get("extracted_text", "")

print("EXTRACTED TEXT:\n")
print(text[:800])  # show first 800 chars

print("\n-----------------------------------\n")

# Step 3 — Extract entities
entities = extract_entities(text)

print("EXTRACTED ENTITIES:\n")
print(entities)

print("\n-----------------------------------\n")

# Step 4 — Run scam classifier
result = classify(text, entities=entities, context="Document OCR/Text extraction")

print("SCAM CLASSIFICATION RESULT:\n")
print(result)

print("\n========== END ==========\n")