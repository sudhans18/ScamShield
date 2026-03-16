from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.scam_routes import router as scam_router
from app.routes.analyze import router as analyze_router

app = FastAPI(
    title="NaukariSaathi API",
    description="AI-powered labour fraud detection platform",
    version="0.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(scam_router)

@app.get("/")
def root():
    return {"message": "NaukariSaathi backend running"}
