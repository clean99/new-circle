"""/weekly: behaviour and calibration metrics. The point is what I did, not whether the thought was wrong."""

from datetime import date, timedelta
from statistics import mean, median

from .episodes import CHECKING, awaiting_fact
from .now import choose_script
from .store import frontmatter, parse_date

BUCKETS = ((0, 49), (50, 79), (80, 100))
ACTION_NAMES = {"checked": "去确认", "chased": "追问/挽留", "held": "忍住没确认", "said_ok": "说了「好」",
                "said_stop": "说了「先到这里」", "said_no": "说了不", "other": "其他"}


def week_bounds(label):
    year, week = label.split("-")
    start = date.fromisocalendar(int(year), int(week), 1)
    return start, start + timedelta(days=6)


def week_label(day):
    year, week, _ = day.isocalendar()
    return f"{year}-{week:02d}"


def in_range(rows, start, end):
    return [row for row in rows if start <= parse_date(row["date"]) <= end]


def ratio(numerator, denominator):
    return None if not denominator else numerator / denominator


def pct(value):
    return "—" if value is None else f"{round(value * 100)}%"


def num(value, digits=1):
    return "—" if value is None else f"{value:.{digits}f}"


def calibration(rows):
    """Stated certainty vs how often the predicted thing actually happened (verifiable outcomes only)."""
    scored = [row for row in rows if row.get("certainty") is not None
              and row.get("outcome") in {"happened", "not_happened"}]
    buckets = []
    for low, high in BUCKETS:
        items = [row for row in scored if low <= row["certainty"] <= high]
        if items:
            buckets.append({"range": f"{low}–{high}%", "n": len(items),
                            "certainty": mean(row["certainty"] for row in items) / 100,
                            "happened": ratio(sum(row["outcome"] == "happened" for row in items), len(items))})
    brier = (mean((row["certainty"] / 100 - (row["outcome"] == "happened")) ** 2 for row in scored)
             if scored else None)
    return {"n": len(scored), "buckets": buckets, "brier": brier,
            "certainty": mean(row["certainty"] for row in scored) / 100 if scored else None,
            "happened": ratio(sum(row["outcome"] == "happened" for row in scored), len(scored))}


def metrics(episode_rows, drill_rows, rungs, view_list, start, end):
    week = in_range(episode_rows, start, end)
    acted = [row for row in week if row.get("action")]
    judged = [row for row in week if row.get("miss") is not None]
    urges = [row["urge"] for row in week if row.get("urge") is not None]
    recovery = [row["recovery_minutes"] for row in week if row.get("recovery_minutes") is not None]
    trend = []
    for back in range(3, -1, -1):
        week_start, week_end = start - timedelta(days=7 * back), end - timedelta(days=7 * back)
        values = [row["urge"] for row in in_range(episode_rows, week_start, week_end)
                  if row.get("urge") is not None]
        trend.append((week_label(week_start), mean(values) if values else None, len(values)))
    drills = in_range(drill_rows, start, end)
    before = [row["suds_before"] for row in drills if row.get("suds_before") is not None]
    after = [row["suds_after"] for row in drills if row.get("suds_after") is not None]
    ladder_done = [(rung, record) for rung in rungs for record in rung.completions
                   if start <= record[0] <= end]
    reviewed = [view for view in view_list if view.last and start <= view.last <= end]
    pending = [row for row in episode_rows if awaiting_fact(row) and parse_date(row["date"]) <= end]
    return {
        "episodes": len(week),
        "no_check_rate": ratio(sum(row["action"] not in CHECKING for row in acted), len(acted)),
        "acted": len(acted),
        "execution_rate": ratio(sum(row["miss"] is False for row in judged), len(judged)),
        "judged": len(judged),
        "urge_mean": mean(urges) if urges else None,
        "urge_trend": trend,
        "calibration_week": calibration(week),
        "calibration_all": calibration([row for row in episode_rows if parse_date(row["date"]) <= end]),
        "recovery_median": median(recovery) if recovery else None,
        "unverifiable": sum(row.get("outcome") == "unverifiable" for row in week),
        "pending": len(pending),
        "pending_ids": [row["id"] for row in pending],
        "drills": len(drills),
        "suds_before": mean(before) if before else None,
        "suds_after": mean(after) if after else None,
        "within_3s": ratio(sum(row.get("within_3s") is True for row in drills),
                           sum(row.get("within_3s") is not None for row in drills)),
        "verbatim": ratio(sum(row.get("verbatim") is True for row in drills),
                          sum(row.get("verbatim") is not None for row in drills)),
        "held": ratio(sum(row.get("held_30s") is True for row in drills),
                      sum(row.get("held_30s") is not None for row in drills)),
        "ladder_done": ladder_done,
        "views_reviewed": len(reviewed),
        "actions": {name: sum(row.get("action") == key for row in week) for key, name in ACTION_NAMES.items()},
        "misses": [row for row in week if row.get("miss") is True],
        "miss_conditions": sorted({condition for row in week if row.get("miss")
                                   for condition in row.get("miss_conditions") or []}),
    }


def if_then(row):
    """For a miss, what I actually said is the behaviour to replace, so the plan uses the target script."""
    conditions = "、".join(row.get("miss_conditions") or []) or "____"
    script = choose_script(row.get("trigger"), row.get("my_thought"))
    return f"如果 {conditions}，那么我说「{script}」，说完停，然后去做____。"


def miss_review(row):
    return "\n".join([
        f"### {row['id']}（{row['date']}）",
        f"- 发生了什么（可观察）：{row.get('trigger') or '____'}",
        f"- 我想了什么：{row.get('my_thought') or '____'}",
        f"- 身体：{row.get('body') or '____'}",
        f"- 我做了什么：{ACTION_NAMES.get(row.get('action'), '____')}"
        + (f"（当时说：「{row['script_used']}」）" if row.get("script_used") else "")
        + (f"；{row['notes']}" if row.get("notes") else ""),
        f"- 下次 if-then：{if_then(row)}",
    ])


def counsellor_note(m, current_rung):
    parts = [f"这周我记录了 {m['episodes']} 次触发"]
    if m["acted"]:
        parts.append(f"其中 {m['acted']} 次记了行动，没有去确认的比例 {pct(m['no_check_rate'])}")
    if m["judged"]:
        parts.append(f"按脚本做到 {pct(m['execution_rate'])}（{m['judged']} 次）")
    if m["urge_mean"] is not None:
        parts.append(f"冲动平均 {num(m['urge_mean'])}/10")
    cal = m["calibration_all"]
    if cal["n"]:
        parts.append(f"累计 {cal['n']} 次可核实的预测里，我当时平均确定 {pct(cal['certainty'])}，"
                     f"实际发生 {pct(cal['happened'])}")
    if m["unverifiable"]:
        parts.append(f"{m['unverifiable']} 次无法核实")
    if m["drills"]:
        parts.append(f"演练 {m['drills']} 次，SUDS 平均 {num(m['suds_before'], 0)} → {num(m['suds_after'], 0)}")
    if current_rung:
        parts.append(f"阶梯在 {current_rung.id}「{current_rung.task}」")
    if m["miss_conditions"]:
        parts.append("没做到时的条件：" + "、".join(m["miss_conditions"]))
    return "；".join(parts) + "。想和你讨论的一件事：____。"


def render(label, m, current_rung, day):
    cal_week, cal_all = m["calibration_week"], m["calibration_all"]
    meta = frontmatter(f"抛锚训练周复盘 {label}", f"{label} 周的未确认率、执行率、冲动、校准、恢复、演练与阶梯进度。",
                       [f"weekly {label}", f"周复盘 {label}"], day)
    lines = [meta, f"# 周复盘 {label}", "",
             "指标看的是我做了什么、我的确定程度准不准；想法成真时流程照常成立。", "",
             "## 行为", "",
             "| 指标 | 本周 |", "|---|---|",
             f"| 触发记录 | {m['episodes']} |",
             f"| 未确认率（没去确认/追问） | {pct(m['no_check_rate'])}（{m['acted']} 次有行动记录） |",
             f"| 执行率（按脚本做到） | {pct(m['execution_rate'])}（{m['judged']} 次） |",
             f"| 冲动均值 | {num(m['urge_mean'])}/10 |",
             f"| 恢复时间中位数 | {num(m['recovery_median'], 0)} 分钟 |",
             f"| 无法核实 | {m['unverifiable']} |",
             f"| 待回填事实（累计） | {m['pending']} |", "",
             "行动分布：" + ("，".join(f"{name} {count}" for name, count in m["actions"].items() if count)
                         or "无"), "",
             "冲动趋势（近 4 周）：" + "，".join(f"{label_} {num(value)}（{count}）"
                                           for label_, value, count in m["urge_trend"]), "",
             "## 校准", "",
             f"本周可核实 {cal_week['n']} 次；累计 {cal_all['n']} 次，平均确定 {pct(cal_all['certainty'])}，"
             f"实际发生 {pct(cal_all['happened'])}，Brier {num(cal_all['brier'], 2)}（越低越准）。", ""]
    if cal_all["buckets"]:
        lines += ["| 当时确定 | 次数 | 平均确定 | 实际发生 |", "|---|---|---|---|"]
        lines += [f"| {bucket['range']} | {bucket['n']} | {pct(bucket['certainty'])} | {pct(bucket['happened'])} |"
                  for bucket in cal_all["buckets"]]
        lines.append("")
    lines += ["## 演练与阶梯", "",
              f"- 演练 {m['drills']} 次；SUDS 前 {num(m['suds_before'], 0)} → 后 {num(m['suds_after'], 0)}；"
              f"3 秒内 {pct(m['within_3s'])}，照字 {pct(m['verbatim'])}，停住 {pct(m['held'])}。",
              f"- 见地复习 {m['views_reviewed']} 条。",
              "- 阶梯完成：" + ("；".join(f"{rung.id} {record[0].isoformat()} SUDS {record[1]}"
                                     for rung, record in m["ladder_done"]) or "无"),
              f"- 当前阶梯：{current_rung.id + ' ' + current_rung.task if current_rung else '全部完成'}", "",
              "## 没做到的复盘", ""]
    if m["misses"]:
        lines += [miss_review(row) + "\n" for row in m["misses"]]
    else:
        lines += ["本周没有记录 miss。", ""]
    if m["pending_ids"]:
        lines += ["## 待回填事实", "", "、".join(m["pending_ids"]), ""]
    lines += ["## 给咨询师的话", "", counsellor_note(m, current_rung), ""]
    return "\n".join(lines)
