from fastapi import APIRouter
from models import ChatRequest, ChatResponse, Intent
from core.llm_utils import llm_classify_intent, llm_rephrase_history, llm_assess_specificity, llm_detect_meta_intent, llm_detect_meta_in_scenario_mode, llm_detect_gibberish
from core.placeholder_engine import handle_placeholder_reply, extract_placeholders, fill_placeholders
# from core.manifest_flow import start_manifest_flow_from_query
from core.manifest_engine import start_manifest_flow_from_query
import uuid, logging
from core.placeholder_engine import format_placeholder_list
from core.session_manager import SessionStore, SessionState
router = APIRouter()
logger = logging.getLogger(__name__)

session_store: SessionStore = None # Should be imported or injected
vector_store = None # injected from app.py
llm = None

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    print(f"[CHAT] Received ChatRequest: {request}")
    print(f"[CHAT] Request.session_id: {request.session_id}")
    if request.session_id:
        # Retrieve session from SessionStore
        session = session_store.get(request.session_id)
        print(f"[CHAT] Looked up session_store.get({request.session_id}) -> {session}")

        print(f"Incoming session_id: {request.session_id}")
        print(f"Active sessions: {session_store.list_ids()}")

        if not session:
            logger.warning(f"Session {request.session_id} not found. Starting new session.")
            request.message = (
                f"Предыдущая сессия завершена. Начнем заново\n" + request.message
            )
            return await chat(ChatRequest(message=request.message, session_id=None))

        if session.mode == "ASK_SCENARIO":
            print("f[CHAT] Mode: ASK_SCENARIO, messages so far: {session.collected_messages}")
            # Detect meta intent early to handle unexpected user input
            meta_intent = llm_detect_meta_in_scenario_mode(llm, request.message)

            if meta_intent == "HELP":
                return ChatResponse(
                    intent=Intent.HELP,
                    action="NONE",
                    suggested_payload=None,
                    reply=(
                        "Вы сейчас на этапе уточнения запроса.\n"
                        "- Опишите, какую интеграцию вы хотите настроить.\n"
                        " - Или напишите 'отмена', чтобы завершить процесс."
                    ),
                    session_id=request.session_id
                )
            
            if meta_intent == "CANCEL":
                session_store.end(request.session_id)
                return ChatResponse(
                    intent=Intent.CANCEL,
                    action="NONE",
                    suggested_payload=None,
                    reply="Хорошо, отменяю процесс. Вы можете начать заново.",
                    session_id=None
                )
                
            # Proceed only if input is not a meta intent
            # Append message and update session
            if llm_detect_gibberish(llm, request.message):
                return ChatResponse(
                    intent=Intent.GET_MANIFESTS,
                    action="ASK_SCENARIO",
                    suggested_payload=None,
                    reply="Похоже, вы ввели случайный или непонятный текст. Попробуйте снова.",
                    session_id=request.session_id
                )

            session.collected_messages.append(request.message)

            try:
                rephrased = llm_rephrase_history(llm, session.collected_messages)
                print(f"[CHAT] collected_messages: {session.collected_messages}")
                print(f"[CHAT] rephrased: {rephrased}")

                assess = llm_assess_specificity(llm, rephrased)
            except Exception as e:
                logger.exception(f"Error while rephrasing or assessing specificity: {e}")
                return ChatResponse(
                    intent=Intent.CHAT,
                    action="NONE",
                    suggested_payload=None,
                    reply="Ошибка при обработке запроса. Попробуйте снова.",
                )

            if not assess["is_specific"]:
                bullet_questions = "\n".join(f"- " + q for q in assess["followups"])
                session_store.save(request.session_id, session)
                return ChatResponse(
                    intent=Intent.GET_MANIFESTS,
                    action="ASK_SCENARIO",
                    suggested_payload=None,
                    reply=("Спасибо. Нужны еще детали: " + bullet_questions),
                    session_id=request.session_id
                )

            query = assess["rephrased_query"] or rephrased.strip()
            logger.info("ASK_SCENARIO query: %s", query)
            return start_manifest_flow_from_query(query, vector_store, llm, session_store, reuse_session_id=request.session_id)

        if session.mode == "MANIFEST":
            print(f"[CHAT] Mode: MANIFEST, remaining placeholders: {session.remaining_placeholders}")
            # Pass session_store to placeholder handler
            text, done = handle_placeholder_reply(llm, request.session_id, session_store, request.message)
            if done:
                session_store.end(request.session_id)
            return ChatResponse(
                intent=Intent.GET_MANIFESTS,
                action="NONE",
                suggested_payload=None,
                reply=text,
                session_id=None if done else request.session_id
            )

        return ChatResponse(
            intent=Intent.CHAT,
            action="NONE",
            suggested_payload=None,
            reply="Сессия в неизвестном состоянии. Начните сначала."
        )
    try:
        label = llm_classify_intent(llm,request.message)
    except Exception as e:
        logger.exception(f"Error while classifying intent: {e}")
        return ChatResponse(
            intent=Intent.CHAT,
            action="NONE",
            suggested_payload=None,
            reply="Не удалось распознать ваш запрос. Попробуйте снова.",
        )

    if label == "GET_MANIFESTS":
        try:
            rephrased = llm_rephrase_history(llm, [request.message])
            assess = llm_assess_specificity(llm, rephrased)

        except Exception as e:
            logger.exception(f"Error while rephrasing or assessing specificity: {e}")
            return ChatResponse(
                intent=Intent.CHAT,
                action="NONE",
                suggested_payload=None,
                reply="Ошибка при обработке запроса. Попробуйте снова.",
            )
        logger.info("Hitting GET_MANIFESTS")
        logger.info("request.message = %s", request.message)
        logger.info("rephrased = %s", rephrased)
        logger.info(f"assess is_specific = {assess['is_specific']}")

        if not assess["is_specific"]:
            bullet_questions = "\n".join(f"- " + q for q in assess["followups"])
            session_id = str(uuid.uuid4())
            logger.info(f"GET_MANIFESTS: session_id = {session_id}")
            # Create new ASK_SCENARIO session in store
            session_store.create(SessionState(
                mode="ASK_SCENARIO",
                collected_messages=[request.message]
            ), reuse_session_id=session_id)
            print(f"[CHAT] ASK_SCENARIO session created: {session_id}")
            print(f"[CHAT] Stored session: {session_store.get(session_id)}")
            return ChatResponse(
                intent=Intent.GET_MANIFESTS,
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
        return start_manifest_flow_from_query(query, vector_store, llm, session_store)

    if label == "HELP":
        return ChatResponse(
            intent=Intent.HELP,
            action="NONE",
            suggested_payload=None,
            reply=(
                "Я помогаю сгенерировать YAML-манифесты для интеграции istio service mesh с другими сервисами"
            ),
        )

    try:
        response = llm.invoke(f"Ответь коротко и дружелюбно: {request.message}")
        text = (getattr(response, "content", "") or "").strip() or "Привет! Опишите, какой сценарий вас интересует."
    except Exception as e:
        logger.exception(f"Error while invoking LLM: {e}")
        text = "Привет! Опишите, какой сценарий вас интересует."

    return ChatResponse(
        intent=Intent.CHAT,
        action="NONE",
        suggested_payload=None,
        reply=text,
    )
