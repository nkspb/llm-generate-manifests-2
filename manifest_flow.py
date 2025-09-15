import uuid
import logging
from models import ChatResponse
from typing import Optional
from core.placeholder_engine import extract_placeholders
from core.placeholder_engine import format_placeholder_list
from core.session_manager import SessionStore, SessionState

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.4

def start_manifest_flow_from_query(query: str, vector_store, llm, session_store: SessionStore, reuse_session_id: Optional[str] = None) -> ChatResponse:
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
        )
    placeholders = extract_placeholders(doc_text)
    first_placeholder = placeholders[0] if placeholders else None
    placeholder_list = format_placeholder_list(placeholders)

    if not first_placeholder:
        state = SessionState(
            mode="MANIFEST",
            original_doc_text=doc_text,
            remaining_placeholders=placeholders[1:],
            filled_values={},
            current_placeholder=first_placeholder,
            source_file=doc_source
        )
        session_id = session_store.create(state, reuse_session_id)
        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply=("Манифест найден. Необходимо заполнить все поля. Отправьте render, чтобы показать их\n"),
            session_id=session_id
    )


    # intro = (
    # f"""Нашел подходящие манифесты. Необходимо заполнить параметры:
    # {placeholder_list}
    # """
    # )
    prompt = (
    f"""Ты - ассистент, который помогает пользователю сформировать манифесты для интеграции сервисов.
    Поприветствуй пользователя и скажи ему, что нашел необходимые манифесты, которые требуется заполнить: {placeholder_list}
    Перечисли все поля, которые нужны для заполнения, с кратким описанием их назначения в одно предложение.
    Помоги пользователю заполнить YAML-файл манифеста, в котором есть плейсхолдер `{{{{ ${first_placeholder} }}}}`.
    Объясни его назначение и задай вопрос, чтобы получить значение.
    """
    )
    llm_response = llm.invoke(prompt)
    ai_message = (getattr(llm_response, "content", "") or "").strip() or f"Введите значение для плейсхолдера {{{{first_placeholder}}}}:"

    state = SessionState(
        mode="MANIFEST",
        original_doc_text=doc_text,
        remaining_placeholders=placeholders[1:],
        filled_values={},
        current_placeholder=first_placeholder,
        source_file=doc_source
    )

    session_id = session_store.create(state, reuse_session_id)
    logger.info("[CHAT manifests] New session created: %s", session_id)

    return ChatResponse(
        intent="GET_MANIFESTS",
        action="NONE",
        suggested_payload=None,
        reply=ai_message,
        session_id=session_id
    )
