"""/now: the trigger-moment reply. Five lines at most, no reassurance, no guessing about the other person."""

import re

SCRIPTS = (
    (re.compile(r"休息|冷静|自己待|一个人待|静一静|空间|先不聊|不想说话|睡了|累了"), "好，你先休息。"),
    (re.compile(r"冷淡|敷衍|不回|没回|已读|嗯|哦|聊不下去|沉默|冷下来"), "那先聊到这里。"),
    (re.compile(r"分手|结束|分开|不想继续|算了吧|离开"), "好，那就这样。"),
)
DEFAULT_SCRIPT = "好，你先休息。"
ANCHOR = (
    "承认：「我注意到我有一个想法：{thought}」——这是一个预测，不是事实。",
    "回到身体：双脚踩地，慢慢呼气比吸气长，找到最紧的地方，让它在。",
    "投入当下：看清眼前三样东西，然后去做下一件事。",
)


def choose_script(trigger, thought=""):
    text = (trigger or "") + " " + (thought or "")
    for pattern, script in SCRIPTS:
        if pattern.search(text):
            return script
    return DEFAULT_SCRIPT


def shorten(text, limit=40):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def reply(episode, action_item, needs_reply=True):
    """The ≤5-line message for the person in the trigger moment."""
    lines = [
        f"记下了 {episode['id']}：确定 {fmt(episode.get('certainty'), '%')}，冲动 {fmt(episode.get('urge'), '/10')}。",
        ANCHOR[0].format(thought=shorten(episode.get("my_thought"))) + " " + ANCHOR[1],
        ANCHOR[2],
    ]
    if needs_reply:
        lines.append(f"要回对方就只说：「{episode.get('script_used') or DEFAULT_SCRIPT}」说完停。")
    lines.append(f"现在去做：{action_item}。24–72 小时后我问你事实。")
    return lines[:5]


def fmt(value, unit):
    return "?" if value is None else f"{value}{unit}"
