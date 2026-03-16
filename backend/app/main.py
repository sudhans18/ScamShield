from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from app.routes.scam_routes import router as scam_router
from app.routes.analyze import router as analyze_router
from app.core.rate_limiter import limiter
from app.services.intelligence.ai_bridge import is_ai_service_available

app = FastAPI(
    title="NaukariSaathi API",
    description="AI-powered labour fraud detection platform",
    version="0.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(analyze_router)
app.include_router(scam_router)

@app.get("/")
def root():
    return {"message": "NaukariSaathi backend running"}


@app.get("/health")
def health():
    """Backend health endpoint."""
    return {"status": "ok"}


@app.get("/ai-health")
def ai_health():
    """AI-service connectivity health endpoint."""
    return {"ai_service": "online" if is_ai_service_available() else "offline"}
