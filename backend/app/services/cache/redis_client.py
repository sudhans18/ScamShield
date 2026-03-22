import redis

from app.core.config import settings

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True
)


def get_cache(key: str):
    return redis_client.get(key)


def set_cache(key: str, value: str, ttl: int = 3600):
    redis_client.setex(key, ttl, value)


def delete_cache(key: str):
    redis_client.delete(key)


def redis_health():
    try:
        redis_client.ping()
        return True
    except Exception:
        return False
