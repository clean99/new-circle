"""Queue for clients that can only write Markdown (for example Claude.ai through the life-os MCP).

The queue is a fenced ```jsonl block inside areas/relationship/inbox.md. Each line is one
operation: {"op": "episode" | "fact" | "drill" | "ladder" | "view", ...}. `ingest` applies the
operations in order and keeps only the lines that failed.
"""

import json
import re

from . import episodes as episode_model
from .store import AnchorError, dumps, frontmatter, write_markdown

BLOCK = re.compile(r"```jsonl\n(.*?)```", re.S)
OPS = ("episode", "fact", "drill", "ladder", "view")

HEADER = """# 抛锚训练待合并队列

能读写 Markdown、但不能直接写 `episodes.jsonl` 的客户端（Claude.ai 经 life-os MCP、其他 bot）把操作追加到下面的代码块里，每行一个 JSON。本地运行 `anchor.py ingest` 时按顺序合并进正式数据，成功的行会被移除，失败的行保留并在终端报告原因。

格式见 anchor-training 技能的 `references/data-contract.md`。不要在这里写正文分析。

"""


def parse(text):
    match = BLOCK.search(text)
    if not match:
        return []
    ops = []
    for number, line in enumerate(match.group(1).splitlines(), 1):
        if not line.strip():
            continue
        try:
            op = json.loads(line)
        except ValueError:
            raise AnchorError("invalid_inbox_line", str(number)) from None
        if not isinstance(op, dict) or op.get("op") not in OPS:
            raise AnchorError("invalid_inbox_op", str(number))
        ops.append(op)
    return ops


def render(ops, day):
    meta = frontmatter("抛锚训练待合并队列", "MCP 客户端写入的 episode、事实回填、演练与阶梯记录，待本地脚本合并。",
                       ["anchor inbox", "抛锚队列"], day)
    lines = "".join(dumps(op) + "\n" for op in ops)
    return meta + "\n" + HEADER + "```jsonl\n" + lines + "```\n"


def read(paths):
    if not paths.inbox.exists():
        return []
    return parse(paths.inbox.read_text(encoding="utf-8"))


def write(paths, ops, day):
    return write_markdown(paths.inbox, render(ops, day), day)


def episode_from_op(op):
    row = {key: value for key, value in op.items() if key != "op"}
    base = episode_model.blank()
    base.update(row)
    base.setdefault("origin", "inbox")
    return base


def apply_episode(op, rows, renames):
    row = episode_from_op(op)
    day = row.get("date")
    taken = {item["id"] for item in rows}
    wanted = row.get("id")
    if wanted in taken:
        existing = next(item for item in rows if item["id"] == wanted)
        core = episode_model.FIELDS
        if all(episode_model.ordered(existing)[key] == episode_model.ordered(row)[key] for key in core):
            return "duplicate"
        fresh = episode_model.next_id(episode_model.parse_date(day), taken)
        renames[wanted] = fresh
        row["id"] = fresh
    elif not wanted:
        row["id"] = episode_model.next_id(episode_model.parse_date(day), taken)
    episode_model.require_valid(row)
    rows.append(row)
    return "added"


def apply_fact(op, rows, renames):
    identity = renames.get(op.get("id"), op.get("id"))
    row = episode_model.find(rows, identity)
    updated, warnings = episode_model.apply_fact(
        row, op.get("outcome"), op.get("outcome_fact"), observed=op.get("observed") is True,
        recovery_minutes=op.get("recovery_minutes"), suds_peak=op.get("suds_peak"),
        action=op.get("action"), miss=op.get("miss"), miss_conditions=op.get("miss_conditions"))
    rows[rows.index(row)] = updated
    return "updated" + ("(" + ",".join(warnings) + ")" if warnings else "")
