# engine/answers.py
# PURPOSE: ON-DEMAND ANSWERS (secondary deliverable) - the chat box.
#   question -> pick ONE guide field of the CURRENT hospital -> answer with that field's own words
#   + one honest STATUS + the SOURCE. The AI never writes the answer, so it cannot invent a rule.

import re                                    # text patterns

from . import llm                            # optional cloud AI fallback (only picks a field NAME)
from .guides import to_local, view           # Step 3
from .logic import lvo, rounding, schedule_status, signoff_checks, stale_note   # Step 4 (same logic as nudges)

# the 6 statuses from the brief, with display labels
STATUS_LABEL = {"answered": "Answered", "not_in_guide": "Not in guide", "time_dependent": "Time-dependent",
                "stale": "Stale", "conflict": "Conflict", "hard_stop": "Hard stop"}
_SHORT_OK = {"ct", "ai", "mri", "eeg", "ehr", "tee", "vpn", "lvo", "pt", "ot"}   # short words still worth matching
_STOP = {"the", "and", "for", "what", "who", "how", "when", "where", "does", "can", "this", "hospital"}   # ignore these


def norm_status(s):
    """'time dependent' / 'time-dependent' / 'time_dependent' -> 'time_dependent' (for comparing with the answer key)"""
    return str(s).strip().lower().replace("-", " ").replace(" ", "_")


# ---------- 1. ROUTING: which field answers this question? ----------
def route(kb, question, guide):
    q = question.lower()
    # Try 1: keyword patterns from data/field_registry.json  (e.g. "mix" -> Thrombolytic Mix Model)
    best, score = None, 0
    for intent in kb.registry:
        sc = sum(w for pat, w in intent["patterns"] if re.search(pat, q))   # add weights of every pattern that matches
        if sc > score:
            best, score = intent, sc                                         # keep the highest-scoring field
    if best:
        return {**best, "via": "keywords"}
    # Try 2 (LIVE TEST safety): match words against THIS hospital's own field names,
    #        so a brand-new field like "Neurosurgery Coverage" still works with no code change.
    words = set(re.findall(r"[a-z0-9]+", q))
    for rec in guide.records():
        toks = {t for t in re.findall(r"[a-z0-9]+", rec.field.lower())
                if (len(t) >= 3 or t in _SHORT_OK) and t not in _STOP}
        sc = len(words & toks)
        if sc > score:
            best, score = {"field": rec.field, "via": "field name"}, sc
    if best:
        return best
    # Try 3 (optional): ask a cloud AI to PICK a field name from this hospital's list. Off unless keys are set.
    picked = llm.pick_field(question, [r.field for r in guide.records()])
    return {"field": picked, "via": "llm"} if picked else None


def _result(status, text, guide, field=None, sources=None, flags=None, via=None):
    """Every answer has the same shape (easy for George's chat box to display)."""
    return {"status": status, "label": STATUS_LABEL[status], "answer": text, "hospital_id": guide.id if guide else None,
            "field": field, "sources": sources or [], "flags": flags or [], "routed_by": via}


# ---------- 2. ANSWERING ----------
def answer(kb, hospital_id, question, local_time, provider_timezone=None, charge_entered=False,
           plan_confirmed=False):
    guide = kb.guides.get(hospital_id)
    if guide is None:                                            # unknown hospital: say so, never borrow
        return _result("not_in_guide", "Guidance unavailable for this hospital. The caselog keeps working; "
                       "no answer is borrowed from another hospital.", None)
    dt = to_local(local_time, guide)                             # hospital's clock
    intent = route(kb, question, guide)
    if intent is None:                                           # couldn't match any field -> honest "not in guide"
        return _result("not_in_guide", f"I couldn't match this to a field in {guide.name}'s guide. "
                       "Not answered from any other hospital.", guide)
    kind, field, via = intent.get("kind", "field"), intent.get("field"), intent.get("via")

    # 2a. "Can I sign off now?"  -> same checks as the hard-stop nudge (V10)
    if kind == "sign_off":
        checks = signoff_checks(kb, guide, dt, charge_entered, plan_confirmed)
        if checks:
            return _result("hard_stop", "Not yet. " + " ".join(m for m, _ in checks), guide, "Sign-off",
                           [fv.rec.source() for _, fv in checks], via=via)
        return _result("answered", "No sign-off requirements are listed in this hospital's guide.", guide,
                       "Sign-off", via=via)

    # 2b. "Is the rounding window open?" -> combines 2 fields + provider's own clock (V17)
    if kind == "rounding_window":
        r = rounding(kb, guide, dt, provider_timezone)
        if r is None:
            return _result("not_in_guide", "Rounding hours are not available in this hospital's guide.", guide,
                           "Rounding Timing", via=via)
        status, msg, fvs, _, _ = r
        flags = ["stale"] if any(f.stale for f in fvs) else []
        if flags:
            msg += " " + " ".join(stale_note(f) for f in fvs if f.stale)
        if status == "answered" and flags:
            status = "stale"
        return _result(status, msg, guide, "Rounding Timing", [f.rec.source() for f in fvs], flags, via)

    # 2c. LVO questions -> exactly the same logic as the LVO nudge (V02, V06, V08, V09)
    if kind == "lvo":
        r = lvo(kb, guide, dt)
        if r is None:
            return _not_in_guide(guide, "LVO Protocol", via)
        status, msg, src, flags = r
        fv = view(kb, guide, "LVO Protocol", dt)
        if fv.stale:
            msg += " " + stale_note(fv)
            status = "stale" if status == "answered" else status
        return _result(status, msg, guide, "LVO Protocol", src, flags, via)

    # 2d. Any other field
    fv = view(kb, guide, field, dt)
    if fv is None:                                               # V14, V20: field missing at this hospital
        return _not_in_guide(guide, field, via)
    src, flags = [fv.rec.source()], (["stale"] if fv.stale else [])
    if fv.conflict:                                              # V12: show BOTH values with sources
        sb = fv.conflict
        msg = (f"Sources disagree — confirm locally. On-call guide: '{fv.value}' (source: {guide.id} · {fv.rec.field}, "
               f"verified {fv.rec.last_verified}). Hospital storyboard: '{sb.value}' (updated {sb.updated}).")
        return _result("conflict", msg, guide, fv.rec.field,
                       src + [{"hospital_id": guide.id, "field": f"Storyboard · {sb.field}", "last_verified": sb.updated}],
                       flags + ["conflict"], via)
    status, msg = schedule_status(fv, dt)                        # open / closed / not listed / undefined / plain text
    if kind == "order_set":                                      # V07: also say whether the teleneurologist orders at all
        oe = view(kb, guide, "Order Entry", dt)
        if oe:
            msg += f" Order entry scope here: {oe.value}."
            src.append(oe.rec.source())
    if fv.stale:                                                 # V13: answer + "possibly out of date"
        if status == "answered":
            status = "stale"
        msg += " " + stale_note(fv)
    return _result(status, msg, guide, fv.rec.field, src, flags, via)


def _not_in_guide(guide, field, via):
    return _result("not_in_guide", f"Not available in {guide.name}'s guide ({field}). "
                   "Not filled in from any other hospital.", guide, field, via=via)
