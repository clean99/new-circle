"""见地库: one-sentence views with their source and a simple 1/3/7/14/30 day review schedule.

Each view in views.md is a list item block:

- **V01** 没有外部理由，也可以拒绝不喜欢的事。
  - 出处：[stated] 「原话」— raw/conversations/...jsonl#message-id（2026-01-15）
  - 复习：阶段 0（间隔 1 天）｜下次 2026-10-26｜上次 —
"""

from dataclasses import dataclass, replace
from datetime import timedelta
import re

from .store import AnchorError, parse_date

INTERVALS = (1, 3, 7, 14, 30)
ITEM = re.compile(r"^- \*\*(V\d{2,3})\*\* (.+)$")
SOURCE = re.compile(r"^  - 出处：(.+)$")
REVIEW = re.compile(r"^  - 复习：阶段 (\d)（间隔 \d+ 天）｜下次 (\d{4}-\d{2}-\d{2})｜上次 (—|\d{4}-\d{2}-\d{2})$")
KIND = re.compile(r"^\[(stated|inferred)\]")


@dataclass(frozen=True)
class View:
    id: str
    text: str
    source: str
    stage: int
    due: object
    last: object
    line: int

    @property
    def kind(self):
        match = KIND.match(self.source)
        return match.group(1) if match else None


def review_line(stage, due, last):
    last_text = last.isoformat() if last else "—"
    return f"  - 复习：阶段 {stage}（间隔 {INTERVALS[stage]} 天）｜下次 {due.isoformat()}｜上次 {last_text}"


def parse(text):
    lines = text.split("\n")
    views = []
    for index, line in enumerate(lines):
        match = ITEM.match(line)
        if not match:
            continue
        source_match = SOURCE.match(lines[index + 1]) if index + 1 < len(lines) else None
        review_match = REVIEW.match(lines[index + 2]) if index + 2 < len(lines) else None
        if not source_match or not review_match:
            raise AnchorError("invalid_view_block", match.group(1))
        stage = int(review_match.group(1))
        if stage >= len(INTERVALS):
            raise AnchorError("invalid_view_stage", match.group(1))
        last = None if review_match.group(3) == "—" else parse_date(review_match.group(3))
        views.append(View(match.group(1), match.group(2).strip(), source_match.group(1).strip(), stage,
                          parse_date(review_match.group(2)), last, index))
    ids = [view.id for view in views]
    if len(ids) != len(set(ids)):
        raise AnchorError("duplicate_view_id")
    return views


def validate(views):
    errors = []
    for view in views:
        if view.kind is None:
            errors.append(f"{view.id}: source_must_start_with_stated_or_inferred")
        if view.kind == "stated" and not re.search(r"「.+」", view.source):
            errors.append(f"{view.id}: stated_view_requires_quote")
        if view.kind == "stated" and "raw/" not in view.source:
            errors.append(f"{view.id}: stated_view_requires_raw_source")
        if view.kind == "inferred" and not re.search(r"《.+》|借用|来源", view.source):
            errors.append(f"{view.id}: inferred_view_requires_borrowed_source")
    return errors


def due(views, day):
    """The view to push today: the most overdue one, else None."""
    pending = [view for view in views if view.due <= day]
    pending.sort(key=lambda view: (view.due, view.id))
    return pending[0] if pending else None


def upcoming(views):
    return sorted(views, key=lambda view: (view.due, view.id))[0] if views else None


def reviewed(view, day, remembered=True):
    """Advance after a review: the gap shown on the stage is applied, then the stage moves up.

    `remembered=False` (the view did not land today) brings it back tomorrow from stage 0.
    """
    if not remembered:
        return replace(view, stage=0, due=day + timedelta(days=1), last=day)
    gap = INTERVALS[view.stage]
    return replace(view, stage=min(view.stage + 1, len(INTERVALS) - 1),
                   due=day + timedelta(days=gap), last=day)


def update(text, view):
    lines = text.split("\n")
    current = {item.id: item for item in parse(text)}
    if view.id not in current:
        raise AnchorError("view_not_found", view.id)
    lines[current[view.id].line + 2] = review_line(view.stage, view.due, view.last)
    return "\n".join(lines)


def find(views, identity):
    for view in views:
        if view.id == identity:
            return view
    raise AnchorError("view_not_found", identity)


def block(identity, text, source, day):
    return "\n".join([f"- **{identity}** {text}", f"  - 出处：{source}", review_line(0, day, None)])
