"""The automatic replies: "you are not authorized" and "isn't a command".

?autoreply on/off      switch them
?autoreply users ...   who they reply to (names, @mentions or all)
?autoreply types ...   which replies show up (unauth, unknown, all or none)
?autoreply text ...    change what a reply says"""
from axion.config import save_config
from axion.constants import AUTOREPLY_ALIASES, AUTOREPLY_KINDS, DEFAULTS
from axion.state import CONFIG, prefix
from axion.ui import r_info, r_ok, r_warn
from axion.utils.fmt import split_list
from axion.utils.users import resolve_user, split_user_args

MAX_TEXT = 200


def cfg():
    return CONFIG["autoreply"]


def audience():
    return ", ".join("@" + u for u in cfg()["users"]) or "everyone"


def shown_types():
    return ", ".join(AUTOREPLY_KINDS[t] for t in cfg()["types"]) or "nothing"


def status_lines(on=None):
    on = cfg()["enabled"] if on is None else on
    who = audience() if on else f"nobody (when on: {audience()})"
    return f"👥 Replying to: {who}\n💬 Shows: {shown_types()}"


def status():
    on = cfg()["enabled"]
    head = "Auto replies are ON" if on else "Auto replies are OFF"
    return r_info(f"{head}\n{status_lines()}", emoji="✅" if on else "❌")


def should_reply(kind, user, is_owner):
    """Whether this kind of reply may go out to this person. The users list only limits other people:
    your own typos are answered whenever the kind is switched on."""
    c = cfg()
    if not c["enabled"] or kind not in c["types"]:
        return False
    if is_owner:
        return True
    return not c["users"] or user in c["users"]


def build_text(kind, user, typed):
    text = cfg()["texts"].get(kind) or DEFAULTS["autoreply"]["texts"][kind]
    text = text.replace("{user}", f"@{user}" if user else "").replace("{cmd}", typed).strip()
    if text.startswith(prefix()) or text.startswith("?"):
        text = "💬 " + text  # a reply that looked like a command would trigger itself
    return text


def reply_for(kind, ctx):
    """Sends the automatic reply for a refused or unknown command when the settings allow it."""
    if ctx.local or not should_reply(kind, ctx.user, ctx.is_owner):
        return
    emoji = "⛔" if kind == "unauth" else "❓"
    ctx.reply(f"{emoji} {build_text(kind, ctx.user, ctx.typed)}")


def parse_kind(word):
    return AUTOREPLY_ALIASES.get(word.lower().replace("-", "").replace("_", ""))


def handle_autoreply(args, rest, mentions=()):
    """args are the words after the command, rest is the same text with its original spacing."""
    p = prefix()
    usage = (
        f"Usage: {p}autoreply on/off, {p}autoreply users <names or all>, "
        f"{p}autoreply types <unauth,unknown|all|none>, {p}autoreply text <unauth|unknown> <message|reset>"
    )
    if not args or args[0].lower() == "show":
        return status()
    sub = args[0].lower()

    if sub in ("on", "off"):
        cfg()["enabled"] = sub == "on"
        save_config()
        on = cfg()["enabled"]
        return r_ok(f"Auto replies {'enabled' if on else 'disabled'}\n{status_lines()}", emoji="✅" if on else "❌")

    if sub == "users" and len(args) > 1:
        if [a.lower() for a in args[1:]] == ["all"]:
            cfg()["users"] = []
        else:
            people, remaining = split_user_args(args[1:], mentions)
            names = [n for n, _e in people] + [resolve_user(a)[0] for a in remaining]
            cfg()["users"] = [n for n in dict.fromkeys(names) if n]
        save_config()
        return r_ok(f"Auto replies now go to: {audience()}", emoji="👥")

    if sub == "types" and len(args) > 1:
        words = [w.lower() for w in split_list(args[1:])]
        if words == ["all"]:
            kinds = list(AUTOREPLY_KINDS)
        elif words == ["none"]:
            kinds = []
        else:
            kinds = [parse_kind(w) for w in words]
            if None in kinds:
                bad = [w for w, k in zip(words, kinds) if k is None]
                return r_warn(f"Unknown reply type: {' '.join(bad)}. Types: {', '.join(AUTOREPLY_KINDS)}")
        cfg()["types"] = [k for k in AUTOREPLY_KINDS if k in kinds]
        save_config()
        return r_ok(f"Auto replies will show: {shown_types()}", emoji="💬")

    if sub == "text" and len(args) > 1:
        kind = parse_kind(args[1])
        if not kind:
            return r_warn(f"Pick a reply type: {', '.join(AUTOREPLY_KINDS)}")
        # the message keeps its original spacing and casing
        words = rest.split(None, 2)
        message = words[2].strip() if len(words) > 2 else ""
        if not message:
            return r_warn(f"Usage: {p}autoreply text {kind} <message>. {{user}} is the person, {{cmd}} the command. Or: reset")
        if message.lower() == "reset":
            cfg()["texts"][kind] = DEFAULTS["autoreply"]["texts"][kind]
            save_config()
            return r_ok(f"Reset the {AUTOREPLY_KINDS[kind]} reply", emoji="💬")
        if len(message) > MAX_TEXT:
            return r_warn(f"Keep it under {MAX_TEXT} characters")
        cfg()["texts"][kind] = message
        save_config()
        return r_ok(f"{AUTOREPLY_KINDS[kind].capitalize()} reply is now: {build_text(kind, 'name', p + 'cmd')}", emoji="💬")

    return r_warn(usage)
