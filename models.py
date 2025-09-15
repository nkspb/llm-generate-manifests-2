from pydantic import BaseModel
from typing import Optional, Literal

# User request body in POST /get_manifests
class QueryRequest(BaseModel):
    query: str

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
