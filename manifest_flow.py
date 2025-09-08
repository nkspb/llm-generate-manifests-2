import uuid
import logging
from models import ChatResponse
from typing import Optional
from core.placeholder_engine import extract_placeholders
from placeholder_utils import format_placeholder_list

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.4

def start_manifest_flow_from_query(query: str, vector_store, llm, sessions: dict, reuse_session_id: Optional[str] = None) -> "ChatResponse":
    """
        Same logics as in get_manifests, 
        but returns ChatResponse so that /chat could perform the flow
    """
    try:
        results = vector_store.similarity_search_with_score(query, k=1)
    except Exception as e:
        logger.error(f"Произошла ошибка при поиске по векторной базе: {e}")
        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply="Произошла ошибка при поиске манифестов. Попробуйте другой запрос.",
            session_id=reuse_session_id
        ).dict()

    if not results:
        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply=("К сожалению, не удалось найти подходящий манифест. Попробуйте другой запрос.\n"),
            session_id=reuse_session_id
        ).dict()

    matched_doc, raw_score = results[0]
    logger.debug("Found document: %s, raw_score = %s", matched_doc.metadata, raw_score)

    doc_text = matched_doc.page_content
    doc_source = matched_doc.metadata.get("source", "source unknown")

    similarity = 1 - raw_score
    SIMILARITY_THRESHOLD = 0.4
    if similarity < SIMILARITY_THRESHOLD:
        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply=("К сожалению, не удалось найти подходящий манифест. Попробуйте другой запрос.\n"),
            session_id=reuse_session_id
        ).dict()
    placeholders = extract_placeholders(doc_text)

    session_id = reuse_session_id or str(uuid.uuid4())
    if not placeholders:
        sessions[session_id] = {
            "mode": "MANIFEST",
            "original_doc_text": doc_text,
            "remaining_placeholders": [],
            "filled_values": {},
            "current_placeholder": None,
            "source_file": doc_source
        }

        placeholder_list = format_placeholder_list(placeholders)

        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply=("Манифест найден. Необходимо заполнить все поля. Отправьте render, чтобы показать их\n"),
            session_id=session_id
        ).dict()
