from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")


settings = Settings()
