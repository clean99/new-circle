"""主体性阶梯: observable tasks from low risk (outside the relationship) to high risk.

Each rung in ladder.md:

- [ ] **L01**｜关系外｜点餐时说一次「不要 X」，不解释原因。
  - 2026-10-27 完成｜SUDS 20｜备注
"""

from dataclasses import dataclass
import re

from .store import AnchorError, parse_date

RUNG = re.compile(r"^- \[( |x)\] \*\*(L\d{2})\*\*｜([^｜]+)｜(.+)$")
DONE = re.compile(r"^  - (\d{4}-\d{2}-\d{2}) 完成｜SUDS (\d{1,3})(?:｜(.*))?$")
CLEAR_AFTER = 2
CLEAR_SUDS = 40


@dataclass(frozen=True)
class Rung:
    id: str
    zone: str
    task: str
    checked: bool
    completions: tuple
    line: int

    @property
    def cleared(self):
        return self.checked or is_cleared(self.completions)


def is_cleared(completions):
    """Two completions with the latest at SUDS ≤ 40 clears a rung; the person can also tick it."""
    return len(completions) >= CLEAR_AFTER and completions[-1][1] <= CLEAR_SUDS


def parse(text):
    lines = text.split("\n")
    rungs = []
    index = 0
    while index < len(lines):
        match = RUNG.match(lines[index])
        if not match:
            index += 1
            continue
        start = index
        completions = []
        index += 1
        while index < len(lines) and lines[index].startswith("  - "):
            done = DONE.match(lines[index])
            if not done:
                raise AnchorError("invalid_ladder_record", match.group(2))
            suds = int(done.group(2))
            if suds > 100:
                raise AnchorError("invalid_ladder_suds", match.group(2))
            completions.append((parse_date(done.group(1)), suds, (done.group(3) or "").strip()))
            index += 1
        rungs.append(Rung(match.group(2), match.group(3).strip(), match.group(4).strip(),
                          match.group(1) == "x", tuple(completions), start))
    ids = [rung.id for rung in rungs]
    if len(ids) != len(set(ids)):
        raise AnchorError("duplicate_rung_id")
    return rungs


def current(rungs):
    for rung in rungs:
        if not rung.cleared:
            return rung
    return None


def find(rungs, identity):
    for rung in rungs:
        if rung.id == identity:
            return rung
    raise AnchorError("rung_not_found", identity)


def complete(text, identity, day, suds, note=""):
    """Append a completion record and tick the rung once it is cleared."""
    if type(suds) is not int or not 0 <= suds <= 100:
        raise AnchorError("invalid_ladder_suds", str(suds))
    if "｜" in note or "\n" in note:
        raise AnchorError("invalid_ladder_note")
    rung = find(parse(text), identity)
    lines = text.split("\n")
    record = f"  - {day.isoformat()} 完成｜SUDS {suds}" + (f"｜{note.strip()}" if note.strip() else "")
    insert_at = rung.line + 1 + len(rung.completions)
    lines.insert(insert_at, record)
    completions = rung.completions + ((day, suds, note),)
    if is_cleared(completions):
        lines[rung.line] = lines[rung.line].replace("- [ ]", "- [x]", 1)
    return "\n".join(lines)


def completions_between(rungs, start, end):
    return [(rung, record) for rung in rungs for record in rung.completions
            if start <= record[0] <= end]
