from fastapi import APIRouter
from models import ChatRequest, ChatResponse
from core.llm_utils import llm_classify_intent, llm_rephrase_history, llm_assess_specificity
from core.placeholder_engine import handle_placeholder_reply, extract_placeholders, fill_placeholders
from core.manifest_flow import start_manifest_flow_from_query
import uuid, logging
from placeholder_utils import format_placeholder_list
router = APIRouter()
logger = logging.getLogger(__name__)

sessions = {} # Should ideally be imported or injected
vector_store = None # Must be injected from app.py
llm = None # Same here

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    global sessions

    if request.session_id:
        session = sessions.get(request.session_id)
        if not session:
            return ChatResponse(
                intent="CHAT",
                action="NONE",
                suggested_payload=None,
                reply=("Сессия не найдена или завершена. Попробуйте начать сначала.")
            )

        mode = session.get("mode")

        if mode == "ASK_SCENARIO":
            session["collected_messages"].append(request.message)
            logger.info(f"collected_messages: {session['collected_messages']}")
            rephrased = llm_rephrase_history(llm, session["collected_messages"])
            assess = llm_assess_specificity(llm, rephrased)

            if not assess["is_specific"]:
                bullet_questions = "\n".join(f"- " + q for q in assess["followups"])
                return ChatResponse(
                    intent="GET_MANIFESTS",
                    action="ASK_SCENARIO",
                    suggested_payload=None,
                    reply=("Спасибо. Нужны еще детали: " + bullet_questions),
                    session_id=request.session_id
                )
            query = assess["rephrased_query"] or rephrased.strip()
            logger.info("ASK_SCENARIO query: %s", query)
            return start_manifest_flow_from_query(query, vector_store, llm, sessions, reuse_session_id=request.session_id)

        if mode == "MANIFEST":
            text, done = handle_placeholder_reply(llm, request.session_id, sessions, request.message)
            if done:
                sessions.pop(request.session_id, None)
            return ChatResponse(
                intent="GET_MANIFESTS",
                action="NONE",
                suggested_payload=None,
                reply=text,
                session_id=None if done else request.session_id
            )

        return ChatResponse(
            intent="CHAT",
            action="NONE",
            suggested_payload=None,
            reply="Сессия в неизвестном состоянии. Начните сначала."
        )

    label = llm_classify_intent(llm,request.message)

    if label == "GET_MANIFESTS":
        rephrased = llm_rephrase_history(llm, [request.message])
        logger.info("Hitting GET_MANIFESTS")
        logger.info("request.message = %s", request.message)
        logger.info("rephrased = %s", rephrased)
        assess = llm_assess_specificity(llm, rephrased)
        print(f"assess rephrased = {assess['is_specific']}")

        if not assess["is_specific"]:
            bullet_questions = "\n".join(f"- " + q for q in assess["followups"])
            session_id = str(uuid.uuid4())
            print(f"GET_MANIFESTS: session_id = {session_id}")
            sessions[session_id] = {
                "mode": "ASK_SCENARIO",
                "collected_messages": [request.message]
            }
            return ChatResponse(
                intent="GET_MANIFESTS",
                action="ASK_SCENARIO",
                suggested_payload=None,
                reply=(
                    "Уточните, пожалуйста, какую интеграцию вы хотите настроить:\n"
                    f"{bullet_questions}"
                ),
                session_id=session_id
            )

        query = rephrased.strip()

        logger.info("GET_MANIFESTS: query = %s", query)
        return start_manifest_flow_from_query(query, vector_store, llm, sessions)

    if label == "HELP":
        return ChatResponse(
            intent=label,
            action="NONE",
            suggested_payload=None,
            reply=(
                "Я помогаю сгенерировать YAML-манифесты для интеграции istio service mesh с другими сервисами"
            ),
        )

    try:
        response = llm.invoke(f"Ответь коротко и дружелюбно: {request.message}")
        text = (getattr(response, "content", "") or "").strip() or "Привет! Опишите, какой сценарий вас интересует."
    except Exception:
        text = "Привет! Опишите, какой сценарий вас интересует."
    return ChatResponse(
        intent="CHAT",
        action="NONE",
        suggested_payload=None,
        reply=text,
    )
