from fastapi import APIRouter
from app.services.supabase_client import supabase

router = APIRouter()

@router.get("/check-phone/{phone}")
def check_phone(phone: str):

    result = supabase.table("scam_reports").select("*").eq("scam_phone", phone).execute()

    if result.data:
        return {
            "status": "reported",
            "data": result.data
        }

    return {
        "status": "not_reported"
    }