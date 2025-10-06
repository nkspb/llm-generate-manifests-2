import uuid
import logging
from models import ChatResponse
from typing import Optional
from core.placeholder_engine import extract_placeholders, format_placeholder_list
from core.session_manager import SessionStore, SessionState

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.4

def start_manifest_flow_from_query(query: str, vector_store, llm, session_store: SessionStore, reuse_session_id: Optional[str] = None) -> ChatResponse:
    """
    Perform vector search, extract placeholders, and initialize LLM-guided flow.
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
        )

    if not results:
        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply=("К сожалению, не удалось найти подходящий манифест. Попробуйте другой запрос.\n"),
            session_id=reuse_session_id
        )

    matched_doc, raw_score = results[0]
    logger.debug("Found document: %s, raw_score = %s", matched_doc.metadata, raw_score)

    doc_source = matched_doc.metadata.get("source", "source unknown")

    try:
        with open(doc_source, encoding="utf-8") as f:
            doc_text = f.read()
        print(f"[MANIFEST_SEARCH] Selected manifest file: {doc_source}")
    except Exception as e:
        logger.warning(f"Failed to load raw YAML from {doc_source}, falling back to embedded text: {e}")
        doc_text = matched_doc.page_content

    similarity = 1 - raw_score
    if similarity < SIMILARITY_THRESHOLD:
        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply=("К сожалению, не удалось найти подходящий манифест. Попробуйте другой запрос.\n"),
            session_id=reuse_session_id
        )
    placeholders = extract_placeholders(doc_text)
    first_placeholder = placeholders[0] if placeholders else None
    placeholder_list = format_placeholder_list(placeholders)


    state = SessionState(
        mode="MANIFEST",
        original_doc_text=doc_text,
        remaining_placeholders=placeholders[1:] if first_placeholder else [],
        filled_values={},
        current_placeholder=first_placeholder,
        source_file=doc_source
    )
    session_id = session_store.create(state, reuse_session_id)

    if not first_placeholder:
        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply=("Манифест найден и не содержит параметров для заполнения."),
            session_id=session_id
    )

    prompt = (
        f"""Ты - ассистент, который помогает пользователю сформировать манифесты для интеграции сервисов.
        Поприветствуй пользователя и скажи ему, что нашел необходимые манифесты, которые требуется заполнить: {placeholder_list}
        Перечисли все поля, которые нужны для заполнения, с кратким описанием их назначения в одно предложение.
        Помоги пользователю заполнить YAML-файл манифеста, в котором есть плейсхолдер `{{{{ ${first_placeholder} }}}}`.
        Объясни его назначение и задай вопрос, чтобы получить значение."""
    )

    try:
        llm_response = llm.invoke(prompt)
        ai_message = (getattr(llm_response, "content", "") or "").strip() or f"Введите значение для плейсхолдера {{{{first_placeholder}}}}:"
    except Exception as e:
        logger.warning(f"[MANIFEST_FLOW] Ошибка при обращении к LLM: {e}")
        ai_message = f"Введите значение для плейсхолдера ${{{first_placeholder}}}:"
    
    logger.info("[MANIFEST_FLOW] Новая сессия создана: %s", session_id)

    return ChatResponse(
        intent="GET_MANIFESTS",
        action="NONE",
        suggested_payload=None,
        reply=ai_message,
        session_id=session_id
    )
