# engine/logic.py
# PURPOSE: the CLINICAL INTERPRETATION of guide fields. Both the nudges (Step 5) and the chat answers
#          (Step 6) call these same functions, so a nudge and an answer can never disagree.
# Every function returns a STATUS from the brief: answered | not_in_guide | time_dependent | stale | conflict | hard_stop

import re                                   # text patterns
from zoneinfo import ZoneInfo               # to show the provider's own clock (V17)

from .guides import view                    # Step 3: the ONLY safe way to read a field
from .schedule import (ALL_DAYS, DAY_LONG, Schedule, Window, evaluate, hm, parse_days,
                       parse_schedule, parse_time_range, when)   # Step 2: time logic

STALE_TXT = "⚠ Stale: last verified {d}, more than 180 days before this encounter — possibly out of date."


def stale_note(fv):
    """The warning line we append whenever a field is stale."""
    return STALE_TXT.format(d=fv.rec.last_verified.isoformat())


def _sentences(text):
    """Split guide text into sentences: 'A. B. C.' -> ['A.', 'B.', 'C.']"""
    return [s.strip() for s in re.split(r"(?<=\.)\s+", text.strip()) if s.strip()]


# =====================================================================================
# 1. LVO PATHWAY  (N1, N2, V02, V06, V08, V09) - the most important function for the demo
# =====================================================================================
def lvo(kb, guide, dt):
    """What to do for a large vessel occlusion at THIS hospital at THIS hour.
    Returns (status, message, sources, flags), or None if the hospital has no LVO Protocol field."""
    fv = view(kb, guide, "LVO Protocol", dt)
    if fv is None:
        return None                                              # caller will say "not in guide"
    text, low = fv.value, fv.value.lower()
    src, flags = [fv.rec.source()], (["stale"] if fv.stale else [])
    sents = _sentences(text)
    outside = [s for s in sents if s.lower().startswith("outside")]        # the "Outside coverage, ..." sentence
    inside = [s for s in sents[1:] if not s.lower().startswith("outside")] # the "During coverage, ..." sentence(s)

    # Case A: hospital can't do thrombectomy at all -> just give the transfer pathway (N1: Bluewater)
    if "not thrombectomy capable" in low or "not evt capable" in low:
        return "answered", text, src, flags

    s = parse_schedule(text)

    # Case B: capable 24/7 -> always the in-house pathway (Redwood)
    if s.kind == "always":
        return "answered", text, src, flags

    # Case C: capable only in a window, e.g. "Mon-Fri 0700-1900" (Highland Valley)
    if s.kind == "windows":
        ev = evaluate(s, dt, closed_lists=True)
        win = s.windows[0].text.split(".")[0]                    # "Thrombectomy capable Mon-Fri 0700-1900"
        if ev.state == "open":                                   # inside the window -> in-house EVT pathway
            return "answered", f"Inside the thrombectomy coverage window ({win}; now {when(dt)}). " + " ".join(inside), src, flags
        # OUTSIDE the window (N2: Tue 19:30, V09: Saturday) -> transfer pathway ONLY.
        # We deliberately DROP the "activate the EVT team" sentence: the brief says we must not suggest it.
        nxt = f" Coverage resumes {DAY_LONG[ev.next_open.weekday()]} {hm(ev.next_open)}." if ev.next_open else ""
        return ("time_dependent",
                f"No — outside the thrombectomy coverage window ({win}; now {when(dt)}). "
                + " ".join(outside) + " The in-coverage pathway does not apply now." + nxt, src, flags)

    # Case D: "capable during staffed coverage" but the guide never gives the hours (V08: Cedar Ridge)
    # -> show BOTH branches and say the hours are unknown. Never borrow hours from another hospital.
    return ("time_dependent",
            "The pathway depends on staffed coverage, but this guide does not give the coverage hours, "
            "so it cannot say which branch applies at " + when(dt) + ". "
            "If within coverage: " + " ".join(inside) + " If outside coverage: " + " ".join(outside)
            + " Confirm coverage with the hospital; hours are not borrowed from any other hospital.", src, flags)


# =====================================================================================
# 2. "IS IT AVAILABLE NOW?" for any schedule-like field (EEG, CT Perfusion, MRI, Mix Model...)
# =====================================================================================
def schedule_status(fv, dt):
    """Returns (status, message). Uses Step 2's evaluate() and turns the result into words."""
    v = fv.value
    s = parse_schedule(v)
    ev = evaluate(s, dt)
    if ev.state == "day_not_listed":                             # V04: "Tue/Thu" asked on Friday
        return "not_in_guide", (f"The guide only lists '{v}'. {DAY_LONG[dt.weekday()]} availability is not "
                                f"provided. Do not assume.")
    if ev.state == "closed":                                     # V16: Mon-Fri asked on Saturday
        nxt = f" Next available {DAY_LONG[ev.next_open.weekday()]} {hm(ev.next_open)}." if ev.next_open else ""
        return "time_dependent", f"No — not available now ({when(dt)}). Guide: {v} only.{nxt}"
    if ev.state == "undefined":                                  # V18: "during staffed hours", hours not given
        return "time_dependent", (f"Depends on staffed/coverage hours that this guide does not define. Guide says: "
                                  f"'{v}'. It is {when(dt)}; the cutoff is not in the guide, so do not assume one.")
    if ev.state == "open":                                       # inside the window
        return "answered", f"Yes — available now ({when(dt)}). Guide: {v}."
    if ev.state == "never":                                      # V05: CT perfusion "No"
        return "answered", "No." if v.strip().lower() in ("no", "none") else f"No. Guide: {v}."
    if ev.state == "always":                                     # "24/7"
        return "answered", f"Yes — {v}."
    # plain text field (e.g. "Patient room"): just return the guide's own words, ending with a period
    return "answered", v if v.rstrip().endswith((".", "!", "?", '"', "]")) else v + "."


# =====================================================================================
# 3. SIGN-OFF CHECKS -> HARD STOPS  (N5, N7, V10)
# =====================================================================================
def signoff_checks(kb, guide, dt, charge_entered=False, plan_confirmed=False):
    """Returns a list of (message, field) for everything that must block 'Complete consult'. Empty list = OK."""
    out = []
    ce = view(kb, guide, "Charge Entry", dt)
    if ce and ce.value.strip().lower().startswith("yes") and not charge_entered:   # N5: Silver Oak needs a charge
        out.append(("Charge required before sign-off: enter the tele-neurology encounter charge "
                    f"(guide: '{ce.value}').", ce))
    cr = view(kb, guide, "Consult Completion Rule", dt)
    if cr and not plan_confirmed:                                # N7: Meadowlands needs the hospital to confirm the plan
        out.append((f"Completion rule: {cr.value}.", cr))
    return out


# =====================================================================================
# 4. ROUNDING WINDOW  (N9, V17) - combines two fields: "When Do We Round?" (days) + "Rounding Timing" (hours)
# =====================================================================================
def rounding(kb, guide, dt, provider_tz=None):
    """Returns (status, message, fieldviews, eval, days_text), or None if neither field exists."""
    days_fv = view(kb, guide, "When Do We Round?", dt)          # e.g. "Monday-Friday"
    time_fv = view(kb, guide, "Rounding Timing", dt)            # e.g. "0700-1100 Central Time"
    if not days_fv and not time_fv:
        return None
    days, dkind = parse_days(days_fv.value) if days_fv else (None, None)
    tr = parse_time_range(time_fv.value) if time_fv else None
    start, end = tr if tr else (0, 24 * 60)
    # build ONE window from the two fields, then reuse Step 2's evaluate()
    s = Schedule("windows", [Window(days or ALL_DAYS, dkind or "unspecified", start, end,
                                    time_fv.value if time_fv else "")])
    ev = evaluate(s, dt, closed_lists=True)                     # rounding day lists ARE complete -> "closed"
    days_txt = days_fv.value if days_fv else "not in guide"
    win_txt = time_fv.value if time_fv else "hours not in guide"
    caveat = "" if days else f" Rounding days: '{days_txt}' — specific days are not in the guide."   # "As scheduled"
    fvs = [f for f in (days_fv, time_fv) if f]

    def prov(t):                                                 # show the PROVIDER's clock too (V17: Eastern)
        if not provider_tz:
            return ""
        p = t.astimezone(ZoneInfo(provider_tz))
        return f" ({hm(p)} {p.tzname()} your time)"

    if ev.state == "open":
        end_dt = dt.replace(hour=end // 60 % 24, minute=end % 60)
        return "answered", f"Yes — the rounding window is open until {hm(end_dt)} local{prov(end_dt)}.{caveat}", fvs, ev, days_txt
    if ev.reason == "day":                                       # N9: Sunday at a Monday-Friday hospital
        return ("time_dependent", f"No — this hospital rounds {days_txt} only; {DAY_LONG[dt.weekday()]} is not a "
                f"rounding day.", fvs, ev, days_txt)
    nxt = ev.next_open
    if nxt and nxt.date() == dt.date():                          # V17: opens later today -> "opens in 15 min"
        mins = int((nxt - dt).total_seconds() // 60)
        return ("time_dependent", f"Not yet. Window is {win_txt}; it opens in {mins} min at {hm(nxt)} local"
                f"{prov(nxt)}.{caveat}", fvs, ev, days_txt)
    nx = f" Next window {DAY_LONG[nxt.weekday()]} {hm(nxt)} local{prov(nxt)}." if nxt else ""
    return "time_dependent", f"Closed. Window is {win_txt}; it is {when(dt)}.{nx}{caveat}", fvs, ev, days_txt
