from app.services.cache.redis_client import redis_client


def check_rate_limit(phone: str):
    key = f"rate:{phone}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 60)
    if count > 10:
        return False
    return True
