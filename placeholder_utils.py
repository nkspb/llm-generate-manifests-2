from langchain_gigachat import GigaChat, GigaChatEmbeddings
from langchain_chroma import Chroma
from documents import load_documents
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from typing import Optional, Literal
from routes import chat

from pydantic import BaseModel, ValidationError # For validating user's POST request body
from placeholder_utils import extract_placeholders, PLACEHOLDER_TYPES, is_placeholder_valid, fill_placeholders, format_placeholder_list

import logging, os, uuid, json

from core.llm_utils import (
    llm_classify_intent,
    llm_assess_specificity,
    llm_detect_meta_intent,
    llm_rephrase_history
)

from core.placeholder_engine import handle_placeholder_reply

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

logger = logging.getLogger(__name__)

# In-memory session store
sessions = {}

VECTOR_DIR = "./database"

# Load a list of documents with metadata
docs = load_documents()

# User request body in POST /get_manifests
class QueryRequest(BaseModel):
    query: str

# User request body in POST /reply
class ReplyRequest(BaseModel):
    session_id: str
    message: str # user's message

# User request body in POST /classify
class ClassifyRequest(BaseModel):
    query: str

# API response for POST /classify
class ClassifyResponse(BaseModel):
    intent: str

# User request body in POST /chat
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None # Optional session ID

# API response for POST /chat
class ChatResponse(BaseModel):
    intent: Literal["GET_MANIFESTS", "HELP", "CHAT"] # Conversation intents
    action: Literal["CALL_GET_MANIFESTS", "ASK_SCENARIO", "NONE"] # For API calls actions
    suggested_payload: Optional[dict] = None # A hint to user with what API call to make next
    reply: str # Human-readable reply to the user
    session_id: Optional[str] = None # Session ID for continuing the conversation

# Build vector store
def build_vector_store():
    """
    Build or rebuild the database
    Run on documents change
    """
    return Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=VECTOR_DIR,
        collection_metadata={"hnsw:space": "cosine"} 
    )

def load_vector_store():
    """
    Load the database
    Run on app startup
    """
    return Chroma(
        persist_directory=VECTOR_DIR,
        embedding_function=embeddings # embedding model for similarity search
    )

# Check if database exists and create it if not
if not os.path.exists(VECTOR_DIR):
    logger.info("База данных не найдена. Создаем новую...")
    os.makedirs(VECTOR_DIR)
    build_vector_store()

# Load the database with manifest templates
vector_store = load_vector_store()

for module in [chat]:
    module.sessions = sessions
    module.llm = llm
    if hasattr(module, "vector_store"):
        module.vector_store = vector_store

app = FastAPI()
app.include_router(chat.router)
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

    first_placeholder = placeholders[0]

    placeholder_list = format_placeholder_list(placeholders)
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
    # EXAMPLE OUTPUT: 
    # Found document: {'description': 'Манифесты для интеграции Istio Service Mesh с PostgreSQL, 
    # c использованием Service Entry', 'keywords': 'istio, service mesh, postgresql, база данных, с service entry', 
    # 'source': 'manifests/istio_postgres_se.yaml'}, raw_score = 9622.58203125
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

@app.post("/reply")
async def reply_to_llm(request: ReplyRequest):
    """
    Handle reply when asked for next placeholder value.
    If there are no more placeholders to fill, session is ended as done will become True.
    """
    text, done = handle_placeholder_reply(llm, request.session_id, request.message)
    if done:
        sessions.pop(request.session_id, None)
    return PlainTextResponse(content=text)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
