import json

from app.services.cache.redis_client import redis_client

QUEUE_NAME = "message_queue"


def enqueue_job(data: dict):
    try:
        redis_client.lpush(QUEUE_NAME, json.dumps(data))
    except Exception:
        return None


def dequeue_job():
    try:
        job = redis_client.brpop(QUEUE_NAME)
    except Exception:
        return None
    if job:
        try:
            return json.loads(job[1])
        except Exception:
            return None
    return None
