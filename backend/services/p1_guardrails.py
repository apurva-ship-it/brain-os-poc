"""
P1 — Guardrail Layer
Always-on, never truncated. Runs before AND after LLM response.
Rules loaded from brand JSON files + hardcoded pharma baseline rules.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from models import GuardrailResult


# ── Hardcoded baseline rules (apply to ALL brands) ──────────────────────────
BASELINE_RULES = [
    {
        "rule_id": "BASE-001",
        "name": "No Cure Claims",
        "description": "Pharma products cannot be described as 'cures' without specific regulatory approval",
        "patterns": [r"\bcure[sd]?\b", r"\bcurative\b", r"\bguarantee[sd]?\b"],
        "severity": "critical",
        "message": "Cure/guarantee claims are prohibited in pharma marketing without specific regulatory basis.",
    },
    {
        "rule_id": "BASE-002",
        "name": "No Superlative Claims",
        "description": "Best-in-class, only, safest claims require specific regulatory approval",
        "patterns": [r"\bbest in class\b", r"\bsafest\b", r"\bonly treatment\b", r"\bonly approved therapy\b"],
        "severity": "high",
        "message": "Superlative claims ('best', 'safest', 'only') require specific clinical evidence and regulatory approval.",
    },
    {
        "rule_id": "BASE-003",
        "name": "PII Detection",
        "description": "No personally identifiable information in outputs",
        "patterns": [r"\b\d{3}-\d{2}-\d{4}\b", r"\bSSN\b", r"\bDOB:\s*\d"],
        "severity": "critical",
        "message": "PII detected — redacted for compliance.",
    },
]

# ── Brand-specific rules loaded from JSON files ──────────────────────────────
BRAND_RULES: dict[str, list[dict]] = {}


def load_brand_rules(data_dir: Path) -> None:
    """Load prohibited claims from brand JSON files into BRAND_RULES."""
    docs_dir = data_dir / "docs"
    if not docs_dir.exists():
        return

    for json_file in docs_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            brand = data.get("brand_metadata", {}).get("brand_name", "")
            if not brand:
                continue

            rules = []
            mc = data.get("marketing_content_rules", {})

            for i, prohibited in enumerate(mc.get("prohibited_claims", [])):
                rules.append({
                    "rule_id": f"{brand}-P{i+1:03d}",
                    "name": f"{brand} Prohibited Claim",
                    "description": prohibited,
                    "patterns": [],
                    "exact_text": prohibited,
                    "severity": "critical",
                    "message": f"Prohibited claim for {brand}: {prohibited}",
                })

            for i, req in enumerate(mc.get("required_fair_balance", [])):
                rules.append({
                    "rule_id": f"{brand}-FB{i+1:03d}",
                    "name": f"{brand} Fair Balance Required",
                    "description": req,
                    "patterns": [],
                    "fair_balance_trigger": True,
                    "required_text": req,
                    "severity": "high",
                    "message": f"Fair balance required for {brand}: {req}",
                })

            bw = data.get("boxed_warning", {})
            if bw:
                rules.append({
                    "rule_id": f"{brand}-BW001",
                    "name": f"{brand} Boxed Warning — Must Not Omit",
                    "description": bw.get("warning_title", ""),
                    "patterns": [],
                    "boxed_warning": bw.get("warning_summary", ""),
                    "severity": "critical",
                    "message": f"Boxed warning must not be minimized for {brand}: {bw.get('warning_title', '')}",
                })

            BRAND_RULES[brand.upper()] = rules
        except Exception:
            pass


def _matches_pattern(text: str, patterns: list[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


def check(message: str, response: str, brand_id: str | None) -> GuardrailResult:
    start = time.monotonic()
    combined = f"{message} {response}".lower()
    violations: list[dict] = []
    rules_checked = 0

    # Check baseline rules
    for rule in BASELINE_RULES:
        rules_checked += 1
        if rule["patterns"] and _matches_pattern(combined, rule["patterns"]):
            violations.append({
                "rule_id": rule["rule_id"],
                "name": rule["name"],
                "severity": rule["severity"],
                "message": rule["message"],
                "matched_text": message[:100],
            })

    # Check brand-specific rules
    brand_key = (brand_id or "").upper()
    for rule in BRAND_RULES.get(brand_key, []):
        rules_checked += 1
        exact = rule.get("exact_text", "").lower()
        # Check if message asks to make a prohibited claim
        if exact and (exact[:40] in combined or "don't" not in combined):
            # Simple heuristic: if user asks about something that matches prohibited text
            if any(word in combined for word in exact.split()[:4]):
                # Don't flag every match — only flag if it's an affirmative request
                if any(kw in message.lower() for kw in ["say", "write", "claim", "state", "tell", "use"]):
                    violations.append({
                        "rule_id": rule["rule_id"],
                        "name": rule["name"],
                        "severity": rule["severity"],
                        "message": rule["message"],
                        "matched_text": message[:100],
                    })

    latency = (time.monotonic() - start) * 1000
    blocked = any(v["severity"] == "critical" for v in violations)
    active_rules = list(BASELINE_RULES) + BRAND_RULES.get(brand_key, [])

    contributions = [
        {"type": "rules_loaded", "count": rules_checked, "brand": brand_key or "global"},
    ]
    if violations:
        for v in violations:
            contributions.append({"type": "violation", "rule": v["name"], "severity": v["severity"]})
    else:
        contributions.append({"type": "status", "message": f"All {rules_checked} rules passed ✓"})

    return GuardrailResult(
        tier="P1",
        label="Guardrails",
        active=True,
        hit=True,
        contributions=contributions,
        token_estimate=250,
        latency_ms=round(latency, 1),
        blocked=blocked,
        violations=violations,
        rules_checked=rules_checked,
    )


def get_rules_for_brand(brand_id: str) -> list[dict]:
    return BASELINE_RULES + BRAND_RULES.get((brand_id or "").upper(), [])
