"""Check that the skill package is self-consistent: links resolve and templates parse."""

from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from anchor_core import actions, inbox, ladder, views  # noqa: E402
from anchor_core.episodes import EXTENSIONS, FIELDS  # noqa: E402
from anchor_core.store import split_frontmatter  # noqa: E402

LINK = re.compile(r"\]\(([^)#]+)(?:#[^)]*)?\)")


def main():
    errors = []
    lines, _ = split_frontmatter((ROOT / "SKILL.md").read_text(encoding="utf-8"))
    for key in ("name", "description"):
        if not any(line.startswith(key + ":") for line in lines):
            errors.append(f"SKILL.md: missing {key}")
    for document in [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md"))]:
        for target in LINK.findall(document.read_text(encoding="utf-8")):
            if not target.startswith("http") and not (document.parent / target).exists():
                errors.append(f"{document.relative_to(ROOT)}: broken link {target}")
    templates = ROOT / "templates"
    parsers = {"views.md": views.parse, "ladder.md": ladder.parse, "actions.md": actions.parse,
               "inbox.md": inbox.parse}
    for name, parse in parsers.items():
        try:
            parse((templates / name).read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001 - report any template that the runtime cannot read
            errors.append(f"templates/{name}: {error}")
    for path in templates.glob("*.md"):
        meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        for key in ("name", "description", "aliases", "updated"):
            if not any(line.startswith(key + ":") for line in meta):
                errors.append(f"templates/{path.name}: missing {key}")
    schema = json.loads((ROOT / "schema/episode.schema.json").read_text(encoding="utf-8"))
    if set(schema["properties"]) != set(FIELDS) | set(EXTENSIONS) or set(schema["required"]) != set(FIELDS):
        errors.append("schema/episode.schema.json: fields differ from anchor_core.episodes")
    for error in errors:
        print(error, file=sys.stderr)
    print(f"skill check: {len(errors)} error(s)")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
