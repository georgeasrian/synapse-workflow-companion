# api.py
# PURPOSE: the "door" George's website knocks on. It wraps our engine in a small web API.
#
#   Run:   uvicorn api:app --reload --port 8000
#   Docs:  http://localhost:8000/docs   <- click and try every endpoint in your browser
#   Panel: http://localhost:8000/       <- reference nudge panel (static/nudge_panel.html)
#
# George's screen sends Sevaro's encounter context (encounter_context_example.json) on EVERY
# caselog step/field change to POST /nudges, and draws whatever comes back.

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException               # the web framework
from fastapi.middleware.cors import CORSMiddleware       # lets a website on another domain call us
from fastapi.responses import FileResponse               # to serve the HTML panel
from pydantic import BaseModel                           # describes the JSON we accept (and validates it)

from engine.answers import answer                        # Step 6
from engine.chat import chat_answer                      # Guideline-grounded OpenAI chat
from engine.guides import KB, norm                       # Step 3
from engine.nudges import run                            # Step 5

app = FastAPI(title="Workflow Companion - Nudge API", version="1.0")
# CORS: browsers block calls to other domains unless the API allows it. "*" = allow George's site (any domain).
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

kb = KB()                                   # load all guides ONCE when the server starts (fast: < 500 ms per call)
STATIC = Path(__file__).parent / "static"
# fields we expect most hospitals to have - used only for the live-test coverage report
CORE_FIELDS = ["Video Eval Location", "Thrombolytic", "Thrombolytic Mix Model", "LVO Protocol", "Wake Up Protocol",
               "Order Entry", "Order Set Name", "Charge Entry", "Required Note Title", "Consult Completion Rule",
               "When Do We Round?", "Rounding Timing", "Rounding Orders", "CT Perfusion", "AI", "EEG"]


# ---------- 1. The shapes of JSON we accept (FastAPI checks them and shows them in /docs) ----------
class FieldEvent(BaseModel):
    field: str                    # e.g. "lvo_present", "complete_clicked", "encounter"
    value: object = None          # e.g. true, "Unknown", "opened"


class EncounterContext(BaseModel):           # exactly Sevaro's encounter_context_example.json
    hospital_id: str
    consult_type: str = "Stroke"             # Stroke | General Neuro | Rounding
    encounter_type: str | None = None        # e.g. Acute
    caselog_step: str                        # Intake | History | Imaging | Recommendation | Note | Sign-off | Rounding
    field_event: FieldEvent
    local_time: str                          # "2026-03-17T19:30:00-05:00" or "2026-03-17T19:30" (hospital-local)
    local_timezone: str | None = None
    provider_timezone: str | None = "America/New_York"
    charge_entered: bool = False
    plan_confirmed: bool = False


class Question(BaseModel):                   # for the chat box
    hospital_id: str
    question: str
    local_time: str
    provider_timezone: str | None = "America/New_York"
    charge_entered: bool = False
    plan_confirmed: bool = False


class ChatQuestion(BaseModel):
    """The browser sends encounter state; the server retrieves the guide itself."""
    hospital_id: str
    question: str
    local_time: str | None = None
    encounter_state: dict = {}
    conversation: list[dict] = []
    # Storyboard uploads are session-local in the browser. Only notes for the
    # selected hospital are sent here and may be retrieved for this answer.
    storyboard_notes: list[dict] = []


# ---------- 2. Endpoints (the URLs George's site can call) ----------
@app.get("/health")
def health():
    """Quick 'is it alive?' check - used after deploying."""
    return {"ok": True, "hospitals": len(kb.guides), "rules": len(kb.rules)}


@app.get("/hospitals")
def hospitals():
    """List of hospitals for the picker in the caselog header."""
    return [{"hospital_id": g.id, "hospital_name": g.name, "timezone": str(g.tz), "fields": len(g.fields)}
            for g in sorted(kb.guides.values(), key=lambda g: g.id)]


@app.post("/nudges")
def nudges(ctx: EncounterContext):
    """MAIN CALL. On every caselog step/field change. An empty 'nudges' list means stay quiet - that's correct."""
    return run(kb, ctx.model_dump())         # model_dump() turns the checked JSON into a plain dict for Step 5


@app.post("/ask")
def ask(q: Question):
    """Chat box question. Always returns status + sources."""
    return answer(kb, q.hospital_id, q.question, q.local_time, q.provider_timezone, q.charge_entered,
                  q.plan_confirmed)


@app.post("/chat")
@app.post("/api/chat")
def chat(q: ChatQuestion):
    """OpenAI-backed RAG chat over the selected guide and storyboard notes."""
    result = chat_answer(kb, q.hospital_id, q.question, q.encounter_state, q.local_time,
                         q.conversation, q.storyboard_notes)
    status = result.pop("status", 200)
    if status >= 400:
        raise HTTPException(status, result.get("error", "Chat is unavailable."))
    return result


@app.post("/hospitals")
def add_hospital(guide: dict):
    """LIVE TEST: judges' new guide (hospital_guides.json format) -> usable immediately. Data change, no code change."""
    added = kb.load_guides(guide)                         # same loader as startup (Step 3)
    if not added:
        raise HTTPException(400, "No hospitals found in that JSON. Expected the hospital_guides.json format.")
    today = kb.reference_date or datetime.now().date()   # the dataset's "today" (2026-03-17), not the real clock
    reports = []
    for hid in added:                                     # coverage report: what this new guide has / lacks
        g = kb.guides[hid]
        reports.append({
            "hospital_id": hid, "hospital_name": g.name, "timezone": str(g.tz) if g.tz else None,
            "fields": len(g.fields),
            "missing_core_fields": [f for f in CORE_FIELDS if not g.get(f)],      # these will answer "not in guide"
            "stale_fields": [r.field for r in g.records() if (today - r.last_verified).days > kb.stale_days],
            "new_field_names": [r.field for r in g.records()                     # fields we've never seen before
                                if norm(r.field) not in {norm(f) for f in CORE_FIELDS}
                                and norm(r.field) not in {norm(x.get("field", "")) for x in kb.registry}],
        })
    return {"added": added, "coverage": reports}


@app.get("/")
def demo_panel():
    """Reference nudge panel (plain HTML/JS) so you can click through the caselog in a browser."""
    return FileResponse(STATIC / "nudge_panel.html")
