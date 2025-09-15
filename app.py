from langchain_gigachat import GigaChat, GigaChatEmbeddings
from langchain_chroma import Chroma
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from typing import Optional, Literal
from routes import chat, classify, health, get_manifests


from pydantic import BaseModel, ValidationError # For validating user's POST request body
from core.placeholder_engine import extract_placeholders, PLACEHOLDER_TYPES, is_placeholder_valid, fill_placeholders, format_placeholder_list
from core.session_manager import SessionStore

import logging, os, uuid, json

from core.config import llm, vector_store
from core.llm_utils import (
    llm_classify_intent,
    llm_assess_specificity,
    llm_detect_meta_intent,
    llm_rephrase_history
)

from core.placeholder_engine import handle_placeholder_reply
from models import ChatResponse, ChatRequest, QueryRequest, \
    ClassifyRequest, ClassifyResponse

# General logging settings
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

# In-memory session store
session_store = SessionStore()
# sessions = {}

for module in [chat, classify, get_manifests]:
    module.session_store = session_store
    module.llm = llm
    if hasattr(module, "vector_store"):
        module.vector_store = vector_store


app = FastAPI()
app.include_router(chat.router)
app.include_router(classify.router)
app.include_router(health.router)
app.include_router(get_manifests.router)
# If parameter is a Pydantic model, FastAPI reads it from request body

get_manifests.llm = llm
get_manifests.vector_store = vector_store
get_manifests.session_store = session_store
app.include_router(get_manifests.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
