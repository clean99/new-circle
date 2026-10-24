"""A throwaway Life OS checkout with the anchor-training data files."""

from datetime import date
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from anchor_core.store import Paths  # noqa: E402

DAY = date(2026, 10, 26)

VIEWS = """---
name: 见地库
description: test
aliases: [views]
updated: 2026-10-25
---

# 见地库

- **V01** 没有外部理由，也可以拒绝不喜欢的事。
  - 出处：[inferred] 借用：《When I Say No, I Feel Guilty》Manuel Smith
  - 复习：阶段 0（间隔 1 天）｜下次 2026-10-26｜上次 —
- **V02** 我只依靠事实去做决定。
  - 出处：[stated] 「我只依靠事实去做决定」— raw/conversations/2026-10/claude-a-1.jsonl#m1（2026-10-24）
  - 复习：阶段 1（间隔 3 天）｜下次 2026-10-28｜上次 2026-10-25
"""

LADDER = """---
name: 主体性阶梯
description: test
aliases: [ladder]
updated: 2026-10-25
---

# 主体性阶梯

- [ ] **L01**｜关系外｜点餐时说一次「不要 X」，不解释原因。
- [ ] **L02**｜关系外｜同事请我帮忙而我不想时，说「这次我不行」。
"""

ACTIONS = """---
name: 现在去做清单
description: test
aliases: [actions]
updated: 2026-10-25
---

## 事业
- 打开工作室剪 10 分钟
## 健康
- 出门快走 15 分钟
## 社交
- 给一个朋友发消息约饭
"""

SCENE = """---
name: 演练剧本 sc-2026-08-28-01
description: test
aliases: [sc-2026-08-28-01]
updated: 2026-10-25
scene: sc-2026-08-28-01
episode: ep-2026-08-28-01
suds_expected: 60
script: 好，你先休息。
cue: 我想自己待一会。
conditions: [电话, 半夜]
---

# sc-2026-08-28-01

## 剧本

我躺在床上，手机亮了，她说「我想自己待一会」。我胸口一紧，脑子里冒出：她是不是不要我了。

## 对方那句话

「我想自己待一会。」
"""


def episode(identity="ep-2026-08-28-01", **changes):
    row = {"id": identity, "date": identity[3:13], "source_ref": "raw/conversations/2026-10/claude-a-1.jsonl#m2",
           "trigger": "她说想自己待一会", "my_thought": "她是不是不要我了", "body": "胸口一紧",
           "urge": 7, "certainty": 80, "action": "held", "script_used": "好，你先休息。",
           "outcome": "not_happened", "outcome_fact": "第二天早上她主动发了早安",
           "recovery_minutes": 40, "suds_peak": 80, "miss": False, "miss_conditions": ["半夜"],
           "notes": ""}
    row.update(changes)
    return row


def raw_conversation(repo, conversation_id, messages, name="claude-a-1.jsonl"):
    path = repo / "raw/conversations/2026-10" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "meta", "schema_version": 1, "source": "claude", "conversation_id": conversation_id,
              "conversation_key": "k", "captured_at": "2026-10-25T00:00:00+08:00", "coverage": "full_export",
              "capture_scope": "supplied_export_messages", "representation": "source_text", "redaction": "none"}]
    for sequence, (identity, role, text) in enumerate(messages, 1):
        lines.append({"type": "message", "message_key": "key-" + identity, "role": role, "redacted": False,
                      "redaction_types": [], "id": identity, "timestamp": "2026-10-24T10:00:00+00:00",
                      "sequence": sequence, "part_index": 0, "part_count": 1, "text": text})
    path.write_text("".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8")
    return path


class LifeOS:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / "AGENTS.md").write_text("# Life OS\n", encoding="utf-8")
        (self.repo / "raw/conversations").mkdir(parents=True)
        area = self.repo / "areas/relationship"
        (area / "scenes").mkdir(parents=True)
        (area / "views.md").write_text(VIEWS, encoding="utf-8")
        (area / "ladder.md").write_text(LADDER, encoding="utf-8")
        (area / "actions.md").write_text(ACTIONS, encoding="utf-8")
        (area / "scenes/sc-2026-08-28-01.md").write_text(SCENE, encoding="utf-8")
        (area / "episodes.jsonl").write_text(json.dumps(episode(), ensure_ascii=False) + "\n", encoding="utf-8")
        self.paths = Paths(self.repo)

    def close(self):
        self.tmp.cleanup()

    def episodes(self):
        return [json.loads(line) for line in self.paths.episodes.read_text(encoding="utf-8").splitlines()]
