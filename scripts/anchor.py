#!/usr/bin/env python3
"""anchor-training: 抛锚与主体性训练. Records and schedules live in the Life OS checkout."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from anchor_core import drills as drill_model  # noqa: E402
from anchor_core import episodes as episode_model  # noqa: E402
from anchor_core import extract as extract_model  # noqa: E402
from anchor_core import ladder as ladder_model  # noqa: E402
from anchor_core import now as now_model  # noqa: E402
from anchor_core import scenes as scene_model  # noqa: E402
from anchor_core import service  # noqa: E402
from anchor_core import views as view_model  # noqa: E402
from anchor_core import weekly as weekly_model  # noqa: E402
from anchor_core.store import (  # noqa: E402
    AREA, TZ, AnchorError, now, parse_date, read_jsonl, resolve_repo, sync_state, write_markdown)


def yes_no(value):
    lowered = value.lower()
    if lowered in {"yes", "y", "true", "1", "是"}:
        return True
    if lowered in {"no", "n", "false", "0", "否"}:
        return False
    raise argparse.ArgumentTypeError("expected yes or no")


def conditions(value):
    return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]


def emit(args, data, text_lines):
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print("\n".join(text_lines))


def moment(args):
    if args.today:
        return datetime.combine(parse_date(args.today), datetime.now(TZ).time(), TZ)
    return now()


def cmd_status(args, paths, day):
    rows = episode_model.load(paths)
    due = episode_model.due_follow_ups(rows, moment(args))
    view = view_model.due(service.load_views(paths), day)
    rung = ladder_model.current(service.load_rungs(paths))
    queued = len(service.inbox_model.read(paths))
    ladder_text = "未建立（anchor.py init）"
    if paths.ladder.exists():
        ladder_text = f"{rung.id} {rung.task}" if rung else "全部完成"
    lines = [f"episodes {len(rows)}｜待回填 {len(due)}｜inbox {queued}",
             "今日见地：" + (f"{view.id} {view.text}" if view else "无到期"),
             "阶梯：" + ladder_text]
    if not paths.area.exists():
        lines.insert(0, f"{AREA} 不存在：先 git pull，或运行 anchor.py init。")
    lines += [f"追问事实：{row['id']}（{state}）{now_model.shorten(row['my_thought'])}" for row, state in due]
    sync = sync_state(paths.repo)
    if sync and sync[1]:
        lines.append(f"注意：Life OS 落后远端 {sync[1]} 个提交" + (f"、本地多 {sync[0]} 个" if sync[0] else "")
                     + "，先 git pull --rebase 再写。")
    emit(args, {"episodes": len(rows), "due": [row["id"] for row, _ in due], "inbox": queued,
                "view": view.id if view else None, "rung": rung.id if rung else None,
                "sync": {"ahead": sync[0], "behind": sync[1]} if sync else None}, lines)


def cmd_now(args, paths, day):
    row = service.record_now(paths, {
        "trigger": args.trigger, "my_thought": args.thought, "body": args.body or "",
        "urge": args.urge, "certainty": args.certainty, "action": args.action,
        "script_used": args.script, "source_ref": args.source_ref,
        "miss_conditions": conditions(args.conditions) if args.conditions else [],
    }, at=moment(args))
    category, item = service.next_action(paths, row["id"])
    lines = now_model.reply(row, item, needs_reply=not args.no_reply)
    emit(args, {"episode": row, "do_now": {"category": category, "item": item}, "reply": lines}, lines)


def cmd_act(args, paths, day):
    row = service.update_episode(paths, args.id, action=args.action, script_used=args.script,
                                 miss=args.miss, recovery_minutes=args.recovery_minutes,
                                 suds_peak=args.suds_peak,
                                 miss_conditions=conditions(args.conditions) if args.conditions else None,
                                 notes=args.notes)
    emit(args, {"episode": row}, [f"已更新 {row['id']}：action={row['action']} miss={row['miss']}"])


def cmd_fact(args, paths, day):
    row, warnings = service.backfill(
        paths, args.id, args.outcome, args.fact, observed=args.observed,
        recovery_minutes=args.recovery_minutes, suds_peak=args.suds_peak, action=args.action,
        miss=args.miss, miss_conditions=conditions(args.conditions) if args.conditions else None)
    lines = [f"已回填 {row['id']}：{row['outcome']}｜{row['outcome_fact']}"]
    if "explanation_recorded_as_unverifiable" in warnings:
        lines.append("对方的解释不算可观察事实，记为 unverifiable。若这是你亲眼看到的事，加 --observed。")
    emit(args, {"episode": row, "warnings": warnings}, lines)


def cmd_due(args, paths, day):
    due = episode_model.due_follow_ups(episode_model.load(paths), moment(args))
    lines = [f"{row['id']}（{state}）想法：{now_model.shorten(row['my_thought'])}｜问：后来可观察到的事实是什么？"
             for row, state in due] or ["没有待回填的事实。"]
    emit(args, {"due": [{"id": row["id"], "state": state} for row, state in due]}, lines)


def cmd_drill(args, paths, day):
    scenes = scene_model.load_all(paths)
    if args.scene:
        scene = next((item for item in scenes if item.id == args.scene), None)
        if scene is None:
            raise AnchorError("scene_not_found", args.scene)
    else:
        state = drill_model.practice_state(drill_model.load(paths))
        misses = drill_model.recent_miss_conditions(episode_model.load(paths), day)
        scene = drill_model.choose(scenes, state, misses, day)
    view = view_model.due(service.load_views(paths), day)
    text = drill_model.script(scene, view, day, hot=args.hot)
    data = {"scene": scene.id, "view": view.id if view else None, "script": text}
    if args.narration:
        target = Path(args.narration)
        target.write_text(drill_model.narration(scene, view, args.hot, args.say_markup), encoding="utf-8")
        data["narration"] = str(target)
        text += f"\n语音稿已写入 {target}\n"
    emit(args, data, [text])


def cmd_drill_log(args, paths, day):
    row = {"date": day.isoformat(), "scene": args.scene, "view": args.view, "hot": args.hot,
           "suds_before": args.suds_before, "suds_after": args.suds_after, "within_3s": args.within_3s,
           "verbatim": args.verbatim, "held_30s": args.held, "notes": args.notes or ""}
    saved, added = service.log_drill(paths, row, day)
    emit(args, {"drill": saved, "added": added},
         [("已记录 " if added else "已存在 ") + saved["id"]
          + f"：SUDS {saved['suds_before']} → {saved['suds_after']}"])


def cmd_drill_plan(args, paths, day):
    start = parse_date(args.start) if args.start else day
    hot_days = {int(item) for item in conditions(args.hot_days)} if args.hot_days else set()
    plan = drill_model.plan(scene_model.load_all(paths), service.load_views(paths),
                            drill_model.load(paths), episode_model.load(paths), start, args.days)
    written = []
    for number, (when, scene, view) in enumerate(plan, 1):
        path = paths.drills / f"{when.isoformat()}.md"
        write_markdown(path, drill_model.render_plan_file(when, number, scene, view, number in hot_days), day)
        written.append(paths.relative(path))
    emit(args, {"written": written}, [f"写入 {path}" for path in written])


def cmd_ladder(args, paths, day):
    if not paths.ladder.exists():
        raise AnchorError("ladder_missing", "git pull, or run anchor.py init")
    rungs = service.load_rungs(paths)
    rung = ladder_model.current(rungs)
    if rung is None:
        emit(args, {"rung": None}, ["阶梯全部完成。和咨询师一起定下一级。"])
        return
    done = len(rung.completions)
    emit(args, {"rung": rung.id, "zone": rung.zone, "task": rung.task, "completions": done},
         [f"下一级 {rung.id}（{rung.zone}）：{rung.task}",
          f"已完成 {done} 次。做完告诉我日期和 SUDS（0–100）；两次完成且最近一次 ≤ 40 就升级。"])


def cmd_ladder_done(args, paths, day):
    rung = service.complete_rung(paths, args.id, parse_date(args.date) if args.date else day, args.suds,
                                 args.note or "")
    upcoming = ladder_model.current(service.load_rungs(paths))
    lines = [f"已记录 {rung.id} 完成｜SUDS {args.suds}" + ("｜本级已过" if rung.cleared else "")]
    if upcoming:
        lines.append(f"下一级：{upcoming.id} {upcoming.task}")
    emit(args, {"rung": rung.id, "cleared": rung.cleared, "next": upcoming.id if upcoming else None}, lines)


def cmd_view(args, paths, day):
    views = service.load_views(paths)
    view = view_model.due(views, day)
    if view is None:
        upcoming = view_model.upcoming(views)
        emit(args, {"view": None, "next_due": upcoming.due if upcoming else None},
             ["今天没有到期的见地" + (f"，下一条 {upcoming.id} 在 {upcoming.due}。" if upcoming else "。")])
        return
    emit(args, {"view": view.id, "text": view.text, "source": view.source},
         [f"{view.id}：{view.text}", f"出处：{view.source}", "读两遍，第二遍出声。读完说「记住了」或「没进去」。"])


def cmd_view_done(args, paths, day):
    view = service.mark_view(paths, args.id, day, remembered=not args.again)
    emit(args, {"view": view.id, "next_due": view.due}, [f"{view.id} 下次复习 {view.due}"])


def cmd_weekly(args, paths, day):
    label = args.week or weekly_model.week_label(day)
    start, end = weekly_model.week_bounds(label)
    rungs = service.load_rungs(paths)
    metrics = weekly_model.metrics(episode_model.load(paths), drill_model.load(paths), rungs,
                                   service.load_views(paths), start, end)
    text = weekly_model.render(label, metrics, ladder_model.current(rungs), day)
    if args.write:
        path = paths.weekly / f"{label}.md"
        write_markdown(path, text, day)
        text += f"\n已写入 {paths.relative(path)}\n"
    emit(args, {"week": label, "metrics": {key: value for key, value in metrics.items()
                                           if key not in {"misses", "ladder_done"}}}, [text])


def cmd_ingest(args, paths, day):
    results = service.ingest(paths, day)
    lines = [f"{kind} {identity or ''}: {outcome}" for kind, identity, outcome in results] or ["inbox 为空。"]
    emit(args, {"results": results}, lines)
    if any(outcome.startswith("failed") for _, _, outcome in results):
        raise SystemExit(1)


def cmd_validate(args, paths, day):
    errors, warnings = service.validate_all(paths)
    emit(args, {"errors": errors, "warnings": warnings},
         [f"error: {item}" for item in errors] + [f"warning: {item}" for item in warnings]
         + [f"anchor validate: {len(errors)} error(s), {len(warnings)} warning(s)"])
    if errors:
        raise SystemExit(1)


def cmd_extract_candidates(args, paths, day):
    manifest, summary = extract_model.write_shards(paths.repo, args.out, args.min_hits, args.budget)
    emit(args, {"shards": manifest, "conversations": len(summary)},
         [f"{len(summary)} 段对话，{len(manifest)} 个分片 → {args.out}"])


def cmd_extract_verify(args, paths, day):
    source = Path(args.file) if args.file else paths.episodes
    rows = read_jsonl(source)
    problems = extract_model.verify(paths.repo, rows)
    emit(args, {"checked": len(rows), "problems": problems},
         [f"{identity}: {problem}" for identity, problem in problems]
         + [f"verified {len(rows) - len({identity for identity, _ in problems})}/{len(rows)}"])
    if problems:
        raise SystemExit(1)


def read_inputs(files):
    rows = []
    for name in files:
        rows += read_jsonl(Path(name))
    return rows


def cmd_extract_merge(args, paths, day):
    existing = episode_model.load(paths)
    added, rejected, duplicates = extract_model.merge(paths.repo, existing, read_inputs(args.files))
    if args.write and added:
        episode_model.save(paths, existing + added)
    lines = [f"新增 {len(added)}，拒绝 {len(rejected)}，疑似重复 {len(duplicates)}" + ("" if args.write else "（未写入，加 --write）")]
    lines += [f"拒绝 {row.get('source_ref', '')[-40:]}: {reason}" for row, reason in rejected]
    lines += [f"疑似重复 {left} ~ {right}" for left, right in duplicates]
    emit(args, {"added": [row["id"] for row in added], "rejected": rejected, "duplicates": duplicates}, lines)


def cmd_extract_scenes(args, paths, day):
    rows = episode_model.load(paths)
    built, rejected = extract_model.scenes_from(rows, read_inputs(args.files))
    written = []
    for scene in built:
        target = paths.scenes / f"{scene.id}.md"
        if target.exists():
            continue
        episode = episode_model.find(rows, scene.episode)
        quote = (f"> {episode['my_thought'] or episode['trigger']}\n\n`{episode['source_ref']}`\n\n"
                 "预期 SUDS 是抽取时的预估，第一次练完按实际感受改。")
        if args.write:
            write_markdown(target, scene_model.render(scene, day, quote), day)
        written.append(paths.relative(target) if args.write else target.name)
    lines = [f"剧本 {len(written)}，拒绝 {len(rejected)}" + ("" if args.write else "（未写入，加 --write）")]
    lines += [f"拒绝 {row.get('source_ref', '')[-40:]}: {reason}" for row, reason in rejected]
    emit(args, {"written": written, "rejected": rejected}, lines)


def cmd_extract_sample(args, paths, day):
    rows = episode_model.load(paths)
    chosen = extract_model.sample(rows, args.n, args.seed)
    text = extract_model.sample_report(paths.repo, chosen, args.seed, len(rows), day)
    out = Path(args.out)
    out = out if out.is_absolute() else paths.repo / out
    write_markdown(out, text, day)
    emit(args, {"sampled": [row["id"] for row in chosen], "out": str(out)},
         [f"抽样 {len(chosen)}/{len(rows)} 条 → {out}"])


def cmd_init(args, paths, day):
    templates = Path(__file__).resolve().parents[1] / "templates"
    created = []
    for template in sorted(templates.glob("*.md")):
        target = paths.area / template.name
        if not target.exists():
            write_markdown(target, template.read_text(encoding="utf-8"), day)
            created.append(paths.relative(target))
    for directory in (paths.scenes, paths.drills, paths.weekly):
        directory.mkdir(parents=True, exist_ok=True)
    if not paths.episodes.exists():
        paths.episodes.write_text("", encoding="utf-8")
        created.append(paths.relative(paths.episodes))
    emit(args, {"created": created}, [f"创建 {item}" for item in created] or ["已存在，未改动。"])


def cmd_commit(args, paths, day):
    subprocess.run(["git", "-C", str(paths.repo), "add", "--", AREA], check=True)
    staged = subprocess.run(["git", "-C", str(paths.repo), "diff", "--cached", "--quiet", "--", AREA])
    if staged.returncode == 0:
        emit(args, {"committed": False}, ["没有变化，不提交。"])
        return
    subprocess.run(["git", "-C", str(paths.repo), "commit", "-q", "-m", args.message, "--", AREA], check=True)
    head = subprocess.run(["git", "-C", str(paths.repo), "rev-parse", "--short", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    emit(args, {"committed": True, "commit": head}, [f"已提交 {head}：{args.message}"])


def build_parser():
    parser = argparse.ArgumentParser(prog="anchor.py", description=__doc__)
    parser.add_argument("--repo", help="Life OS checkout (default: $LIFE_OS_REPO or the life-os skill location)")
    parser.add_argument("--today", help="override today (YYYY-MM-DD, Asia/Singapore)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="在 Life OS 里建 areas/relationship（不覆盖已有文件）").set_defaults(func=cmd_init)
    sub.add_parser("status", help="待回填、今日见地、阶梯位置").set_defaults(func=cmd_status)

    now_parser = sub.add_parser("now", help="触发时刻：记录 episode 并给出 ≤5 行回复")
    now_parser.add_argument("--trigger", required=True, help="对方可观察的言行，原话或客观描述")
    now_parser.add_argument("--thought", required=True, help="我此刻的想法，原话")
    now_parser.add_argument("--body", help="身体感受，原话")
    now_parser.add_argument("--certainty", type=int, help="这个想法有多确定 0–100（本人没给就不填，不估）")
    now_parser.add_argument("--urge", type=int, help="想去确认的冲动 0–10（本人没给就不填，不估）")
    now_parser.add_argument("--action", choices=episode_model.ACTIONS)
    now_parser.add_argument("--script", help="要说的最短脚本（默认按触发自动选）")
    now_parser.add_argument("--conditions", help="条件，逗号分隔：半夜,电话,刚见完面")
    now_parser.add_argument("--source-ref", help="原文位置 raw/...#message-id")
    now_parser.add_argument("--no-reply", action="store_true", help="不需要回对方")
    now_parser.set_defaults(func=cmd_now)

    act = sub.add_parser("act", help="补记我实际做了什么")
    act.add_argument("id")
    act.add_argument("--action", choices=episode_model.ACTIONS)
    act.add_argument("--script")
    act.add_argument("--miss", type=yes_no)
    act.add_argument("--recovery-minutes", type=int)
    act.add_argument("--suds-peak", type=int)
    act.add_argument("--conditions")
    act.add_argument("--notes")
    act.set_defaults(func=cmd_act)

    fact = sub.add_parser("fact", help="回填可观察事实")
    fact.add_argument("id")
    fact.add_argument("--outcome", required=True, choices=episode_model.OUTCOMES)
    fact.add_argument("--fact", default="", help="只写可观察的事；对方的解释记 unverifiable")
    fact.add_argument("--observed", action="store_true", help="确认这是亲眼/亲耳观察到的事实")
    fact.add_argument("--recovery-minutes", type=int)
    fact.add_argument("--suds-peak", type=int)
    fact.add_argument("--action", choices=episode_model.ACTIONS)
    fact.add_argument("--miss", type=yes_no)
    fact.add_argument("--conditions")
    fact.set_defaults(func=cmd_fact)

    sub.add_parser("due", help="到了 24–72 小时追问窗口的 episode").set_defaults(func=cmd_due)

    drill = sub.add_parser("drill", help="今天的 10 分钟演练稿")
    drill.add_argument("--hot", action="store_true", help="先 60 秒爬楼或单车冲刺")
    drill.add_argument("--scene")
    drill.add_argument("--narration", help="另存一份纯文本语音稿，供 TTS 使用")
    drill.add_argument("--say-markup", action="store_true", help="语音稿的停顿用 macOS say 的 [[slnc]] 标记")
    drill.set_defaults(func=cmd_drill)
    drill_sub = drill.add_subparsers(dest="drill_command")
    log = drill_sub.add_parser("log", help="记录一次演练")
    log.add_argument("--scene", required=True)
    log.add_argument("--view")
    log.add_argument("--hot", action="store_true")
    log.add_argument("--suds-before", type=int, required=True)
    log.add_argument("--suds-after", type=int, required=True)
    log.add_argument("--within-3s", type=yes_no, required=True)
    log.add_argument("--verbatim", type=yes_no, required=True)
    log.add_argument("--held", type=yes_no, required=True)
    log.add_argument("--notes")
    log.set_defaults(func=cmd_drill_log)
    plan = drill_sub.add_parser("plan", help="生成未来 N 天的演练稿")
    plan.add_argument("--start")
    plan.add_argument("--days", type=int, default=7)
    plan.add_argument("--hot-days", help="第几天做 hot 版，逗号分隔，如 3,6")
    plan.set_defaults(func=cmd_drill_plan)

    ladder = sub.add_parser("ladder", help="主体性阶梯的下一级")
    ladder.set_defaults(func=cmd_ladder)
    ladder_sub = ladder.add_subparsers(dest="ladder_command")
    done = ladder_sub.add_parser("done", help="记录完成")
    done.add_argument("id")
    done.add_argument("--suds", type=int, required=True)
    done.add_argument("--date")
    done.add_argument("--note")
    done.set_defaults(func=cmd_ladder_done)

    view = sub.add_parser("view", help="推一条到期见地")
    view.set_defaults(func=cmd_view)
    view_sub = view.add_subparsers(dest="view_command")
    view_done = view_sub.add_parser("done", help="复习完成，排下一次")
    view_done.add_argument("id")
    view_done.add_argument("--again", action="store_true", help="没进去，明天再来")
    view_done.set_defaults(func=cmd_view_done)

    weekly = sub.add_parser("weekly", help="周复盘")
    weekly.add_argument("--week", help="ISO 周，如 2026-44（默认本周）")
    weekly.add_argument("--write", action="store_true", help="写入 weekly/YYYY-WW.md")
    weekly.set_defaults(func=cmd_weekly)

    sub.add_parser("ingest", help="合并 inbox.md 队列").set_defaults(func=cmd_ingest)
    sub.add_parser("validate", help="检查全部数据").set_defaults(func=cmd_validate)

    extract = sub.add_parser("extract", help="历史素材抽取工具")
    extract_sub = extract.add_subparsers(dest="extract_command", required=True)
    candidates = extract_sub.add_parser("candidates", help="关键词初筛，写出分片阅读稿")
    candidates.add_argument("--out", required=True)
    candidates.add_argument("--min-hits", type=int, default=2)
    candidates.add_argument("--budget", type=int, default=60_000, help="每个分片的大致字符数")
    candidates.set_defaults(func=cmd_extract_candidates)
    verify = extract_sub.add_parser("verify", help="逐字核对 my_thought/body 是否为本人原话")
    verify.add_argument("file", nargs="?")
    verify.set_defaults(func=cmd_extract_verify)
    merge = extract_sub.add_parser("merge", help="把候选 episode 校验、去重、编号后并入 episodes.jsonl")
    merge.add_argument("files", nargs="+")
    merge.add_argument("--write", action="store_true")
    merge.set_defaults(func=cmd_extract_merge)
    scenes_cmd = extract_sub.add_parser("scenes", help="由剧本候选生成 scenes/<id>.md")
    scenes_cmd.add_argument("files", nargs="+")
    scenes_cmd.add_argument("--write", action="store_true")
    scenes_cmd.set_defaults(func=cmd_extract_scenes)
    sample = extract_sub.add_parser("sample", help="随机抽样，与原文对照，交本人核对")
    sample.add_argument("--n", type=int, default=20)
    sample.add_argument("--seed", type=int, required=True)
    sample.add_argument("--out", required=True, help="写入的 Markdown 路径（仓库内相对路径或绝对路径）")
    sample.set_defaults(func=cmd_extract_sample)

    commit = sub.add_parser("commit", help="只提交 areas/relationship 的改动")
    commit.add_argument("-m", "--message", default="fact: areas/relationship")
    commit.set_defaults(func=cmd_commit)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        paths = resolve_repo(args.repo)
        day = parse_date(args.today) if args.today else now().date()
        args.func(args, paths, day)
    except AnchorError as error:
        print(f"anchor: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
