from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, HTTPException
from models import AddMemoryRequest
from services import p2_session, p3_episodic, p4_knowledge, p5_translation, p1_guardrails

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/user/{user_id}")
async def get_user_memory(user_id: str):
    memories = p3_episodic.get_user_memories(user_id)
    return {"user_id": user_id, "memories": memories, "count": len(memories)}


@router.get("/brand/{brand_id}")
async def get_brand_memory(brand_id: str, market: Optional[str] = None):
    memories = p3_episodic.get_brand_memories(brand_id, market)
    return {"brand_id": brand_id, "market": market, "memories": memories, "count": len(memories)}


@router.post("/add")
async def add_memory(req: AddMemoryRequest):
    if req.brand_id:
        mid = p3_episodic.add_brand_memory(req.brand_id, req.key, req.value, req.market, req.category)
        return {"id": mid, "scope": "brand", "brand_id": req.brand_id}
    else:
        mid = p3_episodic.add_user_memory(req.user_id, req.key, req.value, req.category)
        return {"id": mid, "scope": "user", "user_id": req.user_id}


@router.delete("/entry/{memory_id}")
async def delete_memory(memory_id: str):
    ok = p3_episodic.delete_memory(memory_id)
    return {"deleted": ok, "id": memory_id}


@router.get("/session/{session_id}")
async def get_session_memory(session_id: str):
    session = p2_session.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session


@router.get("/sessions/all")
async def list_all_sessions():
    return p2_session.get_all_sessions()


@router.get("/knowledge/stats")
async def knowledge_stats():
    return p4_knowledge.get_stats()


@router.get("/translation/entries")
async def translation_entries():
    return p5_translation.get_all_entries()


@router.get("/guardrails/{brand_id}")
async def get_guardrails(brand_id: str):
    rules = p1_guardrails.get_rules_for_brand(brand_id)
    return {"brand_id": brand_id, "rules": rules, "count": len(rules)}


@router.get("/inspector")
async def full_inspector(user_id: str, brand_id: Optional[str] = None, market: Optional[str] = None):
    """Full memory state for the inspector panel in UI."""
    user_mems = p3_episodic.get_user_memories(user_id)
    brand_mems = p3_episodic.get_brand_memories(brand_id or "", market) if brand_id else []
    sessions = p2_session.list_sessions(user_id)
    knowledge_stats = p4_knowledge.get_stats()
    tm_entries = p5_translation.get_all_entries()
    guardrails = p1_guardrails.get_rules_for_brand(brand_id)

    return {
        "P1_guardrails": {"rules": guardrails, "count": len(guardrails)},
        "P2_sessions": {"sessions": [s.model_dump() for s in sessions], "count": len(sessions)},
        "P3_user_memory": {"memories": user_mems, "count": len(user_mems)},
        "P3_brand_memory": {"memories": brand_mems, "count": len(brand_mems), "brand": brand_id, "market": market},
        "P4_knowledge": knowledge_stats,
        "P5_translation": {"languages": list(tm_entries.keys()), "term_counts": {k: len(v) for k, v in tm_entries.items()}},
    }
