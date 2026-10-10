# engine/nudges.py
# PURPOSE: THE NUDGE ENGINE (the PRIMARY deliverable).
#   caselog event  ->  check the 11 rules in data/nudge_rules.json  ->  0 or 1 tiered nudge per matching rule
#   Each nudge = tier (hard stop / advisory / info) + message + WHY it fired + SOURCE field + STATUS + display hints.
#   No AI here: same input -> same nudge, in about a millisecond, and nothing can be invented.

import re                                    # text patterns
import time                                  # to measure speed (brief: < 500 ms)

from .guides import to_local, view           # Step 3
from .logic import lvo, rounding, schedule_status, signoff_checks, stale_note   # Step 4
from .schedule import DAY_LONG, evaluate, parse_schedule, when                  # Step 2

TIERS = ["hard_stop", "advisory", "info"]    # most serious first (used for sorting)

# ---------- 1. How each tier must be DISPLAYED (brief: "Nudge tiers" table) ----------
# George's frontend just reads nudge["display"] - it never has to decide placement itself.
DISPLAY = {
    "hard_stop": {"placement": "blocking", "interrupts": True, "blocks_action": True,
                  "requires": "fix_or_acknowledge"},   # blocks the action until fixed
    "advisory": {"placement": "inline", "interrupts": True, "blocks_action": False,
                 "requires": None},                    # shown next to the field, doesn't block
    "info": {"placement": "side_panel", "interrupts": False, "blocks_action": False,
             "requires": None},                        # on hover / side panel, never pops up
}
BLOCKED_ACTION = {"complete_clicked": "complete_consult"}   # which button a hard stop disables


def display_for(tier, trigger_field):
    d = dict(DISPLAY[tier])                    # copy the tier's display rules
    d["anchor_field"] = trigger_field          # which caselog field the card attaches to (e.g. lvo_present)
    d["blocked_action"] = BLOCKED_ACTION.get(trigger_field) if tier == "hard_stop" else None
    return d


# ---------- 2. Does this caselog event match a rule's trigger? ----------
def _truthy(v):
    return v is True or str(v).strip().lower() in ("true", "yes", "y", "1")   # True / "Yes" / "yes" all count


def _norm(v):
    return v if isinstance(v, bool) else str(v).strip().lower()


def trigger_matches(trig, event):
    """trig comes from nudge_rules.json, e.g. {"field": "lvo_present", "op": "eq", "value": true}
    event comes from the caselog,       e.g. {"field": "lvo_present", "value": true}"""
    if not event or event.get("field") != trig["field"]:
        return False                                            # different field -> not this rule
    v, op, want = event.get("value"), trig.get("op", "eq"), trig.get("value")
    if op == "eq":                                              # equals (LVO = Yes, LKW = Unknown)
        return _truthy(v) if isinstance(want, bool) else _norm(v) == _norm(want)
    if op == "in":
        return _norm(v) in [_norm(x) for x in want]
    if op == "not_in":                                          # allergies NOT in ["none", "nkda", ...] (N8 stays quiet)
        return _norm(v) not in [_norm(x) for x in want]
    if op == "matches":                                         # text contains "seizure" or "EEG"
        return bool(re.search(want, str(v or ""), re.I))
    return False


# ---------- 3. Build one nudge (every nudge has the same shape) ----------
def _nudge(rule, tier, message, fvs, ctx, dt, status="answered", details=None, title=None):
    ev = ctx.get("field_event") or {}
    flags = []
    for f in fvs:                                               # collect honesty flags from the fields used
        if f.stale and "stale" not in flags:
            flags.append("stale")
        if f.conflict and "conflict" not in flags:
            flags.append("conflict")
    details = list(details or []) + [stale_note(f) for f in fvs if f.stale]
    return {"rule_id": rule["id"],                              # which rule fired (R05 ...)
            "key": rule.get("key", rule["id"]),                 # rules sharing a key replace each other (no duplicates)
            "tier": tier,                                       # hard_stop | advisory | info
            "title": title or rule.get("title", rule["id"]),
            "message": message,                                 # what the doctor reads
            "details": details,                                 # smaller extra lines (stale warnings, who mixes...)
            "status": status,                                   # answered | time_dependent | conflict | hard_stop ...
            "flags": flags,                                     # extra: stale / conflict
            "trigger_field": ev.get("field"),
            "display": display_for(tier, ev.get("field")),
            "why": (f"{ctx['hospital_id']} · {ctx.get('consult_type')} · {ctx.get('caselog_step')} · "
                    f"{ev.get('field')} = {ev.get('value')} · {when(dt)}"),   # brief: "justify every interruption"
            "sources": [f.rec.source() for f in fvs]}           # brief: "cite the hospital and guide field"


# ---------- 4. HANDLERS: one per kind of rule. They read field NAMES, never hospital IDs ----------
# (This is why a brand-new hospital works with zero code changes.)

def h_show_fields(kb, g, ctx, dt, rule):
    """Show the listed fields as they are (R01 site setup, R09 note title). Flags conflicts (SYN-002 video eval)."""
    lines, fvs, missing, status = [], [], [], "answered"
    for name in rule["fields"]:
        fv = view(kb, g, name, dt)
        if fv is None:
            missing.append(name)
            continue
        fvs.append(fv)
        if fv.conflict:                                         # show BOTH values, never silently pick one
            status = "conflict"
            lines.append(f"{name}: sources disagree — guide says '{fv.value}', hospital storyboard says "
                         f"'{fv.conflict.value}' (updated {fv.conflict.updated}). Confirm locally.")
        else:
            lines.append(f"{name}: {fv.value}")
    if not lines:                                               # none of the fields exist at this hospital
        if rule.get("if_missing") == "info":
            return _nudge(rule, "info", f"Not available in this hospital's guide: {', '.join(missing)}.", [], ctx,
                          dt, "not_in_guide")
        return None                                             # or stay quiet
    return _nudge(rule, rule["tier"], " · ".join(lines), fvs, ctx, dt, status)


def h_wake_up(kb, g, ctx, dt, rule):
    """R02: last known well = Unknown (N3)."""
    fv = view(kb, g, "Wake Up Protocol", dt)
    if fv is None:
        return _nudge(rule, "info", "Wake-up protocol: not available in this hospital's guide.", [], ctx, dt,
                      "not_in_guide")
    if fv.value.strip().lower().startswith("yes"):
        msg = "Wake-up protocol is in use at this hospital — an unknown last-known-well can still be evaluated."
    else:
        msg = "This hospital does not use a wake-up protocol."
    return _nudge(rule, rule["tier"], msg, [fv], ctx, dt)


def h_thrombolytic_allergy(kb, g, ctx, dt, rule):
    """R03: an allergy was typed in -> remind which thrombolytic THIS hospital uses."""
    fv = view(kb, g, "Thrombolytic", dt)
    if fv is None:
        return None
    allergy = (ctx.get("field_event") or {}).get("value")
    return _nudge(rule, rule["tier"], f"Allergy entered ('{allergy}'). This hospital's thrombolytic is {fv.value} — "
                  "check for a contraindication before recommending.", [fv], ctx, dt)


def h_imaging_info(kb, g, ctx, dt, rule):
    """R04: CTA done -> is CT perfusion available here, and which AI tool? (N6, Info tier)."""
    parts, fvs = [], []
    ctp = view(kb, g, "CT Perfusion", dt)
    if ctp:
        fvs.append(ctp)
        ev = evaluate(parse_schedule(ctp.value), dt)            # check against local time
        if ev.state == "never":
            parts.append("CT perfusion is not available at this hospital.")
        elif ev.state == "always":
            parts.append(f"CT perfusion available {ctp.value}.")
        elif ev.state == "open":
            parts.append(f"CT perfusion available now ({ctp.value}).")
        elif ev.state in ("closed", "day_not_listed"):
            parts.append(f"CT perfusion not available now ({ctp.value}; it is {when(dt)}).")
        else:
            parts.append(f"CT perfusion: {ctp.value}.")
    ai = view(kb, g, "AI", dt)
    if ai:
        fvs.append(ai)
        parts.append("No AI LVO tool at this site." if ai.value.strip().lower() in ("none", "no")
                     else f"AI: {ai.value}.")
    if not parts:
        return None                                             # hospital lists neither -> stay quiet
    return _nudge(rule, rule["tier"], " ".join(parts), fvs, ctx, dt)


def h_lvo_protocol(kb, g, ctx, dt, rule):
    """R05: LVO present = Yes -> THE WOW MOMENT (N1, N2). All the thinking is in logic.lvo()."""
    r = lvo(kb, g, dt)
    if r is None:
        return _nudge(rule, "info", "LVO protocol: not available in this hospital's guide.", [], ctx, dt,
                      "not_in_guide")
    status, msg, _, _ = r
    title = "Outside the EVT window" if msg.startswith("No — outside") else rule["title"]
    return _nudge(rule, rule["tier"], msg, [view(kb, g, "LVO Protocol", dt)], ctx, dt, status, title=title)


def _restricted(oe):
    """True if Order Entry starts with 'No ...' (e.g. 'No medication orders entered by teleneurologist')."""
    return bool(oe and re.match(r"\s*no\b", oe.value, re.I))


def h_order_guidance(kb, g, ctx, dt, rule):
    """R06: thrombolytic given = Yes -> which order set (or: hospital provider orders it) (N4)."""
    oe, osn = view(kb, g, "Order Entry", dt), view(kb, g, "Order Set Name", dt)
    th, mm = view(kb, g, "Thrombolytic", dt), view(kb, g, "Thrombolytic Mix Model", dt)
    fvs = [f for f in (oe, osn, th, mm) if f]
    if not fvs:
        return None
    details, status = [], "answered"
    if th:
        details.append(f"Thrombolytic here: {th.value}.")
    if mm:
        st, mm_msg = schedule_status(mm, dt)                    # "during staffed hours" -> time-dependent (V18)
        if st == "time_dependent":
            status = "time_dependent"
            details.append("Who mixes: " + mm_msg)
        else:
            details.append(f"Who mixes: {mm.value}.")
    if _restricted(oe):                                         # N4: NO order-set "Search ..." nudge here
        tail = f" {osn.value}." if osn and osn.value.strip().lower() != "not applicable" else \
            " The hospital provider places the orders."
        msg = f"The teleneurologist does not enter orders here ({oe.value}).{tail}"
        return _nudge(rule, rule["tier"], msg, fvs, ctx, dt, status, details, title="Orders: hospital provider")
    msg = f"Order set: {osn.value if osn else 'not in guide'}. Scope: {oe.value if oe else 'not in guide'}."
    return _nudge(rule, rule["tier"], msg, fvs, ctx, dt, status, details)


def h_order_restriction(kb, g, ctx, dt, rule):
    """R07: the 'order placed in EHR?' field is shown -> warn ONLY if this hospital forbids teleneuro orders."""
    oe = view(kb, g, "Order Entry", dt)
    if not _restricted(oe):
        return None                                             # nothing site-specific -> stay quiet (beat nudge fatigue)
    return _nudge(rule, rule["tier"], f"Do not place the thrombolytic order here — {oe.value}. "
                  "The hospital provider places it.", [oe], ctx, dt, title="Orders: hospital provider")


def h_service_availability(kb, g, ctx, dt, rule):
    """R08: seizure/EEG mentioned -> is EEG available now?"""
    name = rule["fields"][0]
    fv = view(kb, g, name, dt)
    if fv is None:
        return _nudge(rule, "info", f"{name}: not available in this hospital's guide.", [], ctx, dt, "not_in_guide")
    status, msg = schedule_status(fv, dt)
    return _nudge(rule, rule["tier"], f"{name}: {msg}", [fv], ctx, dt, status)


def h_signoff(kb, g, ctx, dt, rule):
    """R10: Complete clicked -> HARD STOP if something required is missing (N5, N7)."""
    checks = signoff_checks(kb, g, dt, ctx.get("charge_entered", False), ctx.get("plan_confirmed", False))
    if not checks:
        return None                                             # nothing missing -> sign-off allowed, stay quiet
    return _nudge(rule, "hard_stop", " ".join(m for m, _ in checks), [fv for _, fv in checks], ctx, dt, "hard_stop")


def h_rounding_check(kb, g, ctx, dt, rule):
    """R11: rounding encounter opened -> is today/now a rounding window? (N9)"""
    r = rounding(kb, g, dt, ctx.get("provider_timezone"))
    if r is None:
        return None
    status, msg, fvs, ev, days_txt = r
    if ev.state == "open":
        ro = view(kb, g, "Rounding Orders", dt)
        return _nudge(rule, "info", f"Rounding window open. Rounding orders: {ro.value}." if ro else msg,
                      fvs + ([ro] if ro else []), ctx, dt)
    if ev.reason == "day":
        msg = (f"This hospital rounds {days_txt} only; check why a {DAY_LONG[dt.weekday()]} rounding encounter "
               "exists.")
    return _nudge(rule, "info", msg, fvs, ctx, dt, status)


# a dictionary {"show_fields": h_show_fields, "lvo_protocol": h_lvo_protocol, ...} built automatically
HANDLERS = {k[2:]: v for k, v in globals().items() if k.startswith("h_")}


# ---------- 5. THE MAIN FUNCTION: called once per caselog event ----------
def run(kb, ctx):
    """ctx = Sevaro's encounter context:
    {hospital_id, consult_type, caselog_step, field_event:{field,value}, local_time, provider_timezone, charge_entered}"""
    t0 = time.perf_counter()                                    # start the stopwatch
    g = kb.guides.get(ctx.get("hospital_id"))
    if g is None:                                               # unknown hospital -> say so, never crash, never borrow
        return {"nudges": [{"rule_id": "SYS", "key": "SYS", "tier": "info", "title": "Guidance unavailable",
                            "message": "No guide is loaded for this hospital. The caselog keeps working; "
                                       "nothing is borrowed from another hospital.",
                            "details": [], "status": "not_in_guide", "flags": [], "why": "", "sources": [],
                            "trigger_field": None, "display": display_for("info", None)}],
                "rules_checked": 0, "guide_fields": 0, "ms": 0.0}
    dt = to_local(ctx["local_time"], g)                         # the HOSPITAL's clock
    out, checked = [], 0
    step, ctype = str(ctx.get("caselog_step", "")).lower(), str(ctx.get("consult_type", "")).lower()
    for rule in kb.rules:                                       # check every rule...
        checked += 1
        if rule["step"].lower() != step:                        # ...wrong caselog step -> skip
            continue
        if ctype not in [c.lower() for c in rule.get("consult_types", [])]:   # ...wrong consult type -> skip
            continue
        if not trigger_matches(rule["trigger"], ctx.get("field_event")):      # ...event doesn't match -> skip
            continue
        try:
            n = HANDLERS[rule["handler"]](kb, g, ctx, dt, rule)               # rule matches -> run its handler
        except Exception as e:                                  # a weird guide value must NEVER break the caselog
            n = {"rule_id": rule["id"], "key": rule.get("key", rule["id"]), "tier": "info",
                 "title": "Guidance unavailable", "message": f"Could not evaluate this rule ({e}).", "details": [],
                 "status": "not_in_guide", "flags": [], "why": "", "sources": [], "trigger_field": None,
                 "display": display_for("info", None)}
        if n:                                                   # handler may return None = stay quiet
            out.append(n)
    out.sort(key=lambda n: TIERS.index(n["tier"]))              # hard stops first
    return {"nudges": out,
            "rules_checked": checked,                           # proof against nudge fatigue:
            "silent": checked - len(out),                       #   "11 rules checked, 10 stayed silent"
            "guide_fields": len(g.fields),
            "ms": round((time.perf_counter() - t0) * 1000, 2)}  # milliseconds taken
