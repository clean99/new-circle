"""Life OS checkout discovery, data file locations and small file helpers."""

from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Singapore")
AREA = "areas/relationship"
LOCATION_FILES = (
    ".claude/skills/life-os/references/location.json",
    ".agents/skills/life-os/references/location.json",
)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


class AnchorError(Exception):
    """A user-facing error with a stable code."""

    def __init__(self, code, detail=""):
        super().__init__(code if not detail else code + ": " + detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Paths:
    repo: Path

    @property
    def area(self):
        return self.repo / AREA

    @property
    def episodes(self):
        return self.area / "episodes.jsonl"

    @property
    def drills_log(self):
        return self.area / "drills.jsonl"

    @property
    def inbox(self):
        return self.area / "inbox.md"

    @property
    def views(self):
        return self.area / "views.md"

    @property
    def ladder(self):
        return self.area / "ladder.md"

    @property
    def actions(self):
        return self.area / "actions.md"

    @property
    def scenes(self):
        return self.area / "scenes"

    @property
    def drills(self):
        return self.area / "drills"

    @property
    def weekly(self):
        return self.area / "weekly"

    def relative(self, path):
        return Path(path).resolve().relative_to(self.repo.resolve()).as_posix()


def looks_like_life_os(path):
    return (path / "AGENTS.md").is_file() and (path / "areas").is_dir() and (path / "raw").is_dir()


def resolve_repo(explicit=None, env=None, home=None):
    """Find the Life OS checkout: --repo, $LIFE_OS_REPO, then the installed life-os skill."""
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    candidates = []
    if explicit:
        candidates.append(("--repo", Path(explicit)))
    elif env.get("LIFE_OS_REPO"):
        candidates.append(("LIFE_OS_REPO", Path(env["LIFE_OS_REPO"])))
    else:
        for relative in LOCATION_FILES:
            location = home / relative
            if location.is_file():
                try:
                    root = json.loads(location.read_text(encoding="utf-8")).get("knowledge_root")
                except (OSError, ValueError, AttributeError):
                    continue
                if isinstance(root, str):
                    candidates.append((str(location), Path(root)))
    for origin, path in candidates:
        path = path.expanduser()
        if looks_like_life_os(path):
            return Paths(path.resolve())
        raise AnchorError("not_a_life_os_checkout", f"{origin} -> {path}")
    raise AnchorError("life_os_repo_not_found", "pass --repo or set LIFE_OS_REPO")


def sync_state(repo):
    """(ahead, behind) against the upstream branch from local refs only, or None when unknown."""
    result = subprocess.run(["git", "-C", str(repo), "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None
    ahead, behind = (int(part) for part in result.stdout.split())
    return ahead, behind


def now():
    return datetime.now(TZ)


def today():
    return now().date()


def parse_date(value, field="date"):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not DATE.fullmatch(value):
        raise AnchorError("invalid_date", f"{field}={value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise AnchorError("invalid_date", f"{field}={value!r}") from None


def parse_timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AnchorError("timestamp_requires_timezone", value)
    return parsed


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".anchor-", delete=False)
    try:
        with handle:
            handle.write(text)
        os.replace(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise AnchorError("invalid_jsonl", f"{path.name}:{number}") from None
        if not isinstance(row, dict):
            raise AnchorError("invalid_jsonl", f"{path.name}:{number}")
        rows.append(row)
    return rows


def dumps(row):
    return json.dumps(row, ensure_ascii=False, separators=(", ", ": "))


def write_jsonl(path, rows):
    atomic_write(path, "".join(dumps(row) + "\n" for row in rows))


def split_frontmatter(text):
    """Return (frontmatter lines, body) for a Markdown file with a leading --- block."""
    if not text.startswith("---\n"):
        return [], text
    end = text.find("\n---\n", 4)
    if end < 0:
        return [], text
    return text[4:end].split("\n"), text[end + 5:]


def frontmatter_value(lines, key):
    prefix = key + ":"
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def set_updated(text, day):
    """Refresh the `updated` field; Life OS treats it as the file modification date."""
    lines, body = split_frontmatter(text)
    if not lines:
        return text
    stamp = "updated: " + day.isoformat()
    lines = [stamp if line.startswith("updated:") else line for line in lines]
    if stamp not in lines:
        lines.append(stamp)
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def write_markdown(path, text, day):
    """Write a knowledge file only when its body changed, refreshing `updated` in that case."""
    path = Path(path)
    if path.exists():
        old = path.read_text(encoding="utf-8")
        if split_frontmatter(old)[1] == split_frontmatter(text)[1]:
            return False
    atomic_write(path, set_updated(text, day))
    return True


def frontmatter(name, description, aliases, day, extra=()):
    alias_text = "[" + ", ".join(aliases) + "]"
    lines = ["---", "name: " + name, "description: " + description, "aliases: " + alias_text,
             "updated: " + day.isoformat()]
    lines.extend(extra)
    lines.append("---")
    return "\n".join(lines) + "\n"
