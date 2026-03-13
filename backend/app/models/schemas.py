from pydantic import BaseModel

class AnalyzeRequest(BaseModel):
    text: str
    source: str
