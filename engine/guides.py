# engine/guides.py
# PURPOSE: load Sevaro's hospital guides, look up ONE field for ONE hospital,
#          and attach two honesty flags: STALE (too old) and CONFLICT (storyboard disagrees).
# Adding a hospital = adding data. Nothing in here names a specific hospital.

import json                                   # read .json files
import re                                     # text patterns
from dataclasses import dataclass             # small data containers
from datetime import date, datetime           # dates
from pathlib import Path                      # file paths that work on Windows and Mac
from zoneinfo import ZoneInfo                 # time zones ("America/Chicago")

DATA = Path(__file__).resolve().parent.parent / "data"   # .../nudge-api/data  (this file's folder -> up one -> data)
STALE_DAYS = 180                              # brief: "last verified more than 180 days before the encounter" = stale
DEFAULT_VERIFIED = "2026-02-02"               # used only if a record has no date
TZ_WORDS = {"eastern": "America/New_York", "central": "America/Chicago", "mountain": "America/Denver",
            "pacific": "America/Los_Angeles", "alaska": "America/Anchorage", "hawaii": "Pacific/Honolulu",
            "arizona": "America/Phoenix"}     # fallback if a guide writes "Central" instead of "America/Chicago"


# ---------- 1. Small helpers ----------
def norm(s):
    """Make field names comparable: 'When Do We Round?' and 'when do we round' -> 'whendoweround'."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())    # lowercase, then drop everything except letters/digits


def norm_val(s):
    """Make VALUES comparable for conflict checks: ignore case, extra spaces, trailing period."""
    return re.sub(r"\s+", " ", str(s).strip().lower().rstrip("."))


def _date(s):
    """'2026-02-02' (text) -> a real date object we can subtract."""
    if isinstance(s, date):
        return s
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


# ---------- 2. Containers ----------
@dataclass
class Record:                     # ONE field of ONE hospital's guide
    hospital_id: str              # "SYN-006"
    field: str                    # "LVO Protocol"
    value: str                    # "Thrombectomy capable Mon-Fri 0700-1900. ..."
    last_verified: date           # 2026-02-02

    def source(self):             # the citation we attach to every nudge/answer
        return {"hospital_id": self.hospital_id, "field": self.field,
                "last_verified": self.last_verified.isoformat()}


@dataclass
class StoryboardNote:             # the "second source" shown in the caselog header
    hospital_id: str
    field: str
    value: str
    updated: str
    note: str = ""


class Guide:                      # ONE hospital's whole rulebook
    def __init__(self, hospital_id, name):
        self.id, self.name, self.fields, self.tz_name = hospital_id, name or hospital_id, {}, None
        # self.fields is a dictionary:  "lvoprotocol" -> Record(...)

    def add(self, rec):
        self.fields[norm(rec.field)] = rec        # store under the normalized name

    def get(self, field):
        return self.fields.get(norm(field))       # look up a field; returns None if this hospital doesn't have it

    def records(self):
        return list(self.fields.values())         # all fields (used for the live-test coverage report)

    @property
    def tz(self):                                 # the hospital's time zone
        if self.tz_name:                          # official file gives "local_timezone": "America/Chicago"
            return ZoneInfo(self.tz_name)
        rec = self.get("Local Time Zone")         # fallback: a field like "Central (America/Chicago)"
        if rec:
            m = re.search(r"([A-Za-z_]+/[A-Za-z_]+)", rec.value)
            if m:
                return ZoneInfo(m.group(1))
            for word, iana in TZ_WORDS.items():
                if word in rec.value.lower():
                    return ZoneInfo(iana)
        return None


# ---------- 3. Reading different JSON layouts ----------
_INLINE_VERIFIED = re.compile(r"\s*\[last verified (\d{4}-\d{2}-\d{2})\]\s*", re.I)   # e.g. "Tue/Thu 0800-1500 [last verified 2025-06-10]"


def _records_from(obj):
    """Flatten any reasonable guide layout into a simple list of {hospital_id, field, value, ...}.
    Why: the judges' NEW hospital in the live test might be shaped slightly differently."""
    if isinstance(obj, dict):
        for k in ("guides", "records", "hospitals", "hospital_guides", "data"):
            if k in obj:                          # official file: {"hospitals": [...]}
                return _records_from(obj[k])
        out = []                                  # layout: {"SYN-008": {"hospital_name":..., "fields": {...}}}
        for hid, h in obj.items():
            if isinstance(h, dict):
                name = h.get("hospital_name") or h.get("name")
                tzn = h.get("local_timezone") or h.get("timezone")
                fields = h.get("fields") or {k: v for k, v in h.items()
                                             if k not in ("hospital_name", "name", "local_timezone", "timezone")}
                for f, v in fields.items():
                    base = {"hospital_id": hid, "hospital_name": name, "field": f, "_tz": tzn}
                    out.append({**base, **v} if isinstance(v, dict) else {**base, "value": v})
        return out
    if isinstance(obj, list):
        out = []
        for r in obj:
            if isinstance(r, dict) and isinstance(r.get("fields"), (dict, list)):    # one object per hospital (OFFICIAL)
                hid = r.get("hospital_id") or r.get("id")
                name = r.get("hospital_name") or r.get("name")
                tzn = r.get("local_timezone") or r.get("timezone")
                fs = r["fields"]
                items = fs.items() if isinstance(fs, dict) else [(x.get("field") or x.get("name"), x) for x in fs]
                for f, v in items:
                    base = {"hospital_id": hid, "hospital_name": name, "field": f, "_tz": tzn}
                    out.append({**base, **v} if isinstance(v, dict) else {**base, "value": v})
            else:
                out.append(r)                     # already one record per row
        return out
    return []


# ---------- 4. The knowledge base: everything loaded ONCE at startup ----------
def _load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


class KB:
    def __init__(self, data_dir=DATA):
        self.data_dir = Path(data_dir)
        self.guides, self.storyboard, self.stale_days = {}, {}, STALE_DAYS
        self.reference_date = None                # dataset's "today" (encounter_reference_date) for reports
        self.load_guides(_load_json(self.data_dir / "hospital_guides.json", {}))
        self.load_storyboard(_load_json(self.data_dir / "storyboard_notes.json", []))
        self.rules = _load_json(self.data_dir / "nudge_rules.json", [])        # added in Step 5
        self.registry = _load_json(self.data_dir / "field_registry.json", [])  # added in Step 6

    def load_guides(self, obj):
        """Add hospitals from any guide JSON. Also used by the LIVE TEST. Returns the hospital IDs added."""
        touched = []
        if isinstance(obj, dict) and obj.get("stale_after_days"):
            self.stale_days = int(obj["stale_after_days"])                    # official file says 180
        if isinstance(obj, dict) and obj.get("encounter_reference_date"):
            self.reference_date = _date(obj["encounter_reference_date"])      # official file says 2026-03-17
        for r in _records_from(obj):
            hid = r.get("hospital_id") or r.get("hospital")
            field = r.get("field") or r.get("guide_field") or r.get("name")
            if not hid or not field:
                continue                                                      # skip broken rows instead of crashing
            value = str(r.get("value", r.get("synthetic_value", "")))
            verified = r.get("last_verified") or r.get("last_verified_date") or r.get("verified")
            m = _INLINE_VERIFIED.search(value)
            if m:                                                             # date written inside the value text
                verified, value = m.group(1), _INLINE_VERIFIED.sub(" ", value).strip()
            g = self.guides.setdefault(hid, Guide(hid, r.get("hospital_name")))   # create hospital if new
            if r.get("hospital_name"):
                g.name = r["hospital_name"]
            if r.get("_tz"):
                g.tz_name = r["_tz"]
            g.add(Record(hid, field, value, _date(verified or DEFAULT_VERIFIED)))
            if hid not in touched:
                touched.append(hid)
        return touched

    def load_storyboard(self, obj):
        items = obj.get("notes", obj) if isinstance(obj, dict) else obj
        for n in items:
            note = StoryboardNote(n["hospital_id"], n["field"],
                                  str(n.get("value", n.get("storyboard_value", ""))),        # official key: storyboard_value
                                  str(n.get("updated", n.get("storyboard_updated", ""))),    # official key: storyboard_updated
                                  n.get("note", ""))
            self.storyboard[(note.hospital_id, norm(note.field))] = note   # key = (hospital, field)


# ---------- 5. Looking up a field WITH its honesty flags ----------
@dataclass
class FieldView:
    rec: Record                   # the guide field
    stale: bool                   # True if verified > 180 days before this encounter
    conflict: StoryboardNote      # the storyboard note IF it disagrees, else None

    @property
    def value(self):
        return self.rec.value


def view(kb, guide, field, dt):
    """THE ONLY WAY the rest of the code reads a field. Returns None if this hospital doesn't have it
    (-> 'not in guide'). Never looks at any other hospital."""
    rec = guide.get(field)
    if rec is None:
        return None
    stale = (dt.date() - rec.last_verified).days > getattr(kb, "stale_days", STALE_DAYS)  # V13
    sb = kb.storyboard.get((guide.id, norm(field)))                                        # same hospital only
    conflict = sb if sb and norm_val(sb.value) != norm_val(rec.value) else None            # V12 (SYN-005 agrees -> no flag)
    return FieldView(rec, stale, conflict)


def to_local(local_time, guide):
    """Turn the encounter time into the HOSPITAL's local time.
    '2026-03-17T19:30' -> 19:30 Chicago.  '2026-03-17T19:30:00-05:00' -> converted to Chicago."""
    dt = local_time if isinstance(local_time, datetime) else datetime.fromisoformat(str(local_time))
    tz = guide.tz or ZoneInfo("America/New_York")
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
