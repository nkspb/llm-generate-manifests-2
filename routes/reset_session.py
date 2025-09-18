from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from core.session_manager import SessionStore
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

session_store: SessionStore = None

@router.post("/reset_all_sessions")
async def reset_all_sessions():
    session_store.clear()
    return PlainTextResponse("Все сессии успешно завершены", status_code=200)
    
@router.post("/reset_session/{session_id}")
async def reset_session(session_id: str):
    session = session_store.get(session_id)
    if not session:
        return PlainTextResponse(f"Сессия {session_id} не найдена или уже завершена", status_code=404)
    
    session_store.end(session_id)
    return PlainTextResponse(f"Сессия {session_id} успешно завершена", status_code=200)
