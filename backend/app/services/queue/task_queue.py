import json

from app.services.cache.redis_client import redis_client

QUEUE_NAME = "message_queue"


def enqueue_job(data: dict):
    redis_client.lpush(QUEUE_NAME, json.dumps(data))


def dequeue_job():
    job = redis_client.brpop(QUEUE_NAME)
    if job:
        return json.loads(job[1])
    return None
