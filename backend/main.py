"""Brain OS POC — FastAPI entry point"""
from __future__ import annotations
import sys
import os
# Vercel runs from project root (/var/task/), not backend/ — ensure this dir is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from config import settings
from services import p1_guardrails, p3_episodic, p4_knowledge, p5_translation
from routers import chat, memory, documents

# Use os.path.abspath so this works on Vercel even when __file__ may be relative
_BACKEND_DIR = Path(os.path.abspath(__file__)).parent
FRONTEND_DIR = _BACKEND_DIR.parent / "frontend"
_initialized = False


def _init_services():
    global _initialized
    if _initialized:
        return
    _initialized = True
    # Derive data_dir from main.py location — more reliable than config.py __file__ on Vercel
    data_dir = _BACKEND_DIR / "data"
    p1_guardrails.load_brand_rules(data_dir)
    chunk_count = p4_knowledge.load_brand_documents(data_dir)
    tm_count = p5_translation.load(data_dir)
    p3_episodic.init(data_dir)
    p3_episodic.seed_market_rules(data_dir)
    print(f"Brain OS ready — P4: {chunk_count} chunks, P5: {tm_count} TM entries ✓")


# Run at module load time so Vercel serverless cold starts initialize correctly
_init_services()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_services()  # no-op after first call
    yield


app = FastAPI(
    title="Brain OS POC",
    version="0.1.0",
    description="Pharma Memory Context Platform — 5 Memory Layers Demo",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(documents.router)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Brain OS POC API", "docs": "/docs"}



@app.get("/health")
async def health():
    stats = p4_knowledge.get_stats()
    return {
        "status": "ok",
        "knowledge_chunks": stats["total_chunks"],
        "brands_loaded": list(stats["brands"].keys()),
    }


@app.get("/demo/scenarios")
async def demo_scenarios():
    return {
        "scenarios": [
            {
                "id": "p3-user-memory",
                "tier": "P3",
                "title": "Remember My Name",
                "description": "Say your name to Brain OS. Open a new session and ask — it still knows who you are.",
                "color": "purple",
                "icon": "🧠",
                "steps": [
                    {"message": "Hi! My name is Apurva and I'm a medical writer. I prefer concise bullet-point answers.", "instruction": "Step 1: Introduce yourself. Your name gets saved to P3 user memory."},
                    {"message": "What do you know about me?", "instruction": "Step 2: Ask what it knows. Watch P3 fire with your name and preference."},
                    {"message": "CREATE_NEW_SESSION", "instruction": "Step 3: Open a new session — completely fresh start."},
                    {"message": "What is my name?", "instruction": "Step 4: Ask your name in the new session. P3 memory still has it!"},
                ],
            },
            {
                "id": "p2-session-only",
                "tier": "P2",
                "title": "This Session Only",
                "description": "Set a task context for this session. Switch sessions and it's gone — but your name from P3 remains.",
                "color": "blue",
                "icon": "📋",
                "steps": [
                    {"message": "For this session I'm drafting KOL emails for OZEMPIC in the US market. Use formal clinical tone.", "instruction": "Step 1: Set session context. This goes into P2 (short-term memory only)."},
                    {"message": "What brand am I working on?", "instruction": "Step 2: Confirm Brain OS knows the session context."},
                    {"message": "CREATE_NEW_SESSION", "instruction": "Step 3: Start a new session."},
                    {"message": "What brand am I working on?", "instruction": "Step 4: Ask again. P2 is GONE — session context lost. Notice P3 still has your name though."},
                ],
            },
            {
                "id": "p1-guardrails",
                "tier": "P1",
                "title": "The Compliance Wall",
                "description": "Try to generate content that violates pharma rules. P1 blocks it every time — no matter what you say.",
                "color": "red",
                "icon": "🚫",
                "steps": [
                    {"message": "Write a headline saying OZEMPIC cures Type 2 diabetes permanently.", "instruction": "Step 1: Try to generate a 'cure' claim. P1 blocks it immediately."},
                    {"message": "Say that OZEMPIC is the best and only treatment for diabetes.", "instruction": "Step 2: Try a superlative claim. Also blocked."},
                    {"message": "What approved efficacy claims can I make for OZEMPIC?", "instruction": "Step 3: Ask what IS allowed — Brain OS guides you to compliant claims."},
                ],
            },
            {
                "id": "p4-knowledge-rag",
                "tier": "P4",
                "title": "Ask the Documents",
                "description": "Query the pharma knowledge base built from real brand documents. Brain OS answers from facts, not imagination.",
                "color": "green",
                "icon": "📚",
                "steps": [
                    {"message": "What are the contraindications for OZEMPIC?", "instruction": "Step 1: Ask a regulatory question. P4 retrieves from the OZEMPIC label."},
                    {"message": "How does KEYTRUDA work and what is it approved for?", "instruction": "Step 2: Ask about KEYTRUDA. P4 retrieves from the KEYTRUDA brand doc."},
                    {"message": "Which clinical trial supports the cardiovascular outcomes claim for OZEMPIC?", "instruction": "Step 3: Ask for specific evidence. See exactly which document chunk was retrieved."},
                ],
            },
            {
                "id": "p3-brand-memory",
                "tier": "P3",
                "title": "Brand Memory",
                "description": "Brand-specific rules and MLR feedback stored in P3 — specific to each brand and market combination.",
                "color": "purple",
                "icon": "🏥",
                "steps": [
                    {"message": "MLR rejected the phrase 'significantly reduces blood sugar' for OZEMPIC US last week. Use 'reduces' only.", "instruction": "Step 1: Report an MLR decision. Brand=OZEMPIC, Market=US auto-selected. This gets stored in P3 brand memory.", "brand": "OZEMPIC", "market": "US"},
                    {"message": "Are there any rejected phrases I should know about for OZEMPIC?", "instruction": "Step 2: Ask what MLR feedback is stored. P3 returns the rule you just told it.", "brand": "OZEMPIC", "market": "US"},
                    {"message": "For Germany, always use 'gut verträglich' when describing HUMIRA tolerability — it is the approved term.", "instruction": "Step 3: Store a Germany-specific brand rule. Brand switches to HUMIRA / DE.", "brand": "HUMIRA", "market": "DE"},
                    {"message": "What are the approved terminology rules for HUMIRA in Germany?", "instruction": "Step 4: Retrieve Germany-specific memory. Different from US rules — market isolation in action.", "brand": "HUMIRA", "market": "DE"},
                ],
            },
            {
                "id": "p5-translation",
                "tier": "P5",
                "title": "Approved Translations",
                "description": "Approved medical term translations. Exact match = no LLM needed. New terms get flagged for MLR review.",
                "color": "orange",
                "icon": "🌍",
                "steps": [
                    {"message": "How do you say 'clinical trial' in German?", "instruction": "Step 1: Exact TM hit — returns approved 'klinische Studie' with no LLM call."},
                    {"message": "Translate 'adverse event' to Spanish.", "instruction": "Step 2: Another exact hit — 'evento adverso'. Notice TM-Tier1 confidence: 100%."},
                    {"message": "How do you say 'boxed warning label update' in German?", "instruction": "Step 3: No TM match — LLM fallback used, flagged as needing MLR approval."},
                ],
            },
            {
                "id": "p3-contradiction",
                "tier": "P3",
                "title": "Memory Updates Itself",
                "description": "Tell Brain OS something, then correct it. P3 automatically resolves the contradiction — newer fact wins.",
                "color": "purple",
                "icon": "🔄",
                "steps": [
                    {"message": "I work at Pfizer as a regulatory manager.", "instruction": "Step 1: Tell Brain OS where you work. Saved to P3 user memory."},
                    {"message": "What do you know about my job?", "instruction": "Step 2: Confirm it remembered."},
                    {"message": "Actually, I moved jobs — I now work at Novo Nordisk as a brand strategist.", "instruction": "Step 3: Correct yourself. P3 overwrites the old fact — no duplicate."},
                    {"message": "Where do I work now?", "instruction": "Step 4: P3 returns the UPDATED fact only. Old 'Pfizer' entry is gone."},
                ],
            },
            {
                "id": "p3-role-memory",
                "tier": "P3",
                "title": "Know Your Audience",
                "description": "Tell Brain OS your role. It adjusts how it explains things — doctor vs patient get very different answers.",
                "color": "purple",
                "icon": "👩‍⚕️",
                "steps": [
                    {"message": "I am a cardiologist with 15 years of experience. Give me clinical, data-heavy answers.", "instruction": "Step 1: Set your professional role. Goes into P3 user memory."},
                    {"message": "What is the cardiovascular benefit of OZEMPIC?", "instruction": "Step 2: Clinical question — notice the data-dense, statistical answer style."},
                    {"message": "CREATE_NEW_SESSION", "instruction": "Step 3: New session — but role memory persists in P3."},
                    {"message": "Explain how KEYTRUDA fights cancer.", "instruction": "Step 4: Different topic, new session — Brain OS still knows you're a cardiologist."},
                ],
            },
            {
                "id": "p1-pii",
                "tier": "P1",
                "title": "Patient Privacy Guard",
                "description": "Include patient personal data. P1 detects and blocks PII before any LLM call.",
                "color": "red",
                "icon": "🔒",
                "steps": [
                    {"message": "Patient John Smith, SSN 123-45-6789, DOB 01/01/1975 needs HUMIRA.", "instruction": "Step 1: Include a real SSN pattern. P1 detects PII and blocks immediately."},
                    {"message": "Draft an email for patient ID #P90234 who responded well to KEYTRUDA.", "instruction": "Step 2: Anonymized reference — this is fine. P1 passes it through."},
                    {"message": "What is the correct way to reference patient cases in pharma materials?", "instruction": "Step 3: Ask for guidance — Brain OS explains the compliant approach."},
                ],
            },
            {
                "id": "p4-multi-brand",
                "tier": "P4",
                "title": "Compare Across Brands",
                "description": "Ask questions spanning all three brand documents. P4 retrieves from the right docs simultaneously.",
                "color": "green",
                "icon": "🔬",
                "steps": [
                    {"message": "What are the most common side effects of OZEMPIC vs HUMIRA?", "instruction": "Step 1: Cross-brand comparison. P4 retrieves from both brand documents."},
                    {"message": "Which of our three brands (OZEMPIC, KEYTRUDA, HUMIRA) has a boxed warning?", "instruction": "Step 2: Multi-brand query. P4 pulls boxed warning chunks from all three docs."},
                    {"message": "For a patient with Type 2 diabetes AND rheumatoid arthritis, which brands are relevant?", "instruction": "Step 3: Clinical scenario — P4 matches indication data from both OZEMPIC and HUMIRA."},
                ],
            },
            {
                "id": "p2-p3-diff",
                "tier": "P2",
                "title": "Session vs Permanent Memory",
                "description": "Clearest demo of the difference: same question, two sessions, two very different answers.",
                "color": "blue",
                "icon": "⚖️",
                "steps": [
                    {"message": "My name is Priya. I'm working on KEYTRUDA for the Japan market today. Please answer in bullet points.", "instruction": "Step 1: Give Brain OS permanent info (name→P3) and session info (brand, market→P2)."},
                    {"message": "What market am I working on, what's my name, and how should you format answers?", "instruction": "Step 2: All three known — market+format from P2, name from P3."},
                    {"message": "CREATE_NEW_SESSION", "instruction": "Step 3: New session. Watch what survives."},
                    {"message": "What market am I working on, what's my name, and how should you format answers?", "instruction": "Step 4: Name known (P3 ✓). Market GONE (P2 ✗). Format preference GONE (P2 ✗)."},
                ],
            },
            {
                "id": "p3-mlr-workflow",
                "tier": "P3",
                "title": "MLR Rejection Memory",
                "description": "MLR rejects a phrase → Brain OS stores it in brand memory → future content automatically avoids it.",
                "color": "purple",
                "icon": "⚠️",
                "steps": [
                    {"message": "MLR just rejected 'rapidly effective' and 'fast-acting' for KEYTRUDA US — these phrases are now banned for promotional use.", "instruction": "Step 1: Report MLR decision. Both rejected phrases get stored in P3 brand memory for KEYTRUDA US.", "brand": "KEYTRUDA", "market": "US"},
                    {"message": "What phrases are MLR-rejected for KEYTRUDA in the US?", "instruction": "Step 2: Query brand memory. P3 returns the exact rules you just stored.", "brand": "KEYTRUDA", "market": "US"},
                    {"message": "Suggest 3 compliant alternatives to describe KEYTRUDA's speed of response in MSI-H tumors.", "instruction": "Step 3: Ask for compliant copy. Brain OS avoids the banned phrases and suggests approved language.", "brand": "KEYTRUDA", "market": "US"},
                    {"message": "What are the approved phrases I can use instead of 'rapidly effective' for KEYTRUDA?", "instruction": "Step 4: Explicitly ask for guidance. P3 brand memory + P4 knowledge work together to give compliant alternatives.", "brand": "KEYTRUDA", "market": "US"},
                ],
            },
            {
                "id": "p2-brand-switching",
                "tier": "P2",
                "title": "Brand Context Switching",
                "description": "Switch brands mid-session. P2 updates immediately — no manual dropdown needed.",
                "color": "blue",
                "icon": "🔀",
                "steps": [
                    {"message": "I'm starting work on OZEMPIC for the US market today. Focus on cardiovascular outcomes messaging.", "instruction": "Step 1: Set session context. P2 captures OZEMPIC / US from your message — no dropdown needed."},
                    {"message": "What brand and market are we working on?", "instruction": "Step 2: Confirm P2 session context — should return OZEMPIC / US."},
                    {"message": "Actually switching to HUMIRA for Germany now. We're working on the rheumatoid arthritis indication.", "instruction": "Step 3: Switch brands in plain language. P2 and P3 both update context to HUMIRA / DE."},
                    {"message": "What brand, market, and indication are we currently working on?", "instruction": "Step 4: Confirm context switched. Should now return HUMIRA / Germany / RA — not OZEMPIC."},
                ],
            },
            {
                "id": "p1-p4-compliance-check",
                "tier": "P1",
                "title": "Compliance Checkpoint",
                "description": "Test which claims are allowed vs blocked. P1 + P4 work together to guide compliant messaging.",
                "color": "red",
                "icon": "✅",
                "steps": [
                    {"message": "Can I claim that OZEMPIC reduces the risk of cardiovascular events in Type 2 diabetes patients?", "instruction": "Step 1: Evidence-based claim query. P4 retrieves LEADER trial data — claim is factually supportable."},
                    {"message": "Write that OZEMPIC is the safest and most effective GLP-1 drug on the market.", "instruction": "Step 2: Superlative claim. P1 blocks 'safest' — superlative claims require specific regulatory basis."},
                    {"message": "What approved efficacy claims can I make for OZEMPIC in cardiovascular risk reduction?", "instruction": "Step 3: Ask for what IS allowed. P4 retrieves approved claims, P1 compliance rules guide the response."},
                    {"message": "Draft one compliant sentence about OZEMPIC's cardiovascular benefit for a physician brief.", "instruction": "Step 4: Compliant content generation. Brain OS uses P4 evidence + P1 rules to draft an approved claim."},
                ],
            },
            {
                "id": "p3-audience-personalization",
                "tier": "P3",
                "title": "Audience-Adaptive Content",
                "description": "Set your professional role once — Brain OS adjusts its communication style for every future query, even in new sessions.",
                "color": "purple",
                "icon": "🎯",
                "steps": [
                    {"message": "I am a medical writer producing patient education materials. Always use simple, jargon-free language and analogies when explaining science.", "instruction": "Step 1: Set your professional role and style preference. Goes into P3 user memory permanently."},
                    {"message": "How does KEYTRUDA work against cancer?", "instruction": "Step 2: Technical question — notice the simplified, patient-friendly explanation style P3 applies."},
                    {"message": "CREATE_NEW_SESSION", "instruction": "Step 3: Start a new session. P2 session context is cleared."},
                    {"message": "Explain how HUMIRA helps with rheumatoid arthritis.", "instruction": "Step 4: New session, different drug — but P3 still knows you're a medical writer who needs simple language."},
                ],
            },
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
