"""
P3 — Episodic Memory (Entity Memory)
Scope: Persistent across sessions. User-scoped, Brand-scoped, or Market-scoped.
Backed by SQLite (file-persisted — survives process restart).

Layman analogy: your brain remembering who each person is, what each client needs,
and what rules apply in each market. Doesn't reset when you open a new tab.

Use cases:
  - "My name is Apurva" → user memory → present in ALL future sessions
  - "MLR rejected 'significantly reduces' for HUMIRA US" → brand+market memory
  - "For Germany, use 'gut verträglich' for tolerability" → market-specific rule
  - "Dr. Mehta prefers clinical evidence-first framing" → user preference
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from models import TierResult


_DB_PATH: Path | None = None
_conn: sqlite3.Connection | None = None

KNOWN_BRANDS = {"OZEMPIC", "KEYTRUDA", "HUMIRA"}
_MARKET_ALIASES = {
    "US": ["US", "UNITED STATES", "USA", "AMERICA"],
    "DE": ["GERMANY", "GERMAN", " DE ", "DEUTSCH"],
    "IN": ["INDIA", "INDIAN", " IN "],
    "JP": ["JAPAN", "JAPANESE", " JP "],
    "EU": ["EUROPE", "EUROPEAN", " EU "],
}


def _detect_brand_market(message: str) -> tuple:
    """Return (brand_id, market) detected from free text, or (None, None)."""
    msg = " " + message.upper() + " "
    brand = next((b for b in KNOWN_BRANDS if b in msg), None)
    market = None
    for mkt, aliases in _MARKET_ALIASES.items():
        if any(a in msg for a in aliases):
            market = mkt
            break
    return brand, market


def init(data_dir: Path) -> None:
    import os
    global _DB_PATH, _conn
    # On Vercel the source tree is read-only — use /tmp instead
    if os.environ.get("VERCEL"):
        _DB_PATH = Path("/tmp/episodic.db")
    else:
        _DB_PATH = data_dir / "memory" / "episodic.db"
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,          -- 'user' | 'brand' | 'brand_market'
            scope_id TEXT NOT NULL,       -- user_id, brand_id, or brand_id:market
            category TEXT NOT NULL,       -- 'user_fact' | 'user_preference' | 'mlr_feedback' | 'market_rule' | 'brand_fact'
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT DEFAULT 'user',   -- 'user' | 'system' | 'mlr'
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_scope ON memories(scope, scope_id)")
    _conn.commit()


def _get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("P3 not initialized — call init() first")
    return _conn


def add(
    scope: str,
    scope_id: str,
    category: str,
    key: str,
    value: str,
    source: str = "user",
) -> str:
    conn = _get_conn()
    # Upsert: if same scope+scope_id+key exists, update it (contradiction resolution)
    existing = conn.execute(
        "SELECT id FROM memories WHERE scope=? AND scope_id=? AND key=?",
        (scope, scope_id, key),
    ).fetchone()

    now = datetime.now().isoformat()
    if existing:
        conn.execute(
            "UPDATE memories SET value=?, category=?, updated_at=?, source=? WHERE id=?",
            (value, category, now, source, existing["id"]),
        )
        conn.commit()
        return existing["id"]
    else:
        mid = str(uuid.uuid4())[:12]
        conn.execute(
            "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, scope, scope_id, category, key, value, source, now, now),
        )
        conn.commit()
        return mid


def add_user_memory(user_id: str, key: str, value: str, category: str = "user_fact") -> str:
    return add("user", user_id, category, key, value)


def add_brand_memory(brand_id: str, key: str, value: str, market: str | None = None, category: str = "brand_fact") -> str:
    scope_id = f"{brand_id}:{market}" if market else brand_id
    scope = "brand_market" if market else "brand"
    return add(scope, scope_id, category, key, value, source="system")


def get_user_memories(user_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM memories WHERE scope='user' AND scope_id=? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_brand_memories(brand_id: str, market: str | None = None) -> list[dict]:
    conn = _get_conn()
    results = []
    # Always include brand-level memories
    rows = conn.execute(
        "SELECT * FROM memories WHERE scope='brand' AND scope_id=?",
        (brand_id,),
    ).fetchall()
    results.extend([dict(r) for r in rows])
    # Add market-specific if provided
    if market:
        scope_id = f"{brand_id}:{market}"
        rows2 = conn.execute(
            "SELECT * FROM memories WHERE scope='brand_market' AND scope_id=?",
            (scope_id,),
        ).fetchall()
        results.extend([dict(r) for r in rows2])
    return results


def delete_memory(memory_id: str) -> bool:
    conn = _get_conn()
    conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
    conn.commit()
    return True


def retrieve(user_id: str, brand_id: str | None, market: str | None, query: str) -> TierResult:
    start = time.monotonic()
    contributions = []

    # Auto-detect brand/market from query when not explicitly set
    detected_brand, detected_market = _detect_brand_market(query)
    effective_brand = brand_id or detected_brand
    effective_market = market or detected_market

    # 1. User memories (cross-session)
    user_mems = get_user_memories(user_id)
    if user_mems:
        for m in user_mems[:5]:
            contributions.append({
                "type": "user_memory",
                "key": m["key"],
                "value": m["value"],
                "category": m["category"],
                "scope": "all sessions",
            })

    # 2. Brand memories
    if effective_brand:
        brand_mems = get_brand_memories(effective_brand, effective_market)
        for m in brand_mems[:5]:
            contributions.append({
                "type": "brand_memory" if m["scope"] == "brand" else "market_memory",
                "key": m["key"],
                "value": m["value"],
                "category": m["category"],
                "scope": f"{effective_brand}" + (f" / {effective_market}" if effective_market and m["scope"] == "brand_market" else ""),
            })

    if not contributions:
        contributions.append({
            "type": "status",
            "message": "No episodic memories yet for this user/brand — memories build up as you chat",
        })

    token_est = len(contributions) * 35
    latency = (time.monotonic() - start) * 1000

    return TierResult(
        tier="P3",
        label="Episodic Memory",
        active=True,
        hit=bool([c for c in contributions if c.get("type") != "status"]),
        contributions=contributions,
        token_estimate=token_est,
        latency_ms=round(latency, 1),
    )


def extract_and_store_facts(message: str, user_id: str, brand_id: str | None, market: str | None, llm_client) -> list[dict]:
    """Use LLM to extract storable facts from user message."""
    # Auto-detect brand/market from message text when not explicitly selected
    detected_brand, detected_market = _detect_brand_market(message)
    effective_brand = brand_id or detected_brand
    effective_market = market or detected_market

    brand_context = f"Brand in context: {effective_brand}" if effective_brand else "No specific brand selected"
    market_context = f"Market in context: {effective_market}" if effective_market else "No specific market"

    prompt = f"""You are a memory extraction system for a pharma AI platform. Extract facts worth remembering persistently from this user message.

{brand_context}
{market_context}
User message: "{message}"

Extract facts in these categories (only clear, explicit statements — not assumptions):
- user_fact: facts about the user (name, role, organization)
- user_preference: preferences (tone, format, language, style)
- mlr_feedback: MLR/regulatory decisions — rejected phrases, approved phrases, flagged content
- market_rule: market-specific rules or guidelines for a brand
- brand_fact: factual information about a specific drug/brand

For mlr_feedback and market_rule, set scope to "brand_market" if a market is mentioned, else "brand".
Use the brand from context if the message doesn't name one explicitly.

Return JSON only:
{{
  "facts": [
    {{"category": "mlr_feedback", "key": "rejected_phrase_significantly_reduces", "value": "MLR rejected 'significantly reduces' — use 'reduces' instead", "scope": "brand_market"}},
    {{"category": "user_fact", "key": "user_name", "value": "Apurva", "scope": "user"}}
  ]
}}

Return {{"facts": []}} if nothing worth remembering persistently."""

    try:
        response = llm_client.chat.completions.create(
            model="anthropic/claude-3-haiku",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content.strip()
        start_idx = text.find("{")
        end_idx = text.rfind("}") + 1
        if start_idx >= 0:
            data = json.loads(text[start_idx:end_idx])
            facts = data.get("facts", [])
            stored = []
            for f in facts:
                if f.get("scope") == "user":
                    mid = add_user_memory(user_id, f["key"], f["value"], f["category"])
                    stored.append({**f, "id": mid, "stored": True})
                elif f.get("scope") in ("brand", "brand_market") and effective_brand:
                    use_market = effective_market if f["scope"] == "brand_market" else None
                    mid = add_brand_memory(effective_brand, f["key"], f["value"], use_market, f["category"])
                    stored.append({**f, "id": mid, "stored": True, "brand": effective_brand, "market": use_market})
            return stored
    except Exception:
        pass
    return []


def seed_market_rules(data_dir: Path) -> None:
    """Seed P3 with market rules from JSON at startup."""
    rules_file = data_dir / "p3_market_rules.json"
    if not rules_file.exists():
        return
    data = json.loads(rules_file.read_text())
    for rule in data.get("rules", []):
        add_brand_memory(
            brand_id=rule["brand_id"],
            key=rule["key"],
            value=rule["value"],
            market=rule.get("market"),
            category=rule["rule_type"],
        )
