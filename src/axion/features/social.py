"""?friend and ?warn: the site's per-user actions, which are keyed by numeric user id."""
import requests

from axion.constants import USERS_URL
from axion.net.http import session
from axion.state import CONFIG, prefix
from axion.ui import r_err, r_ok, r_warn
from axion.utils.users import looks_like_mention, resolve_target

DEFAULT_REASON = "No reason given"


def _targets(args, mentions, usage):
    """Reads the people at the start of args. Returns ([(id, label)], remaining args, error Reply or None).
    Names need an id the bot has seen, numeric ids always work."""
    remaining = list(args)
    tokens = []
    while remaining and looks_like_mention(remaining[0]):
        tokens += [t for t in remaining.pop(0).split(",") if t]
    if not tokens and remaining:
        tokens.append(remaining.pop(0))
    if not tokens:
        return [], remaining, r_warn(usage)
    found = []
    for i, token in enumerate(tokens):
        fallback = mentions[i] if i < len(mentions) else None
        uid, label, err = resolve_target(token, fallback)
        if err:
            return [], remaining, r_err(err)
        if label.lstrip("@").lower() in CONFIG["accounts"]:
            return [], remaining, r_warn(f"{label} is one of your own accounts")
        found.append((uid, label))
    return found, remaining, None


def _explain(r, what):
    if r.status_code == 401:
        return f"The site rejected your session (401) while trying to {what}"
    if r.status_code == 403:
        return f"The site says you aren't allowed to {what} (403)"
    if r.status_code == 404:
        return "The site doesn't know that user (404)"
    return f"Couldn't {what} ({r.status_code}): {r.text[:120]}"


ADD_WORDS = ("add", "a", "request")
REMOVE_WORDS = ("remove", "r", "rm", "unfriend", "delete")


def handle_friend(args, mentions=()):
    """?friend <user> and ?friend add <user> send a request, ?friend remove <user> unfriends.
    A lone action word is usage, and a user really named "add" is written @add."""
    p = prefix()
    usage = (
        f"Usage: {p}friend add <@user or id>, {p}friend remove <@user or id> "
        f"(short: a / r). {p}friend <@user> alone sends a request"
    )
    action, rest = "add", list(args)
    if len(rest) == 1 and rest[0].lower() in ADD_WORDS + REMOVE_WORDS:
        return r_warn(usage)  # just the action word, nobody named (a user called "add" is written @add)
    if len(rest) > 1 and rest[0].lower() in ADD_WORDS + REMOVE_WORDS:
        action = "remove" if rest[0].lower() in REMOVE_WORDS else "add"
        rest = rest[1:]
    targets, _rest, err = _targets(rest, mentions, usage)
    if err:
        return err
    lines, failed = [], False
    for uid, label in targets:
        try:
            if action == "remove":
                r = session.delete(f"{USERS_URL}/{uid}/friend", timeout=15)
            else:
                r = session.post(f"{USERS_URL}/{uid}/friend-request", timeout=15)
        except requests.RequestException as e:
            lines.append(f"{label}: request failed ({e})")
            failed = True
            continue
        if r.status_code >= 400:
            what = "remove that friend" if action == "remove" else "send a friend request"
            lines.append(f"{label}: {_explain(r, what)}")
            failed = True
        else:
            lines.append(f"Removed {label} from your friends" if action == "remove" else f"Friend request sent to {label}")
    text = "\n".join(lines)
    if failed:
        return r_err(text) if len(lines) == 1 else r_warn(text)
    return r_ok(text, emoji="💔" if action == "remove" else "🤝")


def handle_warn(args, mentions=()):
    p = prefix()
    usage = f"Usage: {p}warn <@user or id> [reason], like {p}warn @gilbert spamming"
    targets, rest, err = _targets(args, mentions, usage)
    if err:
        return err
    if len(targets) != 1:
        return r_warn("Warn one person at a time")
    uid, label = targets[0]
    reason = " ".join(rest).strip() or DEFAULT_REASON
    try:
        r = session.post(f"{USERS_URL}/{uid}/warn", json={"reason": reason}, timeout=15)
    except requests.RequestException as e:
        return r_err(f"Warn failed: {e}")
    if r.status_code >= 400:
        return r_err(_explain(r, "warn them"))
    return r_ok(f"Warned {label}\nReason: {reason}", emoji="⚠️")
