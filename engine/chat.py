"""Guideline-grounded chat for Axon.

The retrieval step happens before the model call and only searches the
selected hospital's loaded guide. The model receives those retrieved rows as
its sole reference material and its citations are checked before returning.
"""
import json
import os
import re

from openai import OpenAI


def _tokens(value):
    return {part for part in re.findall(r"[a-z0-9]+", str(value).lower()) if len(part) > 2}


def retrieve(guide, question, encounter_state=None, limit=8):
    """Small-corpus retrieval over one hospital's guideline rows."""
    encounter_state = encounter_state or {}
    query_words = _tokens(question)
    state_words = _tokens(" ".join(
        key.replace("_", " ") for key, value in encounter_state.items() if value
    ))

    ranked = []
    for record in guide.records():
        field_words = _tokens(record.field)
        value_words = _tokens(record.value)
        score = 5 * len(query_words & field_words) + len(query_words & value_words)
        score += 2 * len(state_words & field_words)
        # These clinical workflow fields are useful anchors for open-ended questions.
        if record.field.lower() in {"lvo protocol", "thrombolytic", "order entry", "order set name",
                                    "consult completion rule", "required note title", "rounding timing"}:
            score += 1
        ranked.append((score, record))

    ranked.sort(key=lambda item: (-item[0], item[1].field.lower()))
    return ranked[:limit]


def _source(identifier, record):
    return {
        "id": identifier,
        "hospital_id": record.hospital_id,
        "field": record.field,
        "value": record.value,
        "last_verified": record.last_verified.isoformat(),
        "source_type": "guideline",
    }


def _norm_value(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower().rstrip("."))


def _incoming_storyboards(hospital_id, rows):
    """Normalize browser imports and keep them scoped to one hospital."""
    notes = []
    for row in (rows or [])[:30]:
        if not isinstance(row, dict) or str(row.get("hospital_id", "")).strip() != hospital_id:
            continue
        field = str(row.get("field", "")).strip()[:120]
        value = str(row.get("storyboard_value", row.get("value", ""))).strip()[:1000]
        if not field or not value:
            continue
        notes.append({
            "hospital_id": hospital_id,
            "field": field,
            "value": value,
            "updated": str(row.get("storyboard_updated", row.get("updated", "")))[:40],
            "note": str(row.get("note", ""))[:600],
        })
    return notes


def retrieve_storyboards(kb, guide, question, encounter_state=None, imported=None, limit=8):
    """Retrieve bundled and browser-imported storyboards for this hospital.

    For the same field, the browser-imported note wins so a newly uploaded
    storyboard can supersede the bundled demo note without a server restart.
    """
    query_words = _tokens(question)
    state_words = _tokens(" ".join(key.replace("_", " ") for key, value in
                                    (encounter_state or {}).items() if value))
    by_field = {note.field.lower(): {
        "hospital_id": note.hospital_id, "field": note.field, "value": note.value,
        "updated": note.updated, "note": note.note,
    } for (hid, _), note in kb.storyboard.items() if hid == guide.id}
    for note in _incoming_storyboards(guide.id, imported):
        by_field[note["field"].lower()] = note

    ranked = []
    for note in by_field.values():
        field_words = _tokens(note["field"])
        value_words = _tokens(note["value"] + " " + note["note"])
        score = 5 * len(query_words & field_words) + len(query_words & value_words)
        score += 2 * len(state_words & field_words)
        if score:
            ranked.append((score, note))
    ranked.sort(key=lambda item: (-item[0], item[1]["field"].lower()))
    return ranked[:limit]


def _storyboard_source(identifier, note, guide):
    guide_record = guide.get(note["field"])
    conflict = bool(guide_record and _norm_value(note["value"]) != _norm_value(guide_record.value))
    return {
        "id": identifier,
        "hospital_id": note["hospital_id"],
        "field": note["field"],
        "value": note["value"],
        "updated": note["updated"],
        "note": note["note"],
        "source_type": "storyboard",
        "conflict": conflict,
        "guide_value": guide_record.value if conflict else "",
    }


def chat_answer(kb, hospital_id, question, encounter_state=None, local_time=None, conversation=None,
                storyboard_notes=None):
    guide = kb.guides.get(hospital_id)
    if guide is None:
        return {"error": "Guidance is unavailable for this hospital.", "status": 404}
    if not os.getenv("OPENAI_API_KEY"):
        return {"error": "Chat is not configured.", "status": 503}

    question = str(question or "").strip()
    if not question:
        return {"error": "Enter a question for Axon.", "status": 400}
    question = question[:1200]
    rows = retrieve(guide, question, encounter_state)
    storyboard_rows = retrieve_storyboards(kb, guide, question, encounter_state, storyboard_notes)
    sources = [_source(f"S{index + 1}", record) for index, (_, record) in enumerate(rows)]
    sources.extend(_storyboard_source(f"S{len(sources) + index + 1}", note, guide)
                   for index, (_, note) in enumerate(storyboard_rows))
    source_text = "\n".join(
        f"{source['id']} | {source['source_type']} | {source['field']} | {source['value']} | "
        f"{'CONFLICTS WITH GUIDE: ' + source['guide_value'] if source.get('conflict') else source.get('last_verified', source.get('updated', ''))}"
        for source in sources
    )
    state = {str(key)[:80]: value for key, value in (encounter_state or {}).items()}
    history = [
        {"role": str(item.get("role", "user"))[:16], "content": str(item.get("content", ""))[:1200]}
        for item in (conversation or [])[-6:] if isinstance(item, dict)
    ]

    instructions = """You are Axon, a hospital workflow assistant working with synthetic demo data.
Answer operational questions using ONLY the retrieved guideline and storyboard sources below for the selected hospital.
Do not use general medical knowledge, diagnose, determine treatment eligibility, calculate doses, or invent a protocol.
If the answer is not supported by the sources, say it is not specified in this hospital guide.
When a storyboard source conflicts with a guideline source for the same field, prefer the storyboard for the operational answer, explicitly call out the conflict, and cite BOTH source IDs.
Never imply that a storyboard overrides a hard safety stop; instead say the conflict requires review.
Be concise and practical. Cite every factual guideline claim with one or more source IDs.
Return only JSON matching the requested schema."""
    payload = {
        "hospital": {"id": guide.id, "name": guide.name},
        "encounter_state": state,
        "hospital_local_time": local_time,
        "conversation": history,
        "question": question,
        "retrieved_guideline_sources": source_text,
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "string"}},
            "missing_information": {"type": "array", "items": {"type": "string"}},
            "caution": {"type": "string"},
        },
        "required": ["answer", "citations", "missing_information", "caution"],
    }
    try:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        result = client.responses.create(
            model=os.getenv("AXON_OPENAI_MODEL", "gpt-5-mini"),
            reasoning={"effort": "low"},
            store=False,
            instructions=instructions,
            input=json.dumps(payload),
            text={"format": {"type": "json_schema", "name": "axon_guideline_answer", "strict": True,
                              "schema": schema}},
        )
        parsed = json.loads(result.output_text)
    except Exception:
        return {"error": "The AI guideline service is temporarily unavailable.", "status": 502}

    valid_ids = {source["id"] for source in sources}
    cited = [citation for citation in parsed.get("citations", []) if citation in valid_ids]
    cited_sources = [source for source in sources if source["id"] in cited]
    return {
        "answer": str(parsed.get("answer", ""))[:4000],
        "sources": cited_sources,
        "missing_information": parsed.get("missing_information", [])[:4],
        "caution": str(parsed.get("caution", ""))[:500],
        "retrieval": {"hospital_id": guide.id, "source_count": len(sources)},
        "status": 200,
    }
