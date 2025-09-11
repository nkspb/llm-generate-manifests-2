import os
import logging
from langchain_gigachat import GigaChat, GigaChatEmbeddings
from langchain_chroma import Chroma
from data.documents import load_documents

logger = logging.getLogger(__name__)

VECTOR_DIR = "./database"

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

# Load a list of documents with metadata
docs = load_documents()

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
