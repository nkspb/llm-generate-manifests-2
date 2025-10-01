from __future__ import annotations # Treat all type annotations in this file as strings behind the scenes, to avoid reference problems
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field # Function used to provide extra metadata, constraints, and validation rules to the fields of your BaseModel
import uuid

ModeType = Literal["ASK_SCENARIO", "MANIFEST"]

class SessionState(BaseModel):
    mode: ModeType

    # ASK_SCENARIO
    collected_messages: List[str] = Field(default_factory=list)
    
    # MANIFEST
    source_file: Optional[str] = None
    original_doc_text: Optional[str] = None
    docs_texts: Optional[List[str]] = None
    
    remaining_placeholders: List[str] = Field(default_factory=list)
    filled_values: Dict[str, str] = Field(default_factory=dict)
    current_placeholder: Optional[str] = None

class SessionStore:
    """Simple in-memory store (single-process)."""
    
    # _mem - private variable, Dict[str, SessionState] is a type hint
    # meaning dictionary with str keys and values of type SessionState
    def __init__(self): # Called when new instance of SessionStore is created
        self._mem: Dict[str, SessionState] = {} 

    # This signature says that reuse_session_id should be either provided string, or None will be returned as Default
    # It is just a type hint not affecting program runtime
    def create(self, state: SessionState, reuse_session_id: Optional[str] = None) -> str:
        # If session is reused, essentially update its state
        if reuse_session_id:
            self._mem[reuse_session_id] = state
            return reuse_session_id
        # If session is not reused, return a new session
        sid = str(uuid.uuid4())
        self._mem[sid] = state
        return sid
        
    # Retrieve session data for given session_id
    # -> Optional[SessionState] - return either a SessionState object 
    # if session_id is found or None
    def get(self, session_id: str) -> Optional[SessionState]:
        return self._mem.get(session_id)

    def save(self, session_id: str, state: SessionState) -> None:
        self._mem[session_id] = state

    def end(self, session_id: str) -> None:
        self._mem.pop(session_id, None)

    def list_ids(self) -> List[str]:
        """Return a list of all active session IDs (for debugging purposes)."""
        return list(self._mem.keys())

    def clear(self) -> None:
        """Clear a list of all active session IDs (for debugging purposes)."""
        self._mem.clear()
