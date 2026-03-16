from fastapi import APIRouter
from app.models.schemas import AnalyzeRequest
from app.services.scam_analyzer import analyze_message

router = APIRouter(prefix="/api", tags=["analysis"])

@router.post("/analyze")
def analyze(req: AnalyzeRequest):

    result = analyze_message(req.text)

    return result
