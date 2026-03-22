import redis
import os
from dotenv import load_dotenv

load_dotenv()

r = redis.from_url(os.getenv("REDIS_URL"))

r.set("test", "hello")
print(r.get("test"))