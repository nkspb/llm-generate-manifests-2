from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from models import QueryRequest
from core.manifest_engine import start_manifest_flow_from_query
from core.session_manager import SessionStore
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

llm = None
vector_store = None
session_store: SessionStore = None

@router.post("/get_manifests")
async def get_manifest(request: QueryRequest, fastapi_request: Request):
    query = request.query

    client_ip = fastapi_request.client.host if fastapi_request.client else "unknown"
    logger.info(f"[GET_MANIFESTS Request from {client_ip} with query: {query}]")
    
    try:
        response = start_manifest_flow_from_query(query=query, vector_store=vector_store, llm=llm, session_store=session_store)
    except Exception as e:
        logger.exception("Error during manifest flow")
        return PlainTextResponse(
            content="Произошла ошибка при обработке запроса",
            status_code=500,
            media_type="text/plain"
        )

    return PlainTextResponse(
        content=response.reply,
        headers={
            "App-Session-Id": response.session_id or "",
            "App-Intent": response.intent
        },
        media_type="text/plain"
    )
