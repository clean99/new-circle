"""演练剧本: first person, present tense, my own words, with body sensations, at most 150 characters."""

from dataclasses import dataclass
import re

from .store import AnchorError, frontmatter, frontmatter_value, split_frontmatter

MAX_CHARS = 150
SCENE_ID = re.compile(r"sc-\d{4}-\d{2}-\d{2}-\d{2}\Z")
PAST_MARKERS = re.compile(r"当时|那时|那天|后来|之前|过去了|曾经")
BODY_MARKERS = re.compile(r"心|胸|胃|手|喉|呼吸|喘|发抖|发麻|发紧|发热|发冷|头|肩|肚子|脸|眼|身体|僵|紧")
QUOTE = re.compile(r"「([^」]+)」")


@dataclass(frozen=True)
class Scene:
    id: str
    episode: str
    suds_expected: int
    script: str
    conditions: tuple
    cue: str
    text: str
    path: object = None


def counted_length(text):
    """Characters excluding whitespace, the unit used for the 150-character limit."""
    return len(re.sub(r"\s", "", text))


def parse_list(value):
    value = (value or "").strip()
    if not value.startswith("[") or not value.endswith("]"):
        return ()
    return tuple(item.strip() for item in value[1:-1].split(",") if item.strip())


def parse(text, path=None):
    lines, body = split_frontmatter(text)
    identity = frontmatter_value(lines, "scene")
    if not identity or not SCENE_ID.fullmatch(identity):
        raise AnchorError("invalid_scene_id", str(path))
    try:
        suds = int(frontmatter_value(lines, "suds_expected") or "")
    except ValueError:
        raise AnchorError("invalid_scene_suds", identity) from None
    script = (frontmatter_value(lines, "script") or "").strip()
    cue = (frontmatter_value(lines, "cue") or "").strip()
    section = body.split("## 剧本", 1)
    if len(section) != 2:
        raise AnchorError("scene_body_missing", identity)
    scene_text = section[1].split("\n## ", 1)[0].strip()
    return Scene(identity, frontmatter_value(lines, "episode") or "", suds, script,
                 parse_list(frontmatter_value(lines, "conditions")), cue, scene_text, path)


def validate(scene, episode_ids=None):
    errors, warnings = [], []
    if not scene.episode.startswith("ep-"):
        errors.append("episode_required")
    elif episode_ids is not None and scene.episode not in episode_ids:
        errors.append("episode_not_found")
    if not 0 <= scene.suds_expected <= 100:
        errors.append("suds_expected_out_of_range")
    if not scene.script:
        errors.append("script_required")
    if not scene.cue:
        errors.append("cue_required")
    length = counted_length(scene.text)
    if not length:
        errors.append("scene_text_required")
    if length > MAX_CHARS:
        errors.append(f"scene_text_too_long:{length}")
    if "我" not in scene.text:
        errors.append("scene_must_be_first_person")
    if PAST_MARKERS.search(scene.text):
        warnings.append("scene_contains_past_tense_marker")
    if not BODY_MARKERS.search(scene.text):
        warnings.append("scene_without_body_sensation")
    return errors, warnings


def render(scene, day, source_quote=""):
    meta = frontmatter(
        f"演练剧本 {scene.id}", f"由 {scene.episode} 生成的第一人称演练剧本，练「{scene.script}」。",
        [scene.id], day,
        extra=[f"scene: {scene.id}", f"episode: {scene.episode}",
               f"suds_expected: {scene.suds_expected}", f"script: {scene.script}",
               f"cue: {scene.cue}", "conditions: [" + ", ".join(scene.conditions) + "]"])
    lines = [meta, f"# {scene.id}", "",
             f"来源 {scene.episode}｜预期 SUDS {scene.suds_expected}｜练这一句：「{scene.script}」", "",
             "## 剧本", "", scene.text, "",
             "## 对方那句话", "", f"「{scene.cue}」", ""]
    if source_quote:
        lines += ["## 原话出处", "", source_quote, ""]
    return "\n".join(lines)


def load_all(paths):
    if not paths.scenes.exists():
        return []
    scenes = [parse(path.read_text(encoding="utf-8"), path) for path in sorted(paths.scenes.glob("*.md"))]
    ids = [scene.id for scene in scenes]
    if len(ids) != len(set(ids)):
        raise AnchorError("duplicate_scene_id")
    return scenes


def scene_id_for(episode_id):
    return "sc-" + episode_id[3:]
