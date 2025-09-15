from fastapi import APIRouter
from models import ClassifyRequest, ClassifyResponse
from core.llm_utils import llm_classify_intent

router = APIRouter()
llm = None # Will be injected

# curl -X POST http://localhost:5000/classify -H "Content-Type: application/json" -d '{"query": "Что ты умеешь?"}'
@router.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    label = llm_classify_intent(llm, request.query)
    print(label)
    return ClassifyResponse(intent=label)
