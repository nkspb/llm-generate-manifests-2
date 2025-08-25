from langchain_gigachat import GigaChat, GigaChatEmbeddings
from langchain_chroma import Chroma
from documents import load_documents
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from typing import Optional, Literal

from pydantic import BaseModel # For validating user's POST request body
from placeholder_utils import extract_placeholders, PLACEHOLDER_TYPES, is_placeholder_valid, fill_placeholders

import logging, os, uuid, json

os.environ["ANONYMIZED_TELEMETRY"] = "False"

llm = GigaChat(model="GigaChat-2-Max",
                base_url="https://X/v1",
                verify_ssl_certs=False, # Verify the server's SSL certificate
                cert_file='cert.pem', # Path to certificate to verify the server's identity
                key_file='key.pem') # Path to private key file to verify the client's identity

embeddings = GigaChatEmbeddings(model="EmbeddingsGigaR",
                base_url="https://X/v1",
                verify_ssl_certs=False,
                cert_file='cert.pem',
                key_file='key.pem')

# General logging settings
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Create dedicated logger for the app module
# Since it is run directly, __name__ is __main__
logger = logging.getLogger(__name__)

# In-memory session store
sessions = {}

# Database directory
VECTOR_DIR = "./database"

# Load a list of documents with metadata
docs = load_documents()

class QueryRequest(BaseModel):
    query: str

class ReplyRequest(BaseModel):
    session_id: str
    message: str # user's message

class ClassifyRequest(BaseModel):
    query: str

class ClassifyResponse(BaseModel):
    intent: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None # Optional session ID

class ChatResponse(BaseModel):
    intent: Literal["GET_MANIFESTS", "HELP", "CHAT"] 
    action: Literal["CALL_GET_MANIFESTS", "ASK_SCENARIO", "NONE"] # For API calls actions
    suggested_payload: Optional[dict] = None # Suggest what parameters to use next
    reply: str # Human-readable reply to the user
    session_id: Optional[str] = None # Session ID for continuing the conversation

# Build vector store
# hhsw - Hierarchical Navigable Small World (HNSW) algorithm
# space - how distances between vectors are calculated
def build_vector_store():
    """Run on documents change"""
    return Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=VECTOR_DIR,
        collection_metadata={"hnsw:space": "cosine"} 
    )

def load_vector_store():
    """Run on app startup"""
    return Chroma(
        persist_directory=VECTOR_DIR, # where the vector store is located
        embedding_function=embeddings # embedding model for similarity search
    )

# Check if database exists and create it if not
if not os.path.exists(VECTOR_DIR):
    logger.info("Database not found. Creating new one...")
    os.makedirs(VECTOR_DIR)
    build_vector_store()

vector_store = load_vector_store()

def llm_classify_intent(llm, text: str) -> str:
    """Определение цели запроса пользователя"""
    prompt = f""" Ты - классификатор запросов пользователя. Выбери намерение пользователя
    на основании его запроса:
    - GET_MANIFESTS: запросил манифесты, yaml, интеграцию, сценарий и т.п.
    - HELP: спрашивает, что ты умеешь, как работать с ботом, просит инструкцию
    - CHAT: любой другой запрос, который не требует манифестов

    Верни только одно слово: GET_MANIFESTS, HELP или CHAT

    Пользователь: {text}
    """

    try:
        response = llm.invoke(prompt)
        label = (getattr(response, "content", "") or "").strip().upper()
        logger.info(f"llm_classify_intent label: {label}")
        if label in ["GET_MANIFESTS", "HELP", "CHAT"]:
            return label
    except Exception as e:
        logger.error(f"Произошла ошибка при классификации запроса пользователя: {e}")
        return "CHAT"

def llm_assess_specificity(llm, user_text: str) -> dict:
    """
    Запрос к LLM для оценки, насколько запрос пользователя позволяет понять, какие манифесты генерировать
    """
    prompt = f""" Ты - ассистент, который помогает пользователю сформировать манифесты для интеграции сервисов.
    Определи, достаточно ли специфичен запрос пользователя, чтобы искать нужные манифесты (True/False).
    Если нет - предложи 2-4 коротких уточняющих вопроса.
    Если да - перефразируй запрос кратко и предметно.

    Верни строго JSON вида:
    {{
        "is_specific": true|false,
        "rephrased_query": "строка (может быть пустой)",
        "followups": ["вопрос1", "вопрос2", ...]
    }}

    Запрос: {user_text}
    """

    try:
        response = llm.invoke(prompt)
        raw = (getattr(response, "content", "") or "").strip()
        data = json.loads(raw)

        if not isinstance(data.get("followups", []), list):
            data["followups"] = []
        data["rephrased_query"] = data.get("rephrased_query") or ""
        data["is_specific"] = bool(data.get("is_specific", False))
        logger.info(f"data['is_specific']: {data['is_specific']}")
        return data
    except Exception as e:
        return {
            "is_specific": False,
            "rephrased_query": "",
            "followups": [
                "С каким сервисом вы хотите интегрировать istio service mesh?",
            ]
        }

app = FastAPI()

# Async, so fastapi server can handle other things while waiting for response
# curl -X GET http://localhost:5000/health
@app.get("/health")
async def health_check():
    logger.info("Health check hit")
    return {"status": "ok"}

# curl -X POST http://localhost:5000/classify -H "Content-Type: application/json" -d '{"query": "Что ты умеешь?"}'
@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    label = llm_classify_intent(llm, request.query)
    print(label)
    return ClassifyResponse(intent=label)

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
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
            combined = " ".join(session["collected_messages"])
            assess = llm_assess_specificity(llm, combined)
            if not assess["is_specific"]:
                bullet_questions = "\n".join(f"- " + q for q in assess["followups"])
                return ChatResponse(
                    intent="GET_MANIFESTS",
                    action="ASK_SCENARIO",
                    suggested_payload=None,
                    reply=("Спасибо. Нужны еще детали: " + bullet_questions),
                    session_id=request.session_id
                )
            query = assess["rephrased_query"] or combined
            return _start_manifest_flow_from_query(query, reuse_session_id=request.session_id)

            if mode == "MANIFEST":
                text, done = _handle_placeholder_reply(request.session_id, request.message)
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
                reply="Сессия в неизвестном состоянии. Начните, пожалуйста, сначала."
            )

    label = llm_classify_intent(llm,request.message)

    if label == "GET_MANIFESTS":
        assess = llm_assess_specificity(llm, request.message)
        print(f"assess = {assess}")
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

        query = assess["rephrased_query"] or combined
        return _start_manifest_flow_from_query(query)

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

def _start_manifest_flow_from_query(query: str, reuse_session_id: Optional[str] = None) -> "ChatResponse":
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
        return ChatResponse(
            intent="GET_MANIFESTS",
            action="NONE",
            suggested_payload=None,
            reply=("Манифест найден. Необходимо заполнить все поля. Отправьте render, чтобы показать их\n"),
            session_id=session_id
        )

    first_placeholder = placeholders[0]
    prompt = (
    f"""Ты - ассистент, который помогает пользователю сформировать манифесты для интеграции сервисов.
    Поприветствуй пользователя и скажи ему, что нашел необходимые манифесты.
    Помоги пользователю заполнить YAML-файл манифеста, в котором есть плейсхолдер `{{{{ ${first_placeholder} }}}}`.
    Объясни его назначение и задай вопрос, чтобы получить значение.
    """
    )
    llm_response = llm.invoke(prompt)
    ai_message = (getattr(llm_response, "content", "") or "").strip() or f"Введите значение для плейсхолдера {{{{first_placeholder}}}}:"

    sessions[session_id] = {
        "mode": "MANIFEST",
        "original_doc_text": doc_text,
        "remaining_placeholders": placeholders[1:],
        "filled_values": {},
        "current_placeholder": first_placeholder,
        "source_file": doc_source
    }
    logger.info("[CHAT manifests] New session created: %s", session_id)

    return ChatResponse(
        intent="GET_MANIFESTS",
        action="NONE",
        suggested_payload=None,
        reply=ai_message,
        session_id=session_id
    )

def _handle_placeholder_reply(session_id: str, user_input: str) -> tuple[str, bool]:
    """Shared logic for filling placeholders.
    Returns (reply_text, done).
    If done=True, session is complete and manifests are rendered"""

    # Search for current active session
    session = sessions.get(session_id)
    if not session:
        return ("Сессия не найдена. Начните новую сессию.", True)

    user_input = user_input.strip()
    current_placeholder = session.get("current_placeholder")

    # If there are no more placeholders, make substitutions and render manifests
    if current_placeholder is None and not session["remaining_placeholders"]:
        rendered = fill_placeholders(session["original_doc_text"], session["filled_values"])
        return ("Все значения заполнены! Итоговые манифесты:\n\n" + rendered, True)

    expected_type = PLACEHOLDER_TYPES.get(current_placeholder, "str")
    if not is_placeholder_valid(user_input, expected_type):
        return (f"`{{{{ ${current_placeholder} }}}}` ожидает тип `{expected_type}. Попробуйте снова:", False)

    # Save the value of current placeholder
    session["filled_values"][current_placeholder] = user_input

    if session["remaining_placeholders"]:
        next_placeholder = session["remaining_placeholders"].pop(0)
        session["current_placeholder"] = next_placeholder

        try:
            prompt = f"Объясни значение плейсхолдера `{{{{ ${next_placeholder} }}}}` и попроси пользователя ввести значение."
            response = llm.invoke(prompt)
            text = (getattr(response, "content", "") or "").strip()
        except Exception:
            text = f"Введите значение для ${{{next_placeholder}}}:"
        return (text, False)
    
    rendered = fill_placeholders(session["original_doc_text"], session["filled_values"])
    return ("Все значения заполнены! Итоговые манифесты:\n\n" + rendered, True)



# If parameter is a Pydantic model, FastAPI reads it from request body
# curl -X POST http://localhost:5000/get_manifests -H "Content-Type: application/json" -d '{"query": "Верни только темплейты для интеграции с postgress"}'
@app.post("/get_manifests")
async def get_manifests(request: QueryRequest, fastapi_request: Request):
    # Get client IP for logging
    client_ip = fastapi_request.client.host if fastapi_request.client else "Client IP Unknown"
    # Get query from request body
    query = request.query
    # Search for most relevant yaml document
    try:
        # _with_score returns tuple (document, score), so that we could filter out non-relevant documents
        results = vector_store.similarity_search_with_score(query, k=1)
    except Exception as e:
        logger.error(f"Произошла ошибка при поиске по векторной базе: {e}")
        return PlainTextResponse(
            content="Произошла ошибка при поиске манифестов. Попробуйте другой запрос.", 
            status_code=500,
            media_type="text/plain"
        )
    
    matched_doc, raw_score = results[0]
    # EXAMPLE OUTPUT: Found document: {'description': 'Манифесты для интеграции Istio Service Mesh с PostgreSQL, c использованием Service Entry', 'keywords': 'istio, service mesh, postgresql, база данных, с service entry', 'source': 'manifests/istio_postgres_se.yaml'}, raw_score = 9622.58203125
    logger.debug("Found document: %s, raw_score = %s", matched_doc.metadata, raw_score)

    doc_text = matched_doc.page_content
    logger.debug("Document text: %s", doc_text)
    # .get(key, default) - if key is not found, return default
    doc_source = matched_doc.metadata.get("source", "source unknown")

    # Chroma returns Cosine distance, not similarity
    # So we need to calculate it ourselves.
    similarity = 1 - raw_score

    SIMILARITY_THRESHOLD = 0.4
    # Check if document found is relevant enough
    if similarity < SIMILARITY_THRESHOLD:
        return PlainTextResponse(
            content="К сожалению, не удалось найти подходящий манифест. Попробуйте другой запрос.\n",
            status_code=404,
            media_type="text/plain"
        )

    # Extract placeholders from document for user to fill in
    placeholders = extract_placeholders(doc_text)

    # Start asking from first placeholder
    first_placeholder = placeholders[0]

    prompt = (
        f"""Ты - ассистент, который помогает пользователю сформировать манифесты для интеграции сервисов.
        Поприветствуй пользователя и скажи ему, что нашел необходимые манифесты.
        Помоги пользователю заполнить YAML-файл манифеста, в котором есть плейсхолдер `{{{{ ${first_placeholder} }}}}`.
        Объясни его назначение и задай вопрос, чтобы получить значение.
        """
    )

    llm_response = llm.invoke(prompt)
    logger.info("LLM request invoked")
    # Check if response is not empty
    if not llm_response and not getattr(llm_response, "content", None):
        logger.info(f"Raw LLM response: ${llm_response}")
        return PlainTextResponse("Ошибка получения ответа от LLM. Попробуйте другой запрос.", 
        status_code=500, 
        media_type="text/plain"
        )

    logger.info(f"Raw LLM response: ${llm_response}")

    # Create session ID to associate with the current user
    session_id = str(uuid.uuid4())
    ai_message = llm_response.content.strip() # Extract message from LLM response

    # Store information about current new session
    sessions[session_id] = {
        "original_doc_text": doc_text,
        "remaining_placeholders": placeholders[1:],
        "filled_values": {},
        "current_placeholder": first_placeholder,
        "source_file": doc_source
    }
    logger.info(f"New session created: {session_id}")

    return PlainTextResponse(
        content=f"session_id `{session_id}`\n{ai_message}\n",
        headers={
            "App-Session-ID": session_id,
            "App-Source-File": doc_source
        },
        media_type="text/plain"
    )

# curl -X POST http://localhost:5000/reply -H "Content-Type: application/json" -d '{"message": "value", "session_id": "123"}
# @app.post("/reply")
# async def reply_to_llm(request: ReplyRequest):
#     session_id = request.session_id
#     user_input = request.message.strip()

#     # Find the user session
#     session = sessions.get(session_id)
#     if not session:
#         return PlainTextResponse(
#             content="Сессия не найдена. Начните новую сессию.",
#             status_code=404,
#             media_type="text/plain"
#         )
    
#     # Get current placeholder
#     current_placeholder = session["current_placeholder"]
#     expected_type = PLACEHOLDER_TYPES.get(current_placeholder, "str")

#     if not is_placeholder_valid(user_input, expected_type):
#         return PlainTextResponse(
#             content=f"`{{{{ ${current_placeholder }}}}}` ожидает значение с типом `{expected_type}`. Попробуйте снова: ",
#             status_code=200,
#             media_type="text/plain"
#         )

#     # If placeholder is valid, save its value to current session
#     session["filled_values"][current_placeholder] = user_input

#     # Check if there are remaining placeholders
#     if session["remaining_placeholders"]:
#         next_placeholder = session["remaining_placeholders"].pop(0)
#         session["current_placeholder"] = next_placeholder

#         # Ask user to fill in the next placeholder
#         prompt = (
#             f"""Ты - ассистент, который помогает пользователю сформировать манифесты для интеграции сервисов.
#             Объясни значение плейсхолдера `{{{{ ${next_placeholder} }}}}` и попроси пользователя ввести значение."""
#         )
#         llm_response = llm.invoke(prompt)
#         ai_message = llm_response.content.strip()

#         return PlainTextResponse(content=ai_message + "\n")
#     else:
#         resulting_yaml = session["original_doc_text"]
#         print(session["filled_values"])
#         resulting_yaml = fill_placeholders(resulting_yaml, session["filled_values"])

#         # After all manifests are filled in, delete the session
#         # del sessions[session_id]

#         return PlainTextResponse(
#             content=f"Все значения заполнены! Итоговые манифесты:\n\n + {resulting_yaml}",
#             status_code=200,
#             media_type="text/plain"
#         )

@app.post("/reply")
async def reply_to_llm(request: ReplyRequest):
    text, done = _handle_placeholder_reply(request.session_id, request.message)
    if done:
        sessions.pop(request.session_id, None)
    return PlainTextResponse(content=text)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
