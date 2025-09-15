from fastapi import APIRouter

router = APIRouter()

# curl -X GET http://localhost:5000/health
@router.get("/health")
async def health_check():
    return {"status": "healthy"}
