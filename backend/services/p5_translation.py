"""
P5 — Translation Memory (Localization Layer)
First to compress under token pressure.
3-tier lookup: Exact match (O(1)) → Fuzzy match (difflib) → LLM translation (fallback).

Layman analogy: a company-approved phrasebook. Before any translator makes up a new
translation, they MUST check this book first. Pre-approved phrases only.

Use cases:
  - "Translate 'clinical trial' to German" → exact hit: "klinische Studie"
  - "How do you say 'once weekly' in Spanish?" → exact or fuzzy hit
  - New terms → LLM fallback with warning that it needs MLR approval
"""
from __future__ import annotations

import json
import time
from difflib import SequenceMatcher
from pathlib import Path
from models import TierResult


_tm: dict[str, dict[str, str]] = {}  # {lang_code: {source_term: translation}}
_FUZZY_THRESHOLD = 0.75


def load(data_dir: Path) -> int:
    global _tm
    tm_file = data_dir / "p5_translation_memory.json"
    if not tm_file.exists():
        return 0
    data = json.loads(tm_file.read_text())
    langs = data.get("languages", {})
    count = 0
    for lang_code, lang_data in langs.items():
        _tm[lang_code.upper()] = lang_data.get("entries", {})
        count += len(_tm[lang_code.upper()])
    return count


def _fuzzy_match(query: str, entries: dict[str, str]) -> tuple[str | None, str | None, float]:
    """Return (source_term, translation, score) for best fuzzy match."""
    best_score = 0.0
    best_term = None
    best_translation = None
    q = query.lower()
    for term, translation in entries.items():
        score = SequenceMatcher(None, q, term.lower()).ratio()
        if score > best_score:
            best_score = score
            best_term = term
            best_translation = translation
    return best_term, best_translation, best_score


def translate(term: str, target_lang: str) -> TierResult:
    start = time.monotonic()
    lang = target_lang.upper()

    contributions = []

    if lang not in _tm:
        latency = (time.monotonic() - start) * 1000
        return TierResult(
            tier="P5", label="Translation Memory", active=False, hit=False,
            contributions=[{"type": "status", "message": f"Language '{target_lang}' not in Translation Memory. Available: {list(_tm.keys())}"}],
            token_estimate=0, latency_ms=round(latency, 1),
        )

    entries = _tm[lang]

    # Tier 1: Exact match
    term_lower = term.lower()
    if term_lower in entries:
        translation = entries[term_lower]
        contributions.append({
            "type": "exact_match",
            "tier": "TM-Tier1-Exact",
            "source_term": term,
            "translation": translation,
            "language": target_lang,
            "confidence": 1.0,
            "requires_llm": False,
            "message": f"✓ Exact TM hit — no LLM needed",
        })
        latency = (time.monotonic() - start) * 1000
        return TierResult(
            tier="P5", label="Translation Memory", active=True, hit=True,
            contributions=contributions, token_estimate=20, latency_ms=round(latency, 1),
        )

    # Tier 2: Fuzzy match
    best_term, best_translation, score = _fuzzy_match(term, entries)
    if score >= _FUZZY_THRESHOLD:
        contributions.append({
            "type": "fuzzy_match",
            "tier": "TM-Tier2-Fuzzy",
            "source_term": term,
            "matched_term": best_term,
            "translation": best_translation,
            "language": target_lang,
            "confidence": round(score, 2),
            "requires_llm": False,
            "message": f"~ Fuzzy TM hit ({int(score*100)}% match) — candidate for review",
        })
        latency = (time.monotonic() - start) * 1000
        return TierResult(
            tier="P5", label="Translation Memory", active=True, hit=True,
            contributions=contributions, token_estimate=25, latency_ms=round(latency, 1),
        )

    # Tier 3: TM miss — needs LLM
    contributions.append({
        "type": "tm_miss",
        "tier": "TM-Tier3-LLM-Fallback",
        "source_term": term,
        "language": target_lang,
        "requires_llm": True,
        "confidence": 0.0,
        "message": f"✗ No TM match for '{term}' in {target_lang}. LLM translation used — needs MLR approval before use in materials.",
    })
    latency = (time.monotonic() - start) * 1000
    return TierResult(
        tier="P5", label="Translation Memory", active=True, hit=False,
        contributions=contributions, token_estimate=0, latency_ms=round(latency, 1),
    )


def is_translation_query(message: str) -> tuple[bool, str | None, str | None]:
    """Detect if message is asking for a translation."""
    msg = message.lower()
    lang_map = {
        "german": "DE", "deutsch": "DE", "de": "DE",
        "spanish": "ES", "español": "ES", "es": "ES",
        "french": "FR", "français": "FR", "fr": "FR",
        "japanese": "JA", "日本語": "JA", "ja": "JA",
    }

    translation_keywords = ["translate", "in german", "in spanish", "in french", "in japanese",
                             "auf deutsch", "auf englisch", "how do you say", "what is", "approved translation"]

    if not any(kw in msg for kw in translation_keywords):
        return False, None, None

    detected_lang = None
    for lang_name, code in lang_map.items():
        if lang_name in msg:
            detected_lang = code
            break

    # Try to extract the term being translated
    term = None
    for pattern in ["translate '", "translate \"", "say '", "say \"", "translation of '"]:
        idx = msg.find(pattern)
        if idx >= 0:
            start_idx = idx + len(pattern)
            end_idx = msg.find("'", start_idx) if "'" in pattern else msg.find('"', start_idx)
            if end_idx > start_idx:
                term = message[start_idx:end_idx]
                break

    return True, term, detected_lang


def get_all_entries() -> dict:
    return {lang: list(entries.keys()) for lang, entries in _tm.items()}
