from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from app.routes.scam_routes import router as scam_router
from app.routes.analyze import router as analyze_router
from app.routes.webhook_routes import router as webhook_router
from app.core.rate_limiter import limiter
from app.services.cache.redis_client import redis_health
import logging
import asyncio

app = FastAPI(
    title="ScamShield API",
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
app.include_router(webhook_router)

logger = logging.getLogger(__name__)

@app.get("/")
def root():
    return {"message": "ScamShield backend running"}


@app.get("/health")
def health():
    """Backend health endpoint."""
    return {"status": "ok"}


@app.get("/health/redis")
def redis_health_check():
    return {"redis": "ok" if redis_health() else "down"}


@app.on_event("startup")
async def startup() -> None:
    try:
        from app.services.intelligence.embedding_scorer import _get_model

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _get_model)
        logger.info("LaBSE model preloaded")
    except Exception as exc:
        logger.warning("LaBSE preload failed (non-fatal): %s", exc)
