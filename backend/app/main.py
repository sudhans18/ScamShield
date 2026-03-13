from fastapi import FastAPI
from app.routes.analyze import router as analyze_router

app = FastAPI(
    title="NaukariSaathi API",
    description="AI-powered labour fraud detection platform",
    version="0.1"
)

app.include_router(analyze_router)

@app.get("/")
def root():
    return {"message": "NaukariSaathi backend running"}
