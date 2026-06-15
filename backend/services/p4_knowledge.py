"""
P4 — Knowledge / RAG Layer (Semantic Long-term Memory)
Scope: Brand-scoped. Persists indefinitely. Updated via document ingestion.
Backed by BM25 keyword search over chunked brand documents.

Layman analogy: a very smart librarian who has read every document in your library
and can instantly find the most relevant pages when you ask a question.

Use cases:
  - "What are the contraindications for OZEMPIC?" → retrieves from label JSON
  - "What indications is HUMIRA approved for?" → retrieves from brand doc
  - "What clinical trial supports the KEYTRUDA CV claim?" → retrieves trial data
"""
from __future__ import annotations

import json
import time
import re
from pathlib import Path
from dataclasses import dataclass
from models import TierResult

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


@dataclass
class Chunk:
    chunk_id: str
    brand_id: str
    dataset: str
    section: str
    text: str
    metadata: dict


# In-memory index
_chunks: list[Chunk] = []
_bm25: object | None = None
_tokenized: list[list[str]] = []


def _tokenize(text: str) -> list[str]:
    return re.findall(r'\b\w+\b', text.lower())


def _flatten_brand_doc(data: dict, brand_id: str) -> list[Chunk]:
    """Convert brand JSON into searchable text chunks."""
    chunks = []
    cid = 0

    def make_chunk(section: str, text: str, dataset: str = "brand_knowledge") -> Chunk:
        nonlocal cid
        cid += 1
        return Chunk(
            chunk_id=f"{brand_id}-{cid:04d}",
            brand_id=brand_id,
            dataset=dataset,
            section=section,
            text=text,
            metadata={"source": f"{brand_id}_brand_document", "brand": brand_id},
        )

    # Brand overview
    meta = data.get("brand_metadata", {})
    chunks.append(make_chunk(
        "Brand Overview",
        f"{meta.get('brand_name', brand_id)} ({meta.get('generic_name', '')}) is a {meta.get('drug_class', '')} "
        f"manufactured by {meta.get('manufacturer', '')}. Therapeutic area: {meta.get('therapeutic_area', '')}. "
        f"Route: {', '.join(meta.get('route_of_administration', []))}. Status: {meta.get('approval_status', '')}.",
    ))

    # Indications
    inds = data.get("indications", {})
    for ind in inds.get("approved_indications", []):
        chunks.append(make_chunk(
            "Approved Indication",
            f"{brand_id} approved indication: {ind.get('indication_text', '')} Population: {ind.get('population', '')}. "
            f"Basis: {ind.get('regulatory_basis', '')}.",
            dataset="regulatory_docs",
        ))

    not_approved = inds.get("not_approved_for", [])
    if not_approved:
        chunks.append(make_chunk(
            "Not Approved For",
            f"{brand_id} is NOT approved for: {'; '.join(not_approved)}.",
            dataset="regulatory_docs",
        ))

    # Approved tumor types (KEYTRUDA style)
    for ind in inds.get("approved_tumor_types", []):
        chunks.append(make_chunk(
            f"Indication — {ind.get('tumor_type', '')}",
            f"{brand_id} approved for {ind.get('tumor_type', '')}: {ind.get('indication_text', '')} "
            f"Population: {ind.get('population', '')}. "
            + (f"Biomarker required: {ind.get('biomarker_required', '')}." if ind.get('biomarker_required') else ""),
            dataset="regulatory_docs",
        ))

    # Mechanism of action
    moa = data.get("mechanism_of_action", {})
    if moa:
        mechanisms = "; ".join(moa.get("key_mechanisms", []))
        chunks.append(make_chunk(
            "Mechanism of Action",
            f"{brand_id} mechanism: {moa.get('moa_summary', '')} Key mechanisms: {mechanisms}.",
        ))

    # Approved claims
    for claim in data.get("approved_claims", []):
        chunks.append(make_chunk(
            f"Approved Claim — {claim.get('claim_type', '')}",
            f"APPROVED CLAIM for {brand_id}: {claim.get('claim_text', '')} "
            f"Supporting data: {claim.get('supporting_data', '')}. "
            f"Source: {claim.get('source_section', '')}.",
            dataset="approved_content",
        ))

    # Contraindications
    cis = data.get("contraindications", [])
    if cis:
        ci_texts = "; ".join(c.get("text", "") for c in cis)
        chunks.append(make_chunk(
            "Contraindications",
            f"{brand_id} contraindications: {ci_texts}.",
            dataset="regulatory_docs",
        ))

    # Boxed warning
    bw = data.get("boxed_warning", {})
    if bw:
        chunks.append(make_chunk(
            "Boxed Warning",
            f"{brand_id} BOXED WARNING — {bw.get('warning_title', '')}: {bw.get('warning_summary', '')}",
            dataset="regulatory_docs",
        ))

    # Key warnings
    warnings = data.get("key_warnings", [])
    if warnings:
        chunks.append(make_chunk(
            "Key Warnings",
            f"{brand_id} key warnings: {'; '.join(warnings)}.",
            dataset="regulatory_docs",
        ))

    # Adverse reactions
    ar = data.get("adverse_reactions", {})
    if ar:
        common = ", ".join(ar.get("most_common_gte_5pct", []))
        chunks.append(make_chunk(
            "Adverse Reactions",
            f"{brand_id} most common adverse reactions (≥5%): {common}. "
            f"Post-marketing: {'; '.join(ar.get('postmarketing_notable', []))}.",
        ))

    # Dosing
    dosing = data.get("dosing", {})
    if dosing:
        dose_text = json.dumps(dosing, indent=None)
        chunks.append(make_chunk(
            "Dosing",
            f"{brand_id} dosing information: {dose_text[:400]}",
            dataset="regulatory_docs",
        ))

    # Marketing content rules
    mc = data.get("marketing_content_rules", {})
    if mc:
        prohibited = "; ".join(mc.get("prohibited_claims", []))
        mandatory = "; ".join(mc.get("mandatory_references", []))
        chunks.append(make_chunk(
            "Marketing Rules",
            f"{brand_id} marketing rules. Prohibited: {prohibited}. Mandatory refs: {mandatory}.",
            dataset="approved_content",
        ))

    return chunks


def load_brand_documents(data_dir: Path) -> int:
    """Load all brand JSONs from docs/ directory into BM25 index."""
    global _chunks, _bm25, _tokenized
    docs_dir = data_dir / "docs"
    if not docs_dir.exists():
        return 0

    new_chunks: list[Chunk] = []
    for json_file in docs_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            brand = data.get("brand_metadata", {}).get("brand_name", json_file.stem.split("_")[0])
            new_chunks.extend(_flatten_brand_doc(data, brand.upper()))
        except Exception as e:
            print(f"Failed to load {json_file}: {e}")

    _chunks = new_chunks
    if _chunks and HAS_BM25:
        _tokenized = [_tokenize(c.text) for c in _chunks]
        _bm25 = BM25Okapi(_tokenized)
    return len(_chunks)


def _simple_score(query_tokens: list[str], chunk_text: str) -> float:
    """Fallback scoring when BM25 not available."""
    text = chunk_text.lower()
    return sum(1.0 for t in query_tokens if t in text) / max(len(query_tokens), 1)


def search(query: str, brand_id: str | None = None, top_k: int = 3) -> TierResult:
    start = time.monotonic()

    if not _chunks:
        return TierResult(
            tier="P4", label="Knowledge / RAG", active=False, hit=False,
            contributions=[{"type": "status", "message": "No documents ingested yet. Upload brand documents first."}],
            token_estimate=0, latency_ms=0,
        )

    query_tokens = _tokenize(query)
    candidates = _chunks

    # Detect multi-brand queries — override to search all brands globally
    _BRAND_NAMES = ["OZEMPIC", "KEYTRUDA", "HUMIRA"]
    _MULTI_KW = ["all three", "all brands", "which brand", "each brand", "our brands", "versus", "compare"]
    q_upper = " " + query.upper() + " "
    brands_in_query = [b for b in _BRAND_NAMES if b in q_upper]
    if len(brands_in_query) >= 2 or any(kw in query.lower() for kw in _MULTI_KW):
        brand_id = None  # Search all brands
        top_k = max(top_k, 6)  # More chunks for multi-brand
    elif brand_id:
        brand_chunks = [c for c in candidates if c.brand_id.upper() == brand_id.upper()]
        if brand_chunks:
            candidates = brand_chunks

    if not candidates:
        return TierResult(
            tier="P4", label="Knowledge / RAG", active=True, hit=False,
            contributions=[{"type": "status", "message": f"No documents found for brand: {brand_id}"}],
            token_estimate=0, latency_ms=0,
        )

    # Score chunks
    if HAS_BM25 and _bm25 and brand_id is None:
        # Use global BM25 index (all brands)
        scores = _bm25.get_scores(query_tokens)
        indexed = sorted(
            [(i, scores[i]) for i in range(len(_chunks))],
            key=lambda x: x[1], reverse=True,
        )
        top_chunks = [_chunks[i] for i, _ in indexed[:top_k] if scores[i] > 0]
    else:
        # Simple scoring over filtered candidates
        scored = [(c, _simple_score(query_tokens, c.text)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        top_chunks = [c for c, s in scored[:top_k] if s > 0]

    if not top_chunks:
        top_chunks = candidates[:top_k]  # Fallback: return first chunks

    contributions = []
    for c in top_chunks:
        contributions.append({
            "type": "knowledge_chunk",
            "chunk_id": c.chunk_id,
            "brand": c.brand_id,
            "section": c.section,
            "dataset": c.dataset,
            "preview": c.text[:150] + ("..." if len(c.text) > 150 else ""),
            "full_text": c.text,
        })

    token_est = sum(len(c.text.split()) * 1.3 for c in top_chunks)
    latency = (time.monotonic() - start) * 1000

    return TierResult(
        tier="P4", label="Knowledge / RAG", active=True, hit=True,
        contributions=contributions, token_estimate=int(token_est), latency_ms=round(latency, 1),
    )


def add_document(brand_id: str, content: str, section: str = "Uploaded Document", dataset: str = "brand_knowledge") -> int:
    """Add a custom document chunk to the index."""
    global _chunks, _bm25, _tokenized
    chunk = Chunk(
        chunk_id=f"{brand_id}-UPLOAD-{len(_chunks)+1:04d}",
        brand_id=brand_id.upper(),
        dataset=dataset,
        section=section,
        text=content,
        metadata={"source": "user_upload"},
    )
    _chunks.append(chunk)
    # Rebuild BM25
    if HAS_BM25:
        _tokenized = [_tokenize(c.text) for c in _chunks]
        _bm25 = BM25Okapi(_tokenized)
    return len(_chunks)


def get_stats() -> dict:
    brands = {}
    for c in _chunks:
        brands[c.brand_id] = brands.get(c.brand_id, 0) + 1
    return {"total_chunks": len(_chunks), "brands": brands, "bm25_active": HAS_BM25 and _bm25 is not None}
