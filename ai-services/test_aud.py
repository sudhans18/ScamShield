from audio_pipeline import process_audio
from entity_extractor import extract_entities
from models.scam_classifier import classify

AUDIO_FILE = "sample_inputs/test_audio1.mp3"

print("\n========= AUDIO TEST =========\n")

audio = process_audio(AUDIO_FILE)

if not audio["success"]:
    print(audio["error"])
    exit()

text = audio["transcript"]

print("\nTRANSCRIPT:\n")
print(text)

print("\n-------------------------------\n")

entities = extract_entities(text)

print("ENTITIES:\n")
print(entities)

print("\n-------------------------------\n")

result = classify(text, entities)

print("SCAM RESULT:\n")
print(result)