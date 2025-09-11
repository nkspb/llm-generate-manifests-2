from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from models import QueryRequest
from core.manifest_flow import start_manifest_flow_from_query
import logging
router = APIRouter()

llm = None
vector_store = None
sessions = None

logger = logging.getLogger(__name__)

@router.post("/get_manifests")
async def get_manifest(request: QueryRequest, fastapi_request: Request):
    query = request.query
    client_ip = fastapi_request.client.host if fastapi_request.client else "unknown"
    logger.info(f"[GET_MANIFESTS Request from {client_ip} with query: {query}]")
    
    try:
        response = start_manifest_flow_from_query(query, vector_store, llm, sessions)
        if not response:
            logger.warning("[GET_MANIFESTS] start_manifest_flow_from_query returned None!")
            return PlainTextResponse(content="Произошла ошибка. Попробуйте другой запрос", status_code=500)

        logger.info(f"[GET_MANIFESTS] ChatResponse: intent={response.intent}, session_id={response.session_id}, reply={response.reply}")
        return PlainTextResponse(
            content=response.reply,
            headers={
                "App-Session-Id": response.session_id or "",
                "App=Intent": response.intent
            },
            media_type="text/plain"
        )

    except Exception as e:
        logger.exception(f"[GET_MANIFESTS] Unexpected error: {e}")
        return PlainTextResponse(
            content="Произошла ошибка при обработке запроса",
            status_code=500
        )

