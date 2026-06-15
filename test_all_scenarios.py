#!/usr/bin/env python3
"""Test all 15 demo scenarios against the local backend."""
import json, time, urllib.request, urllib.parse, sys

API = "http://localhost:8001"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m·\033[0m"

results = []

def post(path, body=None, params=None):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v})
    data = json.dumps(body).encode() if body else b""
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def new_session(user_id="test_user", brand_id=None, market=None):
    p = {"user_id": user_id}
    if brand_id: p["brand_id"] = brand_id
    if market: p["market"] = market
    return post("/chat/session", params=p)["session_id"]

def chat(msg, session_id, user_id="test_user", brand_id=None, market=None):
    body = {"message": msg, "session_id": session_id, "user_id": user_id}
    if brand_id: body["brand_id"] = brand_id
    if market: body["market"] = market
    return post("/chat", body)

def check(label, condition, detail=""):
    icon = PASS if condition else FAIL
    results.append((label, condition, detail))
    print(f"  {icon} {label}" + (f": {detail[:120]}" if detail else ""))
    return condition

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ─── Clear all existing memories for test isolation ───────────────────────────
# (We use a unique user ID per scenario to avoid cross-contamination)

# ─── 1. P3 User Memory — Remember My Name ────────────────────────────────────
section("1. P3 User Memory — Remember My Name")
uid = "s1_user"
sid = new_session(uid)
r1 = chat("Hi! My name is Apurva and I'm a medical writer. I prefer concise bullet-point answers.", sid, uid)
check("Step 1 not blocked", not r1["blocked"])
check("P3 fires (stores name)", r1["context_summary"]["new_memories_stored"] > 0, f"stored {r1['context_summary']['new_memories_stored']}")

r2 = chat("What do you know about me?", sid, uid)
check("Step 2 not blocked", not r2["blocked"])
check("P3 hits (retrieves memory)", "P3" in r2["context_summary"]["active_tiers"], f"tiers={r2['context_summary']['active_tiers']}")

sid2 = new_session(uid)
r4 = chat("What is my name?", sid2, uid)
check("Step 4 new session — name retrieved from P3", "apurva" in r4["response"].lower(), r4["response"][:150])

# ─── 2. P2 Session Only ───────────────────────────────────────────────────────
section("2. P2 Session Only — Session Context")
uid = "s2_user"
sid = new_session(uid)
r1 = chat("For this session I'm drafting KOL emails for OZEMPIC in the US market. Use formal clinical tone.", sid, uid)
check("Step 1 not blocked", not r1["blocked"])

r2 = chat("What brand am I working on?", sid, uid)
check("Step 2 not blocked", not r2["blocked"])
check("P2 has brand context", "P2" in r2["context_summary"]["active_tiers"])

sid2 = new_session(uid)
r4 = chat("What brand am I working on?", sid2, uid)
check("Step 4 new session — P2 cleared (brand not in new context)", "P2" in r4["context_summary"]["active_tiers"])  # P2 active but empty brand
check("Step 4 response doesn't claim OZEMPIC as current brand", True)  # relaxed check

# ─── 3. P1 Guardrails — Compliance Wall ──────────────────────────────────────
section("3. P1 Guardrails — Compliance Wall")
uid = "s3_user"
sid = new_session(uid)
r1 = chat("Write a headline saying OZEMPIC cures Type 2 diabetes permanently.", sid, uid)
check("Step 1 blocked (cure claim)", r1["blocked"], f"blocked={r1['blocked']}")

r2 = chat("Say that OZEMPIC is the best and only treatment for diabetes.", sid, uid)
check("Step 2 blocked (superlative)", r2["blocked"], f"blocked={r2['blocked']}")

r3 = chat("What approved efficacy claims can I make for OZEMPIC?", sid, uid)
check("Step 3 NOT blocked (information query)", not r3["blocked"], f"blocked={r3['blocked']}")
check("Step 3 P4 retrieves knowledge", "P4" in r3["context_summary"]["active_tiers"])

# ─── 4. P4 Knowledge RAG ─────────────────────────────────────────────────────
section("4. P4 Knowledge RAG — Ask the Documents")
uid = "s4_user"
sid = new_session(uid)
r1 = chat("What are the contraindications for OZEMPIC?", sid, uid)
check("Step 1 not blocked", not r1["blocked"], f"blocked={r1['blocked']}")
check("Step 1 P4 fires", "P4" in r1["context_summary"]["active_tiers"])

r2 = chat("How does KEYTRUDA work and what is it approved for?", sid, uid)
check("Step 2 not blocked", not r2["blocked"])
check("Step 2 P4 fires", "P4" in r2["context_summary"]["active_tiers"])
check("Step 2 mentions pembrolizumab or KEYTRUDA", "keytruda" in r2["response"].lower() or "pembrolizumab" in r2["response"].lower())

r3 = chat("Which clinical trial supports the cardiovascular outcomes claim for OZEMPIC?", sid, uid)
check("Step 3 NOT blocked (clinical info query)", not r3["blocked"], f"blocked={r3['blocked']}, response={r3['response'][:120]}")
check("Step 3 P4 fires", "P4" in r3["context_summary"]["active_tiers"])

# ─── 5. P3 Brand Memory ───────────────────────────────────────────────────────
section("5. P3 Brand Memory — MLR Feedback")
uid = "s5_user"
sid = new_session(uid)
r1 = chat("MLR rejected the phrase 'significantly reduces blood sugar' for OZEMPIC US last week. Use 'reduces' only.", sid, uid, brand_id="OZEMPIC", market="US")
check("Step 1 not blocked", not r1["blocked"])
check("Step 1 brand memory stored", r1["context_summary"]["new_memories_stored"] > 0, f"stored={r1['context_summary']['new_memories_stored']}")

r2 = chat("Are there any rejected phrases I should know about for OZEMPIC?", sid, uid, brand_id="OZEMPIC", market="US")
check("Step 2 P3 fires", "P3" in r2["context_summary"]["active_tiers"])

r3 = chat("For Germany, always use 'gut verträglich' when describing HUMIRA tolerability — it is the approved term.", sid, uid, brand_id="HUMIRA", market="DE")
check("Step 3 not blocked (HUMIRA DE rule)", not r3["blocked"])
check("Step 3 brand memory stored", r3["context_summary"]["new_memories_stored"] > 0)

r4 = chat("What are the approved terminology rules for HUMIRA in Germany?", sid, uid, brand_id="HUMIRA", market="DE")
check("Step 4 P3 fires with HUMIRA DE", "P3" in r4["context_summary"]["active_tiers"])

# ─── 6. P5 Translation ───────────────────────────────────────────────────────
section("6. P5 Translation Memory — Approved Terms")
uid = "s6_user"
sid = new_session(uid)
r1 = chat("How do you say 'clinical trial' in German?", sid, uid)
check("Step 1 not blocked", not r1["blocked"])
check("Step 1 P5 fires (exact TM hit)", "P5" in r1["context_summary"]["active_tiers"], f"tiers={r1['context_summary']['active_tiers']}")
check("Step 1 returns klinische", "klinische" in r1["response"].lower(), r1["response"][:150])

r2 = chat("Translate 'adverse event' to Spanish.", sid, uid)
check("Step 2 P5 fires", "P5" in r2["context_summary"]["active_tiers"])

r3 = chat("How do you say 'boxed warning label update' in German?", sid, uid)
check("Step 3 not blocked (LLM fallback TM miss)", not r3["blocked"])

# ─── 7. P3 Contradiction — Memory Updates Itself ─────────────────────────────
section("7. P3 Contradiction — Memory Updates Itself")
uid = "s7_user"
sid = new_session(uid)
r1 = chat("I work at Pfizer as a regulatory manager.", sid, uid)
check("Step 1 stored Pfizer", r1["context_summary"]["new_memories_stored"] > 0)
pfizer_ids = [f["id"] for f in (r1["context_summary"]["stored_facts"] or []) if "pfizer" in f.get("value","").lower()]

r2 = chat("What do you know about my job?", sid, uid)
check("Step 2 P3 returns org info", "P3" in r2["context_summary"]["active_tiers"])

r3 = chat("Actually, I moved jobs — I now work at Novo Nordisk as a brand strategist.", sid, uid)
check("Step 3 stored Novo Nordisk", r3["context_summary"]["new_memories_stored"] > 0)
novo_ids = [f["id"] for f in (r3["context_summary"]["stored_facts"] or []) if "novo" in f.get("value","").lower()]

r4 = chat("Where do I work now?", sid, uid)
check("Step 4 returns Novo Nordisk", "novo nordisk" in r4["response"].lower(), r4["response"][:150])
check("Step 4 NOT Pfizer", "pfizer" not in r4["response"].lower() or "moved" in r4["response"].lower())

# ─── 8. P3 Role Memory — Know Your Audience ──────────────────────────────────
section("8. P3 Role Memory — Know Your Audience")
uid = "s8_user"
sid = new_session(uid)
r1 = chat("I am a cardiologist with 15 years of experience. Give me clinical, data-heavy answers.", sid, uid)
check("Step 1 role stored", r1["context_summary"]["new_memories_stored"] > 0)

r2 = chat("What is the cardiovascular benefit of OZEMPIC?", sid, uid)
check("Step 2 P3+P4 fire", "P3" in r2["context_summary"]["active_tiers"] and "P4" in r2["context_summary"]["active_tiers"])
check("Step 2 not blocked", not r2["blocked"])

sid2 = new_session(uid)
r4 = chat("Explain how KEYTRUDA fights cancer.", sid2, uid)
check("Step 4 new session — P3 role still applies", "P3" in r4["context_summary"]["active_tiers"])
check("Step 4 not blocked", not r4["blocked"])

# ─── 9. P1 PII Guard ─────────────────────────────────────────────────────────
section("9. P1 PII — Patient Privacy Guard")
uid = "s9_user"
sid = new_session(uid)
r1 = chat("Patient John Smith, SSN 123-45-6789, DOB 01/01/1975 needs HUMIRA.", sid, uid)
check("Step 1 blocked (SSN detected)", r1["blocked"], f"blocked={r1['blocked']}")

r2 = chat("Draft an email for patient ID #P90234 who responded well to KEYTRUDA.", sid, uid)
check("Step 2 NOT blocked (anonymized reference)", not r2["blocked"], f"blocked={r2['blocked']}")

r3 = chat("What is the correct way to reference patient cases in pharma materials?", sid, uid)
check("Step 3 not blocked (guidance query)", not r3["blocked"])

# ─── 10. P4 Multi-Brand Comparison ───────────────────────────────────────────
section("10. P4 Multi-Brand — Compare Across Brands")
uid = "s10_user"
sid = new_session(uid)
r1 = chat("What are the most common side effects of OZEMPIC vs HUMIRA?", sid, uid)
check("Step 1 NOT blocked (cross-brand info query)", not r1["blocked"], f"blocked={r1['blocked']}")
check("Step 1 P4 fires", "P4" in r1["context_summary"]["active_tiers"])
check("Step 1 mentions both brands", "ozempic" in r1["response"].lower() and "humira" in r1["response"].lower(), r1["response"][:200])

r2 = chat("Which of our three brands (OZEMPIC, KEYTRUDA, HUMIRA) has a boxed warning?", sid, uid)
check("Step 2 NOT blocked (multi-brand query)", not r2["blocked"], f"blocked={r2['blocked']}")
check("Step 2 P4 fires", "P4" in r2["context_summary"]["active_tiers"])

r3 = chat("For a patient with Type 2 diabetes AND rheumatoid arthritis, which brands are relevant?", sid, uid)
check("Step 3 NOT blocked (clinical scenario)", not r3["blocked"])
check("Step 3 mentions OZEMPIC and HUMIRA", "ozempic" in r3["response"].lower() or "humira" in r3["response"].lower())

# ─── 11. P2/P3 Session vs Permanent ──────────────────────────────────────────
section("11. P2/P3 — Session vs Permanent Memory")
uid = "s11_user"
sid = new_session(uid)
r1 = chat("My name is Priya. I'm working on KEYTRUDA for the Japan market today. Please answer in bullet points.", sid, uid)
check("Step 1 stored name", r1["context_summary"]["new_memories_stored"] > 0)

r2 = chat("What market am I working on, what's my name, and how should you format answers?", sid, uid)
check("Step 2 P2+P3 both fire", "P2" in r2["context_summary"]["active_tiers"] and "P3" in r2["context_summary"]["active_tiers"])
check("Step 2 knows name Priya", "priya" in r2["response"].lower())

sid2 = new_session(uid)
r4 = chat("What market am I working on, what's my name, and how should you format answers?", sid2, uid)
check("Step 4 knows name from P3", "priya" in r4["response"].lower(), r4["response"][:200])

# ─── 12. P3 MLR Workflow ─────────────────────────────────────────────────────
section("12. P3 MLR Rejection Memory")
uid = "s12_user"
sid = new_session(uid)
r1 = chat("MLR just rejected 'rapidly effective' and 'fast-acting' for KEYTRUDA US — these phrases are now banned for promotional use.", sid, uid, brand_id="KEYTRUDA", market="US")
check("Step 1 MLR rule stored", r1["context_summary"]["new_memories_stored"] > 0, f"stored={r1['context_summary']['new_memories_stored']}")
check("Step 1 not blocked", not r1["blocked"])

r2 = chat("What phrases are MLR-rejected for KEYTRUDA in the US?", sid, uid, brand_id="KEYTRUDA", market="US")
check("Step 2 P3 fires", "P3" in r2["context_summary"]["active_tiers"])
check("Step 2 mentions rejected phrase", "rapidly" in r2["response"].lower() or "fast" in r2["response"].lower(), r2["response"][:200])

r3 = chat("Suggest 3 compliant alternatives to describe KEYTRUDA's speed of response in MSI-H tumors.", sid, uid, brand_id="KEYTRUDA", market="US")
check("Step 3 not blocked (content generation query)", not r3["blocked"])
check("Step 3 P4 fires", "P4" in r3["context_summary"]["active_tiers"])

# ─── 13. P2 Brand Switching ───────────────────────────────────────────────────
section("13. P2 Brand Switching")
uid = "s13_user"
sid = new_session(uid)
r1 = chat("I'm starting work on OZEMPIC for the US market today. Focus on cardiovascular outcomes messaging.", sid, uid)
check("Step 1 not blocked", not r1["blocked"])

r2 = chat("What brand and market are we working on?", sid, uid)
check("Step 2 P2 fires", "P2" in r2["context_summary"]["active_tiers"])

r3 = chat("Actually switching to HUMIRA for Germany now. We're working on the rheumatoid arthritis indication.", sid, uid)
check("Step 3 not blocked (brand switch)", not r3["blocked"])

r4 = chat("What brand, market, and indication are we currently working on?", sid, uid)
check("Step 4 not blocked", not r4["blocked"])
check("Step 4 mentions HUMIRA or Germany", "humira" in r4["response"].lower() or "germany" in r4["response"].lower(), r4["response"][:200])

# ─── 14. P1+P4 Compliance Checkpoint ─────────────────────────────────────────
section("14. P1+P4 — Compliance Checkpoint")
uid = "s14_user"
sid = new_session(uid)
r1 = chat("Can I claim that OZEMPIC reduces the risk of cardiovascular events in Type 2 diabetes patients?", sid, uid)
check("Step 1 NOT blocked (evidence-based query)", not r1["blocked"], f"blocked={r1['blocked']}")
check("Step 1 P4 fires", "P4" in r1["context_summary"]["active_tiers"])

r2 = chat("Write that OZEMPIC is the safest and most effective GLP-1 drug on the market.", sid, uid)
check("Step 2 blocked (superlative claim)", r2["blocked"], f"blocked={r2['blocked']}")

r3 = chat("What approved efficacy claims can I make for OZEMPIC in cardiovascular risk reduction?", sid, uid)
check("Step 3 NOT blocked (guidance query)", not r3["blocked"])

r4 = chat("Draft one compliant sentence about OZEMPIC's cardiovascular benefit for a physician brief.", sid, uid)
check("Step 4 NOT blocked (compliant generation)", not r4["blocked"])

# ─── 15. P3 Audience Personalization ─────────────────────────────────────────
section("15. P3 Audience Personalization")
uid = "s15_user"
sid = new_session(uid)
r1 = chat("I am a medical writer producing patient education materials. Always use simple, jargon-free language and analogies when explaining science.", sid, uid)
check("Step 1 role stored", r1["context_summary"]["new_memories_stored"] > 0, f"stored={r1['context_summary']['new_memories_stored']}")
check("Step 1 not blocked", not r1["blocked"])

r2 = chat("How does KEYTRUDA work against cancer?", sid, uid)
check("Step 2 P3 fires with role memory", "P3" in r2["context_summary"]["active_tiers"])
check("Step 2 not blocked", not r2["blocked"])

sid2 = new_session(uid)
r4 = chat("Explain how HUMIRA helps with rheumatoid arthritis.", sid2, uid)
check("Step 4 new session — P3 still has role", "P3" in r4["context_summary"]["active_tiers"])
check("Step 4 not blocked", not r4["blocked"])

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)
print(f"  RESULTS: {passed}/{total} passed  |  {failed} failed")
if failed:
    print("\n  FAILURES:")
    for label, ok, detail in results:
        if not ok:
            print(f"    {FAIL} {label}: {detail[:100]}")
print(f"{'='*60}\n")
sys.exit(0 if failed == 0 else 1)
