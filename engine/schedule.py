# engine/schedule.py
# PURPOSE: read guide text like "Mon-Fri 0700-1900; weekend on-call" and answer
#          "is this available right now, at the hospital's local time?"

import re                                            # "regular expressions": find patterns in text
from dataclasses import dataclass, field             # quick way to make small data containers
from datetime import datetime, timedelta, time       # date/time tools

# ---------- 1. Lookup tables ----------
DAY_IDX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}   # Python counts Monday = 0
DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]                      # for printing "Tue 19:30"
DAY_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# a pattern that matches any day name, full or short ("monday", "mon", "tues"...)
_DAY = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues|tue|wed|thurs|thur|thu|fri|sat|sun)"

# matches a time range like "0700-1900":  hour(2 digits) minute(2 digits) - hour minute
# (?<!\d) and (?!\d) = "no digit right before/after", so IDs like "SYN-41021" are NOT read as times
TIME_RANGE = re.compile(r"(?<!\d)([01]\d|2[0-4])([0-5]\d)\s*-\s*([01]\d|2[0-4])([0-5]\d)(?!\d)")

ALL_DAYS = frozenset(range(7))                       # {0,1,2,3,4,5,6} = every day of the week
NEVER = {"no", "none", "not available", "unavailable", "n/a"}   # values that mean "not available at all"

# words that mean "depends on hours the guide never states" (V08, V18) -> we must NOT guess a cutoff
UNDEFINED_HINT = re.compile(r"staffed|overnight|business hours|after[- ]hours|during coverage|coverage hours|\bnights?\b", re.I)


# ---------- 2. Small containers for our results ----------
@dataclass
class Window:              # ONE opening period, e.g. Mon-Fri 07:00-19:00
    days: frozenset        # which weekdays, e.g. {0,1,2,3,4}
    day_kind: str          # "all" (Daily), "range" (Mon-Fri), "list" (Tue/Thu), "unspecified"
    start: int             # minutes after midnight: 07:00 -> 420
    end: int               # 19:00 -> 1140   (minutes make comparisons easy)
    text: str              # the original piece of guide text


@dataclass
class Schedule:            # everything we understood from one guide value
    kind: str              # always | never | yes | windows | undefined | text
    windows: list = field(default_factory=list)   # list of Window objects
    notes: list = field(default_factory=list)     # leftover pieces like "weekend on-call"
    raw: str = ""                                 # original full text


@dataclass
class Eval:                # the answer to "is it open at this moment?"
    state: str             # open | closed | day_not_listed | always | never | yes | text | undefined
    window: Window = None  # which window matched (if any)
    next_open: datetime = None   # when it opens next (powers "opens in 15 min")
    reason: str = ""       # if closed: "hours" (wrong time) or "day" (wrong day)


# ---------- 3. Reading days ----------
def _d(tok):
    return DAY_IDX[tok[:3].lower()]                  # "Tuesday" -> "tue" -> 1


def parse_days(text):
    """Find which days a piece of text talks about. Returns (set_of_days, kind) or (None, None)."""
    t = text.lower()
    if re.search(r"\bdaily\b|\bevery day\b|\b7 days\b", t):          # "Daily 0800-1700"
        return ALL_DAYS, "all"
    m = re.search(r"\b" + _DAY + r"\b\s*(?:-|–|to|through)\s*\b" + _DAY + r"\b", t)   # "Mon-Fri", "Monday-Saturday"
    if m:
        a, b = _d(m.group(1)), _d(m.group(2))        # start day number, end day number
        days, i = set(), a
        while True:                                  # walk from start day to end day
            days.add(i)
            if i == b:
                break
            i = (i + 1) % 7                          # % 7 wraps Sunday back to Monday (handles "Fri-Mon")
        return frozenset(days), "range"
    if re.search(r"\bweekends?\b", t):               # "weekend 0700-1900"
        return frozenset({5, 6}), "range"
    if re.search(r"\bweekdays?\b", t):
        return frozenset(range(5)), "range"
    toks = re.findall(r"\b" + _DAY + r"\b", t)       # "Tue/Thu" or "Tuesday, Thursday, Saturday"
    if toks:
        return frozenset(_d(x) for x in toks), "list"
    return None, None                                # no days mentioned


# ---------- 4. Reading times ----------
def parse_time_range(text):
    """'0830-1200' -> (510, 720) minutes after midnight, or None."""
    m = TIME_RANGE.search(text or "")
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))


# ---------- 5. Reading a whole guide value ----------
def parse_schedule(value):
    raw = (value or "").strip()
    low = raw.lower().rstrip(".")
    if low in NEVER:                                 # "No" -> not available ever (V05)
        return Schedule("never", raw=raw)
    windows, notes = [], []
    for seg in raw.split(";"):                       # "Mon-Fri 0500-2300; weekend 0700-1900" -> 2 pieces
        seg = seg.strip()
        if not seg:
            continue
        tr = parse_time_range(seg)                   # any hours in this piece?
        days, kind = parse_days(seg)                 # any days in this piece?
        if tr:                                       # has hours -> a window (no days given = every day)
            windows.append(Window(days or ALL_DAYS, kind or "unspecified", tr[0], tr[1], seg))
        elif days and not re.search(r"call|unavailable|\bno\b", seg.lower()):
            windows.append(Window(days, kind, 0, 24 * 60, seg))      # days only, e.g. "Monday-Friday" -> all day
        else:
            notes.append(seg)                        # e.g. "weekend on-call", "overnight call"
    if "24/7" in low and not windows:                # "24/7" -> always open
        return Schedule("always", notes=notes, raw=raw)
    if windows:
        return Schedule("windows", windows, notes, raw)
    if UNDEFINED_HINT.search(raw):                   # "during staffed hours" with no hours given
        return Schedule("undefined", notes=notes, raw=raw)
    if low.startswith("yes"):
        return Schedule("yes", notes=notes, raw=raw)
    return Schedule("text", notes=notes, raw=raw)    # ordinary text like "Patient room"


# ---------- 6. Checking a moment against the windows ----------
def _inside(w, minute):
    if w.start <= w.end:                             # normal window, e.g. 07:00-19:00
        return w.start <= minute < w.end             # 19:00 itself counts as closed (window "ended")
    return minute >= w.start or minute < w.end       # overnight window, e.g. 22:00-06:00


def next_open(s, dt):
    """Search the next 7 days for the next time any window starts."""
    best = None
    for d in range(0, 8):
        day = (dt + timedelta(days=d)).date()
        for w in s.windows:
            if day.weekday() in w.days and w.start < 24 * 60:
                cand = datetime.combine(day, time(w.start // 60, w.start % 60), tzinfo=dt.tzinfo)
                if cand > dt and (best is None or cand < best):   # later than now, and earliest so far
                    best = cand
    return best


def evaluate(s, dt, closed_lists=False):
    """THE KEY DECISION: is it open at hospital-local time dt?"""
    if s.kind != "windows":                          # always / never / undefined / text: nothing to check
        return Eval(s.kind)
    wd, minute = dt.weekday(), dt.hour * 60 + dt.minute       # e.g. Tuesday=1, 19:30 -> 1170
    covering = [w for w in s.windows if wd in w.days]         # windows that apply to TODAY
    for w in covering:
        if _inside(w, minute):
            return Eval("open", w)                   # right day, right time
    nxt = next_open(s, dt)
    if covering:
        return Eval("closed", covering[0], nxt, "hours")      # right day, wrong time (N2: 19:30 > 1900)
    if not closed_lists and all(w.day_kind == "list" for w in s.windows):
        return Eval("day_not_listed", None, nxt, "day")       # "Tue/Thu" on Friday -> don't assume (V04)
    return Eval("closed", None, nxt, "day")                   # "Mon-Fri" on Saturday -> No (V16)


# ---------- 7. Formatting helpers ----------
def hm(dt):
    return dt.strftime("%H:%M")                      # 19:30


def when(dt):
    return f"{DAY_SHORT[dt.weekday()]} {hm(dt)} {dt.tzname()}"   # "Tue 19:30 CDT"
