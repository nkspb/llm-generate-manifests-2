from langchain_gigachat import GigaChat, GigaChatEmbeddings
from langchain_chroma import Chroma
from documents import load_documents
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from pydantic import BaseModel # For validating user's POST request body
from placeholder_utils import extract_placeholders, PLACEHOLDER_TYPES, is_placeholder_valid, fill_placeholders

import logging, os, uuid

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
    level=logging.DEBUG,
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

# Decide what the user wants to do and reroute accordingly
def llm_classify_intent(llm, text: str) -> str:
    pass

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

app = FastAPI()

# Async, so fastapi server can handle other things while waiting for response
# curl -X GET http://localhost:5000/health
@app.get("/health")
async def health_check():
    logger.info("Health check hit")
    return {"status": "ok"}

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
@app.post("/reply")
async def reply_to_llm(request: ReplyRequest):
    session_id = request.session_id
    user_input = request.message.strip()

    # Find the user session
    session = sessions.get(session_id)
    if not session:
        return PlainTextResponse(
            content="Сессия не найдена. Начните новую сессию.",
            status_code=404,
            media_type="text/plain"
        )
    
    # Get current placeholder
    current_placeholder = session["current_placeholder"]
    expected_type = PLACEHOLDER_TYPES.get(current_placeholder, "str")

    if not is_placeholder_valid(user_input, expected_type):
        return PlainTextResponse(
            content=f"`{{{{ ${current_placeholder }}}}}` ожидает значение с типом `{expected_type}`. Попробуйте снова: ",
            status_code=200,
            media_type="text/plain"
        )

    # If placeholder is valid, save its value to current session
    session["filled_values"][current_placeholder] = user_input

    # Check if there are remaining placeholders
    if session["remaining_placeholders"]:
        next_placeholder = session["remaining_placeholders"].pop(0)
        session["current_placeholder"] = next_placeholder

        # Ask user to fill in the next placeholder
        prompt = (
            f"""Ты - ассистент, который помогает пользователю сформировать манифесты для интеграции сервисов.
            Объясни значение плейсхолдера `{{{{ ${next_placeholder} }}}}` и попроси пользователя ввести значение."""
        )
        llm_response = llm.invoke(prompt)
        ai_message = llm_response.content.strip()

        return PlainTextResponse(content=ai_message + "\n")
    else:
        resulting_yaml = session["original_doc_text"]
        print(session["filled_values"])
        resulting_yaml = fill_placeholders(resulting_yaml, session["filled_values"])

        # After all manifests are filled in, delete the session
        del sessions[session_id]

        return PlainTextResponse(
            content=f"Все значения заполнены! Итоговые манифесты:\n\n + {resulting_yaml}",
            status_code=200,
            media_type="text/plain"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
