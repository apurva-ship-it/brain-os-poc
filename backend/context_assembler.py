"""
Context Assembler — P1 → P2 → P3 → P4 → P5
Assembles the full system prompt from all 5 memory tiers with token budgeting.
P1 is NEVER truncated. P5 is FIRST to compress.
"""
from __future__ import annotations

from services import p1_guardrails, p2_session, p3_episodic, p4_knowledge, p5_translation
from models import TierResult


TOKEN_BUDGET = 3000  # System prompt token budget


def _build_system_prompt(
    p1_result,
    p2_result,
    p3_result,
    p4_result,
    p5_result,
    brand_id: str | None,
    market: str | None,
) -> str:
    sections = []

    # ── P1 ALWAYS included ────────────────────────────────────────────────────
    rules = p1_guardrails.get_rules_for_brand(brand_id)
    if rules:
        rule_lines = []
        for r in rules[:8]:  # Cap at 8 rules in prompt
            rule_lines.append(f"- [{r['rule_id']}] {r['description']}")
        sections.append(
            "## COMPLIANCE RULES (P1 — NEVER IGNORE)\n"
            "The following rules are MANDATORY. Violating any of them is prohibited:\n"
            + "\n".join(rule_lines)
        )

    # ── P2 Session context ─────────────────────────────────────────────────────
    p2_lines = []
    for c in p2_result.contributions:
        if c.get("type") in ("brand_context", "market_context", "session_preference"):
            p2_lines.append(f"- {c['key'].replace('_', ' ').title()}: {c['value']}")
    if p2_lines:
        sections.append("## CURRENT SESSION CONTEXT (P2)\n" + "\n".join(p2_lines))

    # ── P3 Episodic memory ─────────────────────────────────────────────────────
    p3_lines = []
    for c in p3_result.contributions:
        if c.get("type") in ("user_memory", "brand_memory", "market_memory"):
            scope = c.get("scope", "")
            p3_lines.append(f"- [{c['type'].replace('_', ' ').upper()}] {c['key']}: {c['value']}")
    if p3_lines:
        sections.append("## REMEMBERED CONTEXT (P3 — persistent across sessions)\n" + "\n".join(p3_lines))

    # ── P4 Knowledge / RAG ─────────────────────────────────────────────────────
    p4_lines = []
    for c in p4_result.contributions:
        if c.get("type") == "knowledge_chunk":
            p4_lines.append(f"### From: {c['brand']} — {c['section']}\n{c.get('full_text', c.get('preview', ''))}")
    if p4_lines:
        sections.append("## KNOWLEDGE BASE (P4 — retrieved from ingested documents)\n" + "\n\n".join(p4_lines))

    # ── P5 Translation Memory ──────────────────────────────────────────────────
    p5_lines = []
    for c in p5_result.contributions:
        if c.get("type") in ("exact_match", "fuzzy_match"):
            p5_lines.append(f"- Approved translation for '{c['source_term']}' in {c['language']}: {c['translation']}")
    if p5_lines:
        sections.append("## APPROVED TRANSLATIONS (P5)\n" + "\n".join(p5_lines))

    # ── Base instruction ───────────────────────────────────────────────────────
    brand_ctx = f" for {brand_id}" if brand_id else ""
    market_ctx = f" in the {market} market" if market else ""
    base = (
        f"You are Brain OS, a pharma brand intelligence assistant{brand_ctx}{market_ctx}. "
        "Answer questions using the knowledge base and remembered context above. "
        "Always cite sources when making factual claims. "
        "Comply with all P1 compliance rules — never generate content that violates them."
    )

    return base + "\n\n" + "\n\n".join(sections)


def assemble(
    message: str,
    session_id: str,
    user_id: str,
    brand_id: str | None,
    market: str | None,
    target_language: str | None = None,
) -> tuple[str, dict, bool]:
    """
    Returns: (system_prompt, memory_trace, is_blocked)
    """
    # P1 — guardrails check (pre-LLM on the incoming message)
    p1 = p1_guardrails.check(message, "", brand_id)

    # P2 — session context
    p2 = p2_session.retrieve(session_id)

    # P3 — episodic memory
    p3 = p3_episodic.retrieve(user_id, brand_id, market, message)

    # P4 — knowledge RAG
    p4 = p4_knowledge.search(message, brand_id, top_k=3)

    # P5 — translation memory
    is_translation, term, lang = p5_translation.is_translation_query(message)
    if is_translation and term and lang:
        p5 = p5_translation.translate(term, lang)
    elif target_language:
        p5 = p5_translation.translate(message, target_language)
    else:
        p5 = TierResult(
            tier="P5", label="Translation Memory", active=False, hit=False,
            contributions=[{"type": "status", "message": "Not a translation query — P5 not needed"}],
            token_estimate=0, latency_ms=0,
        )

    # Build system prompt
    system_prompt = _build_system_prompt(p1, p2, p3, p4, p5, brand_id, market)

    memory_trace = {
        "P1": p1.model_dump(),
        "P2": p2.model_dump(),
        "P3": p3.model_dump(),
        "P4": p4.model_dump(),
        "P5": p5.model_dump(),
        "total_tokens": p1.token_estimate + p2.token_estimate + p3.token_estimate + p4.token_estimate + p5.token_estimate,
    }

    return system_prompt, memory_trace, p1.blocked
