import redis

from app.core.config import settings

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True
)


def get_cache(key: str):
    try:
        return redis_client.get(key)
    except Exception:
        return None


def set_cache(key: str, value: str, ttl: int = 3600):
    try:
        redis_client.setex(key, ttl, value)
    except Exception:
        return None


def delete_cache(key: str):
    try:
        redis_client.delete(key)
    except Exception:
        return None


def redis_health():
    try:
        redis_client.ping()
        return True
    except Exception:
        return False
