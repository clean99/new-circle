"""Operations on the Life OS data that every client shares (CLI, inbox ingest, tests)."""

from . import actions as action_model
from . import drills as drill_model
from . import episodes as episode_model
from . import inbox as inbox_model
from . import ladder as ladder_model
from .now import choose_script
from . import scenes as scene_model
from . import views as view_model
from .store import AnchorError, now, read_jsonl, write_markdown


def read_text(path):
    if not path.exists():
        raise AnchorError("missing_file", str(path))
    return path.read_text(encoding="utf-8")


def load_views(paths):
    return view_model.parse(read_text(paths.views)) if paths.views.exists() else []


def load_rungs(paths):
    return ladder_model.parse(read_text(paths.ladder)) if paths.ladder.exists() else []


def mark_view(paths, identity, day, remembered=True):
    text = read_text(paths.views)
    view = view_model.reviewed(view_model.find(view_model.parse(text), identity), day, remembered)
    write_markdown(paths.views, view_model.update(text, view), day)
    return view


def complete_rung(paths, identity, day, suds, note=""):
    text = ladder_model.complete(read_text(paths.ladder), identity, day, suds, note)
    write_markdown(paths.ladder, text, day)
    return ladder_model.find(ladder_model.parse(text), identity)


def log_drill(paths, row, day):
    if row.get("scene") not in {scene.id for scene in scene_model.load_all(paths)}:
        raise AnchorError("scene_not_found", str(row.get("scene")))
    saved, added = drill_model.record(paths, row)
    if added and saved.get("view"):
        mark_view(paths, saved["view"], day)
    return saved, added


def record_now(paths, fields, at=None):
    at = at or now()
    rows = episode_model.load(paths)
    row = episode_model.blank()
    row.update({key: value for key, value in fields.items() if value is not None})
    row["date"] = at.date().isoformat()
    row["id"] = episode_model.next_id(at.date(), {item["id"] for item in rows})
    row["recorded_at"] = at.isoformat(timespec="seconds")
    row["origin"] = "now"
    if not row.get("source_ref"):
        row["source_ref"] = "live:" + at.isoformat(timespec="minutes")
    if not row.get("script_used"):
        row["script_used"] = choose_script(row["trigger"], row["my_thought"])
    episode_model.require_valid(row)
    rows.append(row)
    episode_model.save(paths, rows)
    return episode_model.ordered(row)


def next_action(paths, key):
    if not paths.actions.exists():
        return ("健康", "出门走 10 分钟")
    return action_model.pick(action_model.parse(read_text(paths.actions)), key)


def update_episode(paths, identity, **changes):
    rows = episode_model.load(paths)
    row = episode_model.find(rows, identity)
    updated = dict(row)
    updated.update({key: value for key, value in changes.items() if value is not None})
    episode_model.require_valid(updated)
    rows[rows.index(row)] = updated
    episode_model.save(paths, rows)
    return episode_model.ordered(updated)


def backfill(paths, identity, outcome, fact, **options):
    rows = episode_model.load(paths)
    row = episode_model.find(rows, identity)
    updated, warnings = episode_model.apply_fact(row, outcome, fact, **options)
    rows[rows.index(row)] = updated
    episode_model.save(paths, rows)
    return episode_model.ordered(updated), warnings


def apply_op(paths, op, rows, renames, day):
    kind = op["op"]
    if kind == "episode":
        outcome = inbox_model.apply_episode(op, rows, renames)
        episode_model.save(paths, rows)
        return outcome
    if kind == "fact":
        outcome = inbox_model.apply_fact(op, rows, renames)
        episode_model.save(paths, rows)
        return outcome
    on = episode_model.parse_date(op.get("date", day.isoformat()))
    if kind == "drill":
        _, added = log_drill(paths, {key: value for key, value in op.items() if key != "op"}, on)
        return "added" if added else "duplicate"
    if kind == "ladder":
        rung = complete_rung(paths, op["id"], on, op["suds"], op.get("note", ""))
        return "completed" + ("(cleared)" if rung.cleared else "")
    view = mark_view(paths, op["id"], on, op.get("remembered", True) is not False)
    return "reviewed(next " + view.due.isoformat() + ")"


def ingest(paths, day):
    """Apply queued inbox operations in order.

    The inbox is rewritten after every operation so an interrupted run never applies a line twice;
    failed lines stay in the inbox for the next run.
    """
    ops = inbox_model.read(paths)
    rows = episode_model.load(paths)
    renames, results, kept = {}, [], []
    for index, op in enumerate(ops):
        try:
            outcome = apply_op(paths, op, rows, renames, day)
        except (AnchorError, KeyError, TypeError, ValueError) as error:
            outcome = "failed:" + str(error)
            kept.append(op)
            rows = episode_model.load(paths)
        results.append((op["op"], op.get("id"), outcome))
        inbox_model.write(paths, kept + ops[index + 1:], day)
    return results


def validate_all(paths):
    """Return (errors, warnings) across every anchor-training data file."""
    errors, warnings = [], []
    episode_ids = set()
    try:
        rows = read_jsonl(paths.episodes)
    except AnchorError as error:
        return [str(error)], []
    for row in rows:
        row_errors, row_warnings = episode_model.validate(row)
        errors += [f"episode {row.get('id')}: {item}" for item in row_errors]
        warnings += [f"episode {row.get('id')}: {item}" for item in row_warnings]
        if row.get("id") in episode_ids:
            errors.append(f"episode {row.get('id')}: duplicate_id")
        episode_ids.add(row.get("id"))
    def check_drills():
        return [f"drill {row.get('id')}: {item}" for row in read_jsonl(paths.drills_log)
                for item in drill_model.validate(row)]

    def check_ladder():
        return ["ladder: no rungs"] if paths.ladder.exists() and not load_rungs(paths) else []

    def check_actions():
        if paths.actions.exists():
            action_model.parse(read_text(paths.actions))
        return []

    def check_inbox():
        inbox_model.read(paths)
        return []

    for name, check in (("drills", check_drills), ("views", lambda: view_model.validate(load_views(paths))),
                        ("ladder", check_ladder), ("actions", check_actions), ("inbox", check_inbox)):
        try:
            errors += check()
        except AnchorError as error:
            errors.append(f"{name}: {error}")
    try:
        for scene in scene_model.load_all(paths):
            scene_errors, scene_warnings = scene_model.validate(scene, episode_ids)
            errors += [f"scene {scene.id}: {item}" for item in scene_errors]
            warnings += [f"scene {scene.id}: {item}" for item in scene_warnings]
    except AnchorError as error:
        errors.append(f"scenes: {error}")
    return errors, warnings
