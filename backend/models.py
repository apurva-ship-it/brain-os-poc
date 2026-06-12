from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TierResult(BaseModel):
    tier: str
    label: str
    active: bool
    hit: bool
    contributions: list[dict] = []
    token_estimate: int = 0
    latency_ms: float = 0.0


class GuardrailResult(TierResult):
    blocked: bool = False
    violations: list[dict] = []
    rules_checked: int = 0


class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: str
    brand_id: Optional[str] = None
    market: Optional[str] = None
    target_language: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    blocked: bool = False
    session_id: str
    memory_trace: dict
    context_summary: dict


class MemoryEntry(BaseModel):
    id: str
    category: str
    key: str
    value: str
    scope: str
    scope_id: str
    created_at: str
    session_id: Optional[str] = None


class AddMemoryRequest(BaseModel):
    user_id: str
    key: str
    value: str
    category: str = "user_fact"
    brand_id: Optional[str] = None
    market: Optional[str] = None


class SessionInfo(BaseModel):
    session_id: str
    user_id: str
    brand_id: Optional[str] = None
    market: Optional[str] = None
    turn_count: int = 0
    created_at: str
    last_active: str


class DocumentIngestRequest(BaseModel):
    brand_id: str
    dataset: str = "brand_knowledge"
    description: Optional[str] = None
