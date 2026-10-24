"""Find relationship and emotion material in my own messages and check extractions word for word."""

from collections import Counter
import json
from pathlib import Path
import random
import re

from . import episodes as episode_model
from . import now as now_model
from .scenes import Scene, scene_id_for
from .scenes import validate as validate_scene
from .store import AnchorError, frontmatter, read_jsonl

LEXICON = (
    "女朋友", "女友", "前任", "分手", "复合", "恋爱", "约会", "吵架", "冷战", "不安", "焦虑", "恐慌",
    "害怕", "难受", "心慌", "胸口", "心跳", "想她", "找她", "联系她", "回消息", "不回", "已读", "拉黑",
    "依恋", "安全感", "患得患失", "异性", "暧昧", "挽回", "亲密", "委屈", "尊重", "边界", "拒绝", "说不",
    "讨好", "内疚", "愧疚", "主体性", "抛锚", "咨询师", "她说", "她跟我", "她不", "她要", "她想", "她又",
    "跟她", "和她", "对象", "喜欢她", "爱她", "在一起", "失恋", "girlfriend", "breakup", "attachment",
)
PATTERN = re.compile("|".join(map(re.escape, LEXICON)), re.I)
SOURCES = ("claude",)
ALL_SOURCES = ("claude", "claude_ai", "claude-code", "claude-design")
REF = re.compile(r"(raw/conversations/\d{4}-\d{2}/[A-Za-z0-9_.-]+\.jsonl)#(.+)\Z")
MISS_TEXT = {True: "没做到", False: "做到了", None: "—"}
ELLIPSIS = re.compile(r"…+|\.\.\.+")


def normalize(text):
    return re.sub(r"\s+", "", text or "")


def conversation_files(repo, sources=SOURCES):
    groups = {}
    for path in sorted((repo / "raw/conversations").glob("*/*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
        try:
            meta = json.loads(first)
        except ValueError:
            continue
        if meta.get("type") != "meta" or meta.get("source") not in sources:
            continue
        groups.setdefault(meta["conversation_id"], []).append(path)
    return groups


def read_conversation(repo, paths):
    """Reassemble split message parts; returns messages ordered by sequence with their file."""
    pieces = {}
    for path in paths:
        relative = path.relative_to(repo).as_posix()
        for row in read_jsonl(path)[1:]:
            if row.get("type") != "message":
                continue
            entry = pieces.setdefault(row["message_key"], {"parts": {}, "row": row, "file": relative})
            entry["parts"][row["part_index"]] = row["text"]
    messages = []
    for entry in pieces.values():
        row = entry["row"]
        parts = entry["parts"]
        if sorted(parts) != list(range(row["part_count"])):
            continue
        messages.append({"id": row.get("id") or row["message_key"], "role": row["role"],
                         "timestamp": row.get("timestamp"), "sequence": row["sequence"],
                         "file": entry["file"], "text": "".join(parts[index] for index in sorted(parts))})
    messages.sort(key=lambda item: item["sequence"])
    return messages


def titles(repo):
    """Conversation names from the archived export records (latest export wins)."""
    fragments = {}
    for path in sorted((repo / "raw/exports/claude/conversations").glob("*.jsonl")):
        rows = read_jsonl(path)
        if not rows or rows[0].get("type") != "meta":
            continue
        meta = rows[0]
        key = (meta.get("conversation_id"), meta.get("source_sha256"))
        for row in rows[1:]:
            if row.get("type") == "source_file":
                fragments.setdefault(key, {})[row["part_index"]] = (row["part_count"], row["text"])
    result = {}
    for (identity, _), parts in fragments.items():
        count = next(iter(parts.values()))[0]
        if identity is None or sorted(parts) != list(range(count)):
            continue
        try:
            record = json.loads("".join(parts[index][1] for index in range(count)))
        except ValueError:
            continue
        stamp = record.get("updated_at") or ""
        if identity not in result or stamp > result[identity][1]:
            result[identity] = (record.get("name") or "", stamp)
    return {identity: name for identity, (name, _) in result.items()}


def candidates(repo, min_hits=2, sources=SOURCES):
    """Conversations with at least `min_hits` keyword hits in my messages, densest first."""
    found = []
    names = titles(repo)
    for identity, paths in conversation_files(repo, sources).items():
        messages = read_conversation(repo, paths)
        mine = [message for message in messages if message["role"] == "user"]
        hits = Counter()
        flagged = 0
        for message in mine:
            words = PATTERN.findall(message["text"])
            message["hits"] = sorted(set(words))
            if words:
                flagged += 1
                hits.update(words)
        if flagged >= min_hits or (flagged and len(mine) <= 3):
            stamps = [message["timestamp"] for message in messages if message["timestamp"]]
            found.append({"conversation_id": identity, "title": names.get(identity, ""),
                          "first": min(stamps) if stamps else None, "last": max(stamps) if stamps else None,
                          "user_messages": len(mine), "hit_messages": flagged,
                          "top_hits": hits.most_common(6), "messages": messages})
    found.sort(key=lambda item: (-item["hit_messages"], item["conversation_id"]))
    return found


def shard_text(conversation, assistant_chars=240):
    """A compact reading copy for classification: my messages in full, replies abbreviated."""
    lines = [f"# {conversation['title'] or conversation['conversation_id']}",
             f"conversation_id: {conversation['conversation_id']}",
             f"range: {conversation['first']} — {conversation['last']}", ""]
    for message in conversation["messages"]:
        if message["role"] == "tool":
            continue
        text = message["text"]
        if message["role"] == "assistant":
            text = " ".join(text.replace("This block is not supported on your current device yet.", "")
                            .replace("```", "").split())
            text = text[:assistant_chars] + ("…" if len(text) > assistant_chars else "")
            lines.append(f"[assistant {message['timestamp'] or ''}] {text}")
        else:
            marker = " HIT:" + ",".join(message["hits"]) if message.get("hits") else ""
            lines.append(f"\n[user {message['timestamp'] or ''} ref={message['file']}#{message['id']}{marker}]")
            lines.append(text)
        lines.append("")
    return "\n".join(lines)


def write_shards(repo, out, min_hits=2, budget=60_000):
    """Write reading copies grouped into shards of roughly `budget` characters each."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    found = candidates(repo, min_hits)
    shards, current, size = [], [], 0
    for conversation in found:
        text = shard_text(conversation)
        if current and size + len(text) > budget:
            shards.append(current)
            current, size = [], 0
        current.append((conversation, text))
        size += len(text)
    if current:
        shards.append(current)
    manifest = []
    for number, shard in enumerate(shards, 1):
        name = f"shard-{number:02d}.md"
        (out / name).write_text("\n\n".join(text for _, text in shard), encoding="utf-8")
        manifest.append({"shard": name, "conversations": [item["conversation_id"] for item, _ in shard],
                         "chars": sum(len(text) for _, text in shard)})
    summary = [{key: item[key] for key in ("conversation_id", "title", "first", "last", "user_messages",
                                          "hit_messages", "top_hits")} for item in found]
    (out / "manifest.json").write_text(json.dumps({"shards": manifest, "conversations": summary},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest, summary


def message_index(repo, refs):
    """Resolve `raw/...jsonl#id` references to message text, reading each conversation once."""
    parsed = [(ref, REF.fullmatch(ref or "")) for ref in refs]
    owner = {}
    for _, match in parsed:
        if match and match.group(1) not in owner and (repo / match.group(1)).is_file():
            with (repo / match.group(1)).open(encoding="utf-8") as handle:
                owner[match.group(1)] = json.loads(handle.readline()).get("conversation_id")
    files = conversation_files(repo, sources=ALL_SOURCES)
    messages = {}
    for identity in set(owner.values()):
        for message in read_conversation(repo, files.get(identity, [])):
            messages[(identity, message["id"])] = message
    resolved = {}
    for ref, match in parsed:
        if match and match.group(1) in owner:
            message = messages.get((owner[match.group(1)], match.group(2)))
            if message:
                resolved[ref] = message
    return resolved


def verbatim(quote, source):
    """True when every fragment of `quote` (split on …) appears in order in `source`."""
    position = 0
    haystack = normalize(source)
    for fragment in ELLIPSIS.split(quote or ""):
        fragment = normalize(fragment)
        if not fragment:
            continue
        found = haystack.find(fragment, position)
        if found < 0:
            return False
        position = found + len(fragment)
    return True


def verify(repo, rows, fields=("my_thought", "body")):
    """Check that quoted fields are my own words from the referenced message."""
    index = message_index(repo, [row.get("source_ref") for row in rows])
    problems = []
    for row in rows:
        message = index.get(row.get("source_ref"))
        if message is None:
            problems.append((row.get("id"), "source_ref_not_found"))
            continue
        if message["role"] != "user":
            problems.append((row.get("id"), "source_is_not_my_message"))
        for field in fields:
            if row.get(field) and not verbatim(row[field], message["text"]):
                problems.append((row.get("id"), f"{field}_not_verbatim"))
    return problems


def bigrams(text):
    text = normalize(text)
    return {text[index:index + 2] for index in range(len(text) - 1)}


def similar(left, right, threshold=0.5):
    a, b = bigrams(left), bigrams(right)
    return bool(a and b) and len(a & b) / len(a | b) >= threshold


def merge(repo, existing, candidates):
    """Validate, verify and number candidate episodes.

    Returns (new rows, rejected [(candidate, reason)], possible duplicates [(new id, other id)]).
    Candidates already present (same source and thought) are skipped, so re-running is idempotent.
    """
    problems = {}
    for identity, reason in verify(repo, [dict(row, id=str(n)) for n, row in enumerate(candidates)]):
        problems.setdefault(int(identity), reason)
    seen = {(row["source_ref"], normalize(row["my_thought"])) for row in existing}
    taken = {row["id"] for row in existing}
    queue = sorted(enumerate(candidates),
                   key=lambda item: (item[1].get("date") or "", item[1].get("source_ref") or "", item[0]))
    added, rejected = [], []
    for number, candidate in queue:
        if number in problems:
            rejected.append((candidate, problems[number]))
            continue
        key = (candidate.get("source_ref"), normalize(candidate.get("my_thought")))
        if key in seen:
            continue
        row = episode_model.blank()
        row.update(candidate)
        if row.get("outcome") is None and (row.get("outcome_fact") or "").strip():
            # A follow-up that does not settle the prediction is context, not an outcome.
            row["notes"] = "；".join(part for part in (row.get("notes"), "后续：" + row["outcome_fact"].strip()) if part)
            row["outcome_fact"] = ""
        row.setdefault("origin", "export")
        row.setdefault("review", "pending")
        try:
            row["id"] = episode_model.next_id(episode_model.parse_date(row["date"]), taken)
            episode_model.require_valid(row)
        except AnchorError as error:
            rejected.append((candidate, str(error)))
            continue
        taken.add(row["id"])
        seen.add(key)
        added.append(episode_model.ordered(row))
    duplicates = []
    pool = existing + added
    for row in added:
        for other in pool:
            if other["id"] < row["id"] and other["date"] == row["date"] and (
                    similar(other["trigger"], row["trigger"]) or similar(other["my_thought"], row["my_thought"])):
                duplicates.append((row["id"], other["id"]))
    return added, rejected, duplicates


def scenes_from(rows, candidates):
    """Turn scene candidates into Scene objects linked to the episode they came from."""
    built, rejected = [], []
    used = set()
    for candidate in candidates:
        matches = [row for row in rows if row["source_ref"] == candidate.get("source_ref")
                   and row["date"] == candidate.get("date")]
        if not matches:
            rejected.append((candidate, "episode_not_found"))
            continue
        text = candidate.get("text") or ""
        row = max(matches, key=lambda item: len(bigrams(text) & bigrams(item["my_thought"] + item["trigger"])))
        identity = scene_id_for(row["id"])
        if identity in used:
            rejected.append((candidate, "duplicate_scene_for_episode"))
            continue
        cue = (candidate.get("cue") or "").strip() or now_model.shorten(row["trigger"], 40)
        script = (candidate.get("script") or "").strip() or now_model.choose_script(row["trigger"], row["my_thought"])
        suds = candidate.get("suds_expected")
        if type(suds) is not int:
            suds = row["suds_peak"] if row["suds_peak"] is not None else 60
        conditions = tuple(candidate.get("conditions") or row["miss_conditions"])
        scene = Scene(identity, row["id"], suds, script, conditions, cue, text.strip())
        errors, _ = validate_scene(scene, {item["id"] for item in rows})
        if errors:
            rejected.append((candidate, ",".join(errors)))
            continue
        used.add(identity)
        built.append(scene)
    return built, rejected


def sample(rows, count, seed):
    pool = sorted(rows, key=lambda row: row["id"])
    if count > len(pool):
        raise AnchorError("sample_larger_than_population", f"{count}>{len(pool)}")
    return sorted(random.Random(seed).sample(pool, count), key=lambda row: row["id"])


def sample_report(repo, rows, seed, population, day, excerpt=700):
    """Side-by-side check sheet: extracted fields next to the original message."""
    index = message_index(repo, [row["source_ref"] for row in rows])
    lines = [frontmatter(f"抽取抽样核对 {day.isoformat()}", f"从 {population} 条 episode 随机抽 {len(rows)} 条，"
                         "与原文对照，交本人核对。", ["抽样核对", "extraction sample"], day),
             f"# 抽取抽样核对（{len(rows)}/{population}，seed {seed}）", "",
             "逐条看：触发是不是对方可观察的言行？我的想法、身体是不是我当时的原话？行动和结果有没有被改写？"
             "有问题直接在条目下写「错：……」，改完运行 `anchor.py validate`。", ""]
    for number, row in enumerate(rows, 1):
        message = index.get(row["source_ref"])
        original = message["text"] if message else "（原文未找到）"
        original = original if len(original) <= excerpt else original[:excerpt] + "…（截断）"
        lines += [f"## {number}. {row['id']}", "",
                  f"- 触发：{row['trigger']}",
                  f"- 我的想法：{row['my_thought']}",
                  f"- 身体：{row['body'] or '—'}",
                  f"- 冲动/确定：{row['urge'] if row['urge'] is not None else '—'} / "
                  f"{row['certainty'] if row['certainty'] is not None else '—'}",
                  f"- 行动：{row['action'] or '—'}｜脚本：{row['script_used'] or '—'}",
                  f"- 结果：{row['outcome'] or '无后续记录'}｜{row['outcome_fact'] or '—'}",
                  f"- miss：{MISS_TEXT[row['miss']]}｜条件：{'、'.join(row['miss_conditions']) or '—'}",
                  f"- 备注：{row['notes'] or '—'}",
                  f"- 出处：`{row['source_ref']}`", "",
                  "原文：", "", "> " + original.replace("\n", "\n> "), "",
                  "核对：□ 对　□ 错：", ""]
    return "\n".join(lines)
