"""
P2 — Session Memory (Short-term / Working Memory)
Scope: THIS session only. Cleared when session ends or times out.
Layman analogy: sticky note on your desk — useful now, thrown away when you leave.
Use cases:
  - "I'm working in formal tone for this session"
  - "I'm drafting for Brand X in US market today"
  - Current conversation turns
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from models import TierResult, SessionInfo


# In-memory store — intentionally NOT persisted. Dies with process.
_sessions: dict[str, dict] = {}
_SESSION_TTL = 1800  # 30 minutes


def create_session(user_id: str, brand_id: str | None = None, market: str | None = None) -> str:
    session_id = str(uuid.uuid4())[:8]
    _sessions[session_id] = {
        "session_id": session_id,
        "user_id": user_id,
        "brand_id": brand_id,
        "market": market,
        "turns": [],
        "preferences": {},
        "created_at": datetime.now().isoformat(),
        "last_active": time.time(),
    }
    return session_id


def get_session(session_id: str) -> dict | None:
    session = _sessions.get(session_id)
    if not session:
        return None
    # Check TTL
    if time.time() - session["last_active"] > _SESSION_TTL:
        del _sessions[session_id]
        return None
    return session


def add_turn(session_id: str, role: str, content: str) -> None:
    session = _sessions.get(session_id)
    if not session:
        return
    session["turns"].append({"role": role, "content": content, "ts": datetime.now().isoformat()})
    session["last_active"] = time.time()
    # Keep only last 10 turns in session
    if len(session["turns"]) > 10:
        session["turns"] = session["turns"][-10:]


def set_preference(session_id: str, key: str, value: str) -> None:
    session = _sessions.get(session_id)
    if session:
        session["preferences"][key] = value
        session["last_active"] = time.time()


def update_context(session_id: str, brand_id: str | None = None, market: str | None = None) -> None:
    session = _sessions.get(session_id)
    if not session:
        return
    if brand_id:
        session["brand_id"] = brand_id
    if market:
        session["market"] = market


def retrieve(session_id: str) -> TierResult:
    import time as _time
    start = _time.monotonic()
    session = get_session(session_id)

    if not session:
        return TierResult(
            tier="P2", label="Session Memory", active=False, hit=False,
            contributions=[{"type": "status", "message": "No active session — create one first"}],
            token_estimate=0, latency_ms=0,
        )

    contributions = []
    if session.get("brand_id"):
        contributions.append({"type": "brand_context", "key": "brand", "value": session["brand_id"]})
    if session.get("market"):
        contributions.append({"type": "market_context", "key": "market", "value": session["market"]})
    for k, v in session.get("preferences", {}).items():
        contributions.append({"type": "session_preference", "key": k, "value": v})

    turn_count = len(session.get("turns", []))
    if turn_count:
        contributions.append({"type": "conversation_history", "key": "turns", "value": f"{turn_count} turns in this session"})
    else:
        contributions.append({"type": "status", "message": "New session — no prior turns"})

    token_est = 80 + turn_count * 40 + len(contributions) * 15
    latency = (_time.monotonic() - start) * 1000

    return TierResult(
        tier="P2", label="Session Memory", active=True, hit=bool(contributions),
        contributions=contributions, token_estimate=token_est, latency_ms=round(latency, 1),
    )


def get_conversation_turns(session_id: str) -> list[dict]:
    session = _sessions.get(session_id)
    if not session:
        return []
    return [{"role": t["role"], "content": t["content"]} for t in session.get("turns", [])]


def list_sessions(user_id: str) -> list[SessionInfo]:
    result = []
    for sid, s in _sessions.items():
        if s.get("user_id") == user_id:
            result.append(SessionInfo(
                session_id=sid,
                user_id=s["user_id"],
                brand_id=s.get("brand_id"),
                market=s.get("market"),
                turn_count=len(s.get("turns", [])),
                created_at=s["created_at"],
                last_active=datetime.fromtimestamp(s["last_active"]).isoformat(),
            ))
    return result


def get_all_sessions() -> list[dict]:
    return [
        {
            "session_id": sid,
            "user_id": s["user_id"],
            "brand_id": s.get("brand_id"),
            "market": s.get("market"),
            "turn_count": len(s.get("turns", [])),
            "preferences": s.get("preferences", {}),
            "created_at": s["created_at"],
        }
        for sid, s in _sessions.items()
    ]
