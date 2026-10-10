"""Scores the engine against Sevaro's OFFICIAL files (data/official/):
  nudge_scenarios.json  - N1-N9, written as readable text ("LVO present = Yes", "Tue 14:00 Mountain")
  validation_set.csv    - V01-V20 with expected_status
Expected tier/status come from the official files. data/check_nudges.json and data/check_answers.json add
extra wording checks (e.g. N2 must not mention activating the EVT team)."""
import csv
import json
import re
from datetime import date, timedelta

from .answers import answer, norm_status
from .nudges import run

REF_DATE = date(2026, 3, 17)          # encounter_reference_date in hospital_guides.json (a Tuesday)
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ZONE_WORDS = {"eastern": "America/New_York", "et": "America/New_York", "central": "America/Chicago",
              "ct": "America/Chicago", "mountain": "America/Denver", "mt": "America/Denver",
              "pacific": "America/Los_Angeles", "pt": "America/Los_Angeles"}
# caselog wording in the official scenarios -> engine field names (same names the UI sends)
EVENT_FIELDS = {"lvo present": "lvo_present", "large vessel occlusion present": "lvo_present",
                "last known well": "last_known_well", "thrombolytic given": "thrombolytic_given",
                "cta done": "cta_done", "allergies entered": "allergies", "allergies": "allergies",
                "complete clicked": "complete_clicked", "encounter opened": "encounter",
                "note being created": "note_created", "assessment": "assessment"}
TIER_WORDS = {"hard stop": "hard_stop", "advisory": "advisory", "info": "info", "no nudge": None}


def _value(v):
    v = v.strip()
    return {"yes": True, "no": False}.get(v.lower(), v)


def parse_event(text):
    """'LVO present = Yes' -> ctx bits. Handles 'Complete clicked; charge not entered', 'Allergies entered: none'."""
    extra = {}
    if re.search(r"charge not entered", text, re.I):
        extra["charge_entered"] = False
    main = text.split(";")[0].strip()
    m = re.match(r"\s*(.+?)\s*(?:=|:)\s*(.+)$", main)
    label, value = (m.group(1), _value(m.group(2))) if m else (main, True)
    field = EVENT_FIELDS.get(label.lower(), re.sub(r"\W+", "_", label.lower()).strip("_"))
    if field == "encounter":
        value = "opened"
    return {"field": field, "value": value}, extra


def parse_short_time(text):
    """'Tue 19:30 Central' -> '2026-03-17T19:30' (day placed in the reference week)."""
    m = re.match(r"\s*(\w{3})\w*\s+(\d{1,2}):(\d{2})", text)
    d = REF_DATE + timedelta(days=DAYS.index(m.group(1).lower()) - REF_DATE.weekday())
    return f"{d.isoformat()}T{int(m.group(2)):02d}:{m.group(3)}"


def parse_validation_time(text):
    """'Tue 2026-03-17 08:15 local (10:15 ET)' -> ('2026-03-17T08:15', 'America/New_York')"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})", text)
    z = re.search(r"\(\s*\d{1,2}:\d{2}\s+([A-Za-z]+)\s*\)", text)
    ptz = ZONE_WORDS.get(z.group(1).lower()) if z else None
    return f"{m.group(1)}T{int(m.group(2)):02d}:{m.group(3)}", ptz


def expected_tier(text):
    t = text.strip().lower()
    for word, tier in TIER_WORDS.items():
        if t.startswith(word):
            return tier
    return "unknown"


def _checks(kb, name):
    p = kb.data_dir / name
    return {c["id"]: c for c in json.loads(p.read_text())} if p.exists() else {}


def _text(n):
    return " ".join([n["title"], n["message"]] + n.get("details", [])).lower()


def official_nudge_contexts(kb):
    for s in json.loads((kb.data_dir / "official" / "nudge_scenarios.json").read_text()):
        ev, extra = parse_event(s["field_event"]) if isinstance(s["field_event"], str) else (s["field_event"], {})
        ctx = {"hospital_id": s["hospital_id"], "consult_type": s["consult_type"], "caselog_step": s["caselog_step"],
               "field_event": ev, "local_time": parse_short_time(s["local_time"]),
               "provider_timezone": "America/New_York", "charge_entered": False, **extra}
        yield s, ctx


def run_nudge_scenarios(kb):
    checks, rows = _checks(kb, "check_nudges.json"), []
    for s, ctx in official_nudge_contexts(kb):
        res = run(kb, ctx)
        nudges, want = res["nudges"], expected_tier(s["expected"])
        if want is None:
            ok, note = not nudges, "" if not nudges else f"{len(nudges)} unexpected nudge(s)"
        else:
            hit = [n for n in nudges if n["tier"] == want]
            ok, note = len(nudges) == 1 and bool(hit), ""
            if not ok:
                note = f"got {[n['tier'] for n in nudges]}"
            else:
                c = checks.get(s["id"], {})
                miss = [m for m in c.get("must_include", []) if m.lower() not in _text(hit[0])]
                bad = [m for m in c.get("must_exclude", []) if any(m.lower() in _text(n) for n in nudges)]
                ok = not miss and not bad
                note = (f"missing {miss} " if miss else "") + (f"should not say {bad}" if bad else "")
        rows.append({"pass": ok, "id": s["id"], "hospital": s["hospital_id"], "event": s["field_event"],
                     "time": s["local_time"], "expected": s["expected"],
                     "got": " | ".join(f"{n['tier']}: {n['message']}" for n in nudges) or "(silent)",
                     "ms": res["ms"], "note": note})
    return rows


def run_validation(kb):
    checks, rows = _checks(kb, "check_answers.json"), []
    with open(kb.data_dir / "official" / "validation_set.csv", newline="") as f:
        for v in csv.DictReader(f):
            lt, ptz = parse_validation_time(v["encounter_local_time"])
            r = answer(kb, v["hospital_id"], v["question"], lt, ptz or "America/New_York")
            c = checks.get(v["id"], {})
            t = r["answer"].lower()
            status_ok = norm_status(r["status"]) == norm_status(v["expected_status"])
            miss = [m for m in c.get("must_include", []) if m.lower() not in t]
            bad = [m for m in c.get("must_exclude", []) if m.lower() in t]
            rows.append({"pass": status_ok and not miss and not bad, "id": v["id"], "hospital": v["hospital_id"],
                         "question": v["question"], "expected": v["expected_status"], "got": r["status"],
                         "field": r["field"], "answer": r["answer"], "expected_answer": v["expected_answer"],
                         "note": ("" if status_ok else "wrong status ") + (f"missing {miss} " if miss else "")
                         + (f"should not say {bad}" if bad else "")})
    return rows
