"""Episode schema: one observable trigger, the thought it produced, what I did and what happened."""

from datetime import timedelta
import re

from .store import AnchorError, parse_date, parse_timestamp, read_jsonl, write_jsonl

FIELDS = ("id", "date", "source_ref", "trigger", "my_thought", "body", "urge", "certainty",
          "action", "script_used", "outcome", "outcome_fact", "recovery_minutes", "suds_peak",
          "miss", "miss_conditions", "notes")
EXTENSIONS = ("recorded_at", "origin", "review")
ACTIONS = ("checked", "chased", "held", "said_ok", "said_stop", "said_no", "other")
CHECKING = {"checked", "chased"}
OUTCOMES = ("happened", "not_happened", "unverifiable")
ORIGINS = ("now", "export", "capture", "inbox", "manual")
REVIEWS = ("pending", "confirmed", "rejected")
EPISODE_ID = re.compile(r"ep-(\d{4}-\d{2}-\d{2})-(\d{2})\Z")
FOLLOW_UP = (timedelta(hours=24), timedelta(hours=72))

# Reported denials and explanations from the other person are not observations.
EXPLANATION = re.compile(
    r"(她|他|对方|ta|TA)(说|解释|表示|告诉我|保证|发誓|否认|承认)"
    r"|说(不是|没有|没|只是|就是普通|只是朋友)|解释说|跟我解释|否认"
    r"|\b(she|he|they) (said|says|told me|explained|denied|promised)\b",
    re.I,
)
MOTIVE = re.compile(r"故意|想报复|报复我|肯定是|因为她想|她想让我|在试探|她觉得我|动机|心里想")


def blank():
    return {"id": None, "date": None, "source_ref": "", "trigger": "", "my_thought": "", "body": "",
            "urge": None, "certainty": None, "action": None, "script_used": "", "outcome": None,
            "outcome_fact": "", "recovery_minutes": None, "suds_peak": None, "miss": None,
            "miss_conditions": [], "notes": ""}


def ordered(row):
    result = {key: row.get(key, blank()[key]) for key in FIELDS}
    for key in EXTENSIONS:
        if key in row:
            result[key] = row[key]
    return result


def bounded_int(value, low, high, field, errors):
    if value is None:
        return
    if type(value) is not int or not low <= value <= high:
        errors.append(f"{field}_out_of_range")


def text_field(row, field, errors, required=False, limit=4000):
    value = row.get(field)
    if not isinstance(value, str):
        errors.append(f"{field}_must_be_text")
    elif len(value) > limit:
        errors.append(f"{field}_too_long")
    elif required and not value.strip():
        errors.append(f"{field}_required")


def validate(row):
    """Return (errors, warnings) for one episode."""
    errors, warnings = [], []
    unknown = set(row) - set(FIELDS) - set(EXTENSIONS)
    if unknown:
        errors.append("unknown_fields:" + ",".join(sorted(unknown)))
    match = EPISODE_ID.fullmatch(row.get("id") or "")
    if not match:
        errors.append("invalid_id")
    try:
        day = parse_date(row.get("date"))
        if match and match.group(1) != day.isoformat():
            errors.append("id_date_mismatch")
    except AnchorError:
        errors.append("invalid_date")
    text_field(row, "source_ref", errors, required=True, limit=400)
    text_field(row, "trigger", errors, required=True)
    text_field(row, "my_thought", errors)
    if isinstance(row.get("my_thought"), str) and not row["my_thought"].strip():
        warnings.append("my_thought_empty")
    for field in ("body", "script_used", "outcome_fact", "notes"):
        text_field(row, field, errors)
    bounded_int(row.get("urge"), 0, 10, "urge", errors)
    bounded_int(row.get("certainty"), 0, 100, "certainty", errors)
    bounded_int(row.get("suds_peak"), 0, 100, "suds_peak", errors)
    bounded_int(row.get("recovery_minutes"), 0, 60 * 24 * 14, "recovery_minutes", errors)
    if row.get("action") is not None and row.get("action") not in ACTIONS:
        errors.append("invalid_action")
    outcome = row.get("outcome")
    if outcome is not None and outcome not in OUTCOMES:
        errors.append("invalid_outcome")
    fact = row.get("outcome_fact") if isinstance(row.get("outcome_fact"), str) else ""
    if outcome in {"happened", "not_happened"} and not fact.strip():
        errors.append("outcome_fact_required")
    if outcome is None and fact.strip():
        errors.append("outcome_required_with_fact")
    if outcome in {"happened", "not_happened"} and is_explanation(fact):
        warnings.append("outcome_fact_looks_like_explanation")
    if row.get("miss") is not None and not isinstance(row.get("miss"), bool):
        errors.append("miss_must_be_boolean")
    if row.get("miss") is True and row.get("action") is None:
        errors.append("miss_requires_action")
    conditions = row.get("miss_conditions")
    if not isinstance(conditions, list) or not all(isinstance(item, str) and item.strip()
                                                   for item in conditions):
        errors.append("miss_conditions_must_be_text_list")
    if isinstance(row.get("trigger"), str) and MOTIVE.search(row["trigger"]):
        warnings.append("trigger_mentions_motive")
    if "recorded_at" in row:
        try:
            parse_timestamp(row["recorded_at"])
        except (AnchorError, ValueError, AttributeError):
            errors.append("invalid_recorded_at")
    if "origin" in row and row["origin"] not in ORIGINS:
        errors.append("invalid_origin")
    if "review" in row and row["review"] not in REVIEWS:
        errors.append("invalid_review")
    return errors, warnings


def is_explanation(text):
    return bool(EXPLANATION.search(text or ""))


def require_valid(row):
    errors, _ = validate(row)
    if errors:
        raise AnchorError("invalid_episode", f"{row.get('id')}: {', '.join(errors)}")
    return row


def load(paths):
    rows = read_jsonl(paths.episodes)
    seen = set()
    for row in rows:
        require_valid(row)
        if row["id"] in seen:
            raise AnchorError("duplicate_episode_id", row["id"])
        seen.add(row["id"])
    return rows


def save(paths, rows):
    rows = [ordered(require_valid(row)) for row in rows]
    rows.sort(key=lambda row: row["id"])
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise AnchorError("duplicate_episode_id")
    write_jsonl(paths.episodes, rows)


def next_id(day, taken):
    prefix = "ep-" + day.isoformat() + "-"
    used = {int(item[len(prefix):]) for item in taken if item.startswith(prefix)}
    free = [number for number in range(1, 100) if number not in used]
    if not free:
        raise AnchorError("too_many_episodes_for_day", day.isoformat())
    return prefix + f"{free[0]:02d}"


def apply_fact(row, outcome, fact, observed=False, recovery_minutes=None, suds_peak=None,
               action=None, miss=None, miss_conditions=None):
    """Backfill what happened. Returns (updated row, warnings)."""
    if outcome not in OUTCOMES:
        raise AnchorError("invalid_outcome", str(outcome))
    fact = (fact or "").strip()
    warnings = []
    if outcome in {"happened", "not_happened"} and not fact:
        raise AnchorError("outcome_fact_required")
    if outcome in {"happened", "not_happened"} and is_explanation(fact) and not observed:
        warnings.append("explanation_recorded_as_unverifiable")
        outcome = "unverifiable"
    updated = dict(row, outcome=outcome, outcome_fact=fact)
    if recovery_minutes is not None:
        updated["recovery_minutes"] = recovery_minutes
    if suds_peak is not None:
        updated["suds_peak"] = suds_peak
    if action is not None:
        updated["action"] = action
    if miss is not None:
        updated["miss"] = miss
    if miss_conditions is not None:
        updated["miss_conditions"] = miss_conditions
    require_valid(updated)
    return updated, warnings


def awaiting_fact(row):
    """Live records still waiting for a fact. Historical extractions without a follow-up are not chased."""
    return row.get("outcome") is None and row.get("origin") != "export"


def due_follow_ups(rows, at):
    """Pending episodes whose 24–72 hour fact window has opened, oldest first."""
    due = []
    for row in rows:
        if not awaiting_fact(row):
            continue
        if row.get("recorded_at"):
            start = parse_timestamp(row["recorded_at"])
        else:
            start = parse_timestamp(row["date"] + "T12:00:00+08:00")
        age = at - start
        if age >= FOLLOW_UP[0]:
            due.append((row, "overdue" if age > FOLLOW_UP[1] else "due"))
    due.sort(key=lambda item: item[0]["id"])
    return due


def find(rows, identity):
    for row in rows:
        if row["id"] == identity:
            return row
    raise AnchorError("episode_not_found", identity)
