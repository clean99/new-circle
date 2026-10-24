"""每日 10 分钟演练: scene selection, the spoken flow and the practice log."""

from collections import Counter
from datetime import timedelta
import re

from . import views as view_model
from .store import AnchorError, frontmatter, parse_date, read_jsonl, write_jsonl

SCENE_INTERVALS = (2, 4, 7, 14, 30)
DRILL_ID = re.compile(r"dr-(\d{4}-\d{2}-\d{2})-(\d{2})\Z")
FIELDS = ("id", "date", "scene", "view", "hot", "suds_before", "suds_after", "within_3s",
          "verbatim", "held_30s", "notes")
LOW_SUDS = 40
MISS_WINDOW = timedelta(days=14)
CHANNELS = ("文字", "电话", "当面")


def validate(row):
    errors = []
    match = DRILL_ID.fullmatch(row.get("id") or "")
    if not match:
        errors.append("invalid_id")
    try:
        day = parse_date(row.get("date"))
        if match and match.group(1) != day.isoformat():
            errors.append("id_date_mismatch")
    except AnchorError:
        errors.append("invalid_date")
    if not isinstance(row.get("scene"), str) or not row["scene"].startswith("sc-"):
        errors.append("scene_required")
    if row.get("view") is not None and not isinstance(row.get("view"), str):
        errors.append("invalid_view")
    for field in ("suds_before", "suds_after"):
        value = row.get(field)
        if value is not None and (type(value) is not int or not 0 <= value <= 100):
            errors.append(f"{field}_out_of_range")
    for field in ("hot", "within_3s", "verbatim", "held_30s"):
        if row.get(field) is not None and not isinstance(row.get(field), bool):
            errors.append(f"{field}_must_be_boolean")
    if not isinstance(row.get("notes", ""), str):
        errors.append("notes_must_be_text")
    unknown = set(row) - set(FIELDS)
    if unknown:
        errors.append("unknown_fields:" + ",".join(sorted(unknown)))
    return errors


def load(paths):
    rows = read_jsonl(paths.drills_log)
    for row in rows:
        errors = validate(row)
        if errors:
            raise AnchorError("invalid_drill", f"{row.get('id')}: {', '.join(errors)}")
    return rows


def without_id(row):
    return {key: value for key, value in row.items() if key != "id"}


def record(paths, row):
    """Append one drill. Re-recording the same drill (with or without its id) is a no-op."""
    rows = load(paths)
    row = ordered(row)
    if row["id"]:
        existing = next((item for item in rows if item["id"] == row["id"]), None)
        if existing is not None:
            if existing == row:
                return existing, False
            raise AnchorError("drill_id_conflict", row["id"])
    else:
        existing = next((item for item in rows if without_id(item) == without_id(row)), None)
        if existing is not None:
            return existing, False
        prefix = "dr-" + str(row["date"]) + "-"
        used = {int(item["id"][len(prefix):]) for item in rows if item["id"].startswith(prefix)}
        free = [number for number in range(1, 100) if number not in used]
        if not free:
            raise AnchorError("too_many_drills_for_day", str(row["date"]))
        row["id"] = prefix + f"{free[0]:02d}"
    errors = validate(row)
    if errors:
        raise AnchorError("invalid_drill", ", ".join(errors))
    rows.append(row)
    rows.sort(key=lambda item: item["id"])
    write_jsonl(paths.drills_log, rows)
    return row, True


def ordered(row):
    defaults = {"view": None, "hot": False, "suds_before": None, "suds_after": None,
                "within_3s": None, "verbatim": None, "held_30s": None, "notes": ""}
    return {key: row.get(key, defaults.get(key)) for key in FIELDS}


def practice_state(drill_rows):
    """Per scene: (times practised, last date, recent low-SUDS count)."""
    state = {}
    for row in sorted(drill_rows, key=lambda item: item["id"]):
        count, _, low = state.get(row["scene"], (0, None, 0))
        suds = row.get("suds_before")
        low = low + 1 if suds is not None and suds < LOW_SUDS else 0
        state[row["scene"]] = (count + 1, parse_date(row["date"]), low)
    return state


def recent_miss_conditions(episode_rows, day):
    counts = Counter()
    for row in episode_rows:
        if row.get("miss") is True and day - parse_date(row["date"]) <= MISS_WINDOW:
            counts.update(row.get("miss_conditions") or [])
    return counts


def choose(scenes, state, misses, day):
    """Pick today's scene.

    Due scenes come first (spaced 2/4/7/14/30 days, so the same scene never runs two days in a row).
    Among them, scenes sharing conditions with misses in the last 14 days weigh most, unpractised scenes
    get a small bonus for variety, and a scene that felt below SUDS 40 twice in a row is pushed back so
    that a closer one comes up.
    """
    if not scenes:
        raise AnchorError("no_scenes", "generate scenes from episodes first")

    def rank(scene):
        count, last, low = state.get(scene.id, (0, None, 0))
        due = day if last is None else last + timedelta(days=SCENE_INTERVALS[min(count, len(SCENE_INTERVALS)) - 1])
        overdue = (day - due).days
        overlap = sum(misses.get(condition, 0) for condition in scene.conditions)
        fits = 1 if 40 <= scene.suds_expected <= 70 else 0
        novelty = 2 if count == 0 else 0
        too_easy = 5 if low >= 2 else 0
        weight = 3 * overlap + fits + novelty + min(overdue, 7) / 2 - too_easy
        return (overdue < 0, -weight, scene.id)

    return min(scenes, key=rank)


def channels_for(scene):
    named = [channel for channel in CHANNELS if channel in scene.conditions]
    rest = [channel for channel in CHANNELS if channel not in named]
    return (named + rest)[:3]


def script(scene, view, day, hot=False):
    """The 10-minute spoken flow. Short cues only; no long visualisation."""
    channels = channels_for(scene)
    lines = []
    lines.append(f"# 演练 {day.isoformat()}｜{scene.id}" + ("｜hot" if hot else ""))
    lines.append("")
    lines.append(f"练这一句：「{scene.script}」｜预期 SUDS {scene.suds_expected}"
                 + (f"｜重点条件：{'、'.join(scene.conditions)}" if scene.conditions else ""))
    lines.append("")
    if hot:
        lines += ["**0:00 先把心率拉上去（60 秒）**：爬楼或单车冲刺，喘着开始下一步。", ""]
    lines += [
        "**0:00–0:30 接地**：双脚踩实地面，感觉坐着的重量。慢慢呼气一次，比吸气长。只注意身体此刻的感觉，不用做别的。",
        "",
        "开始前打分：现在的不适度 SUDS（0–100）＝____",
        "",
        "**0:30–1:30 读剧本**：出声、慢慢读一遍，读到身体有反应就停一下，让它在。",
        "",
        "> " + scene.text.replace("\n", "\n> "),
        "",
        "**1:30–7:30 出声回应，共 3 轮**：每轮先在心里听到对方那句话，3 秒内出声说脚本，说完就停，不解释、不补一句。然后带着不舒服停留 30 秒：不做任何事，只注意身体哪里紧、哪里热，让它在。再自由呼吸 30 秒进入下一轮。",
        "",
    ]
    for number, channel in enumerate(channels, 1):
        lines.append(f"{number}. （{channel}）对方：「{scene.cue}」→ 我：「{scene.script}」→ 停 30 秒")
    lines.append("")
    if view:
        lines += [f"**7:30–8:30 见地 {view.id}**：读两遍，第二遍出声。", "", f"> {view.text}", ""]
    else:
        lines += ["**7:30–8:30 见地**：今天没有到期的见地，安静坐一分钟。", ""]
    lines += [
        "**8:30–9:30 收尾打分**：结束 SUDS＝____；3 秒内说出口了吗？照字说了吗？说完停住了吗？",
        "",
        "**9:30–10:00 记录**：把四个数和三个是/否发给 bot，或运行：",
        "",
        "```bash",
        f"python3 scripts/anchor.py drill log --scene {scene.id}"
        + (f" --view {view.id}" if view else "") + (" --hot" if hot else "")
        + " --suds-before N --suds-after N --within-3s yes --verbatim yes --held yes",
        "```",
    ]
    return "\n".join(lines) + "\n"


def narration(scene, view, hot=False, say_markup=False):
    """Plain text for TTS. Pauses are `[停 N 秒]`, or macOS `say` silence commands with say_markup."""

    def pause(seconds):
        return f"[[slnc {seconds * 1000}]]" if say_markup else f"[停 {seconds} 秒]"

    parts = []
    if hot:
        parts.append("先爬楼或者单车冲刺六十秒，喘着开始。" + pause(60))
    parts += ["双脚踩实地面，感觉坐着的重量。慢慢呼气一次，比吸气长。" + pause(20),
              "给现在的不舒服打个分，零到一百。" + pause(5),
              "出声读剧本。" + pause(2), scene.text + pause(5)]
    for channel in channels_for(scene):
        parts += [f"{channel}。对方说：{scene.cue}" + pause(3),
                  "说完了就停。带着不舒服待在这里。" + pause(30), "自由呼吸。" + pause(30)]
    if view:
        parts += ["见地。" + view.text + pause(3), "再出声读一遍。" + pause(8)]
    parts.append("再打一次分。三秒内说出口了吗？照字说了吗？说完停住了吗？")
    return "\n".join(parts) + "\n"


def plan(scenes, view_list, drill_rows, episode_rows, start, days):
    """Simulate a week of drills, assuming each day is done, and return (day, scene, view) tuples."""
    state = practice_state(drill_rows)
    views = list(view_list)
    used_views = set()
    result = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        scene = choose(scenes, state, recent_miss_conditions(episode_rows, day), day)
        count, _, low = state.get(scene.id, (0, None, 0))
        state[scene.id] = (count + 1, day, low)
        candidates = [view for view in views if view.due <= day and view.id not in used_views]
        candidates.sort(key=lambda view: (view.due, view.id))
        if not candidates:
            candidates = sorted((view for view in views if view.id not in used_views),
                                key=lambda view: (view.due, view.id))
        view = candidates[0] if candidates else None
        if view:
            used_views.add(view.id)
            views[views.index(view)] = view_model.reviewed(view, day)
        result.append((day, scene, view))
    return result


def render_plan_file(day, number, scene, view, hot):
    meta = frontmatter(f"演练稿 {day.isoformat()}", f"第 {number} 天的 10 分钟演练流程稿：剧本 {scene.id}"
                       + (f"，见地 {view.id}" if view else "") + "。",
                       [f"drill {day.isoformat()}"], day,
                       extra=[f"scene: {scene.id}", f"view: {view.id if view else ''}",
                              f"hot: {'true' if hot else 'false'}"])
    return meta + "\n" + script(scene, view, day, hot)
