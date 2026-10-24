"""「现在去做：X」清单: concrete things from my own career, health and social life.

actions.md lists items under three headings:

## 事业
- 打开个人 IP 工作室，剪下一段 10 分钟
## 健康
## 社交
"""

import hashlib
import re

from .store import AnchorError

HEADINGS = ("事业", "健康", "社交")
HEADING = re.compile(r"^## (.+)$")
ITEM = re.compile(r"^- (?:\[[ x]\] )?(.+)$")


def parse(text):
    groups, current = {}, None
    for line in text.split("\n"):
        heading = HEADING.match(line)
        if heading:
            name = heading.group(1).strip()
            current = name if name in HEADINGS else None
            if current:
                groups.setdefault(current, [])
            continue
        item = ITEM.match(line)
        if current and item:
            groups[current].append(item.group(1).strip())
    if not any(groups.values()):
        raise AnchorError("actions_list_empty")
    return groups


def pick(groups, key):
    """Deterministic rotation across categories and items, keyed by the episode id."""
    flat = [(name, item) for name in HEADINGS for item in groups.get(name, [])]
    digest = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
    return flat[digest % len(flat)]
