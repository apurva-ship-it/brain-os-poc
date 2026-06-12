# Brain OS POC — 5 Memory Layers Demo

## Quick Start

```bash
# 1. Add your Anthropic API key
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > backend/.env

# 2. Run
./start.sh

# 3. Open browser
open http://localhost:8000
```

## What it demonstrates

| Layer | What it is | Layman example |
|---|---|---|
| P1 Guardrails | Always-on rules, never bypassed | "Write that OZEMPIC cures diabetes" → BLOCKED |
| P2 Session | This session only, cleared on close | "I'm working on OZEMPIC US today" → gone in new session |
| P3 Episodic | Persists across sessions, user + brand | "My name is Apurva" → remembered in ALL future sessions |
| P4 Knowledge | RAG over brand documents | "What are OZEMPIC's contraindications?" → from label JSON |
| P5 Translation | Approved medical translations | "clinical trial" in German → "klinische Studie" (TM hit) |

## Demo Scenarios (click Demo Scenarios tab)

1. **P3 Remember My Name** — Say your name, open new session, ask it again
2. **P2 This Session Only** — Set brand context, switch sessions, it's gone
3. **P1 Compliance Wall** — Try to generate prohibited claims, get blocked
4. **P4 Ask the Documents** — Query OZEMPIC, KEYTRUDA, HUMIRA brand docs
5. **P3 Brand Memory** — Market-specific MLR rules pre-loaded in P3
6. **P5 Approved Translations** — Exact TM hit vs LLM fallback for medical terms

## Pre-loaded data

- **P4 Knowledge**: 67 chunks from OZEMPIC, KEYTRUDA, HUMIRA brand documents (FDA labels + approved claims)
- **P3 Brand Memory**: 8 market rules (OZEMPIC US/DE, KEYTRUDA US, HUMIRA US/DE/IN)
- **P5 Translation Memory**: 106 approved medical translations (German, Spanish, French, Japanese)
- **P1 Guardrails**: Baseline rules (no cure claims, no superlatives, PII detection) + brand-specific prohibited claims

## Architecture

```
User message
    ↓
P1 Guardrails check (pre-LLM) — blocks prohibited content
    ↓
P2 Session memory — current brand/market/task context
    ↓
P3 Episodic memory — user facts + brand-market rules (SQLite, persistent)
    ↓
P4 Knowledge RAG — BM25 search over brand documents
    ↓
P5 Translation Memory — exact/fuzzy match from approved TM
    ↓
Context assembled → LLM (Claude Haiku) → P1 validated → Response + Memory Trace
    ↓
P3 write — extract and store new facts from this conversation
```
