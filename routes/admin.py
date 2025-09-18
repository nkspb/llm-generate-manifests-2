from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()
session_store = None

@router.get("/sessions")
async def list_sessions():
    return JSONResponse(content={"active_sessions": session_store.list_ids()})

