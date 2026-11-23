"""Reacts to new messages with an emoji."""
import requests

from axion.config import save_config
from axion.constants import BASE
from axion.net.http import session
from axion.state import AUTOREACT, CONFIG, prefix
from axion.ui import print_warning, r_info, r_ok, r_warn
from axion.utils.users import resolve_user, split_user_args


def auto_react(m):
    """Reacts to a new message with the configured emoji. Never reacts to your own messages."""
    if not AUTOREACT["enabled"]:
        return
    user = (m.get("username") or "").lower()
    if user in CONFIG["accounts"]:
        return
    users = AUTOREACT["users"]
    if users and user not in users:
        return
    try:
        r = session.post(
            f"{BASE}/{m['id']}/reactions",
            json={"emoji": AUTOREACT["emoji"]},
            timeout=10,
        )
        if r.status_code >= 400:
            print_warning(f"Auto react failed on {m['id']} ({r.status_code}): {r.text[:100]}")
    except requests.RequestException as e:
        print_warning(f"Auto react error: {e}")


def autoreact_status():
    on = AUTOREACT["enabled"]
    users = ", ".join("@" + u for u in AUTOREACT["users"]) or "everyone"
    return r_info(
        f"Auto react: {'on' if on else 'off'}\n😀 Emoji: {AUTOREACT['emoji']}\n👥 Reacting to: {users}",
        emoji="✅" if on else "❌",
    )


def handle_autoreact(args, mentions=()):
    p = prefix()
    if not args or args[0].lower() == "show":
        return autoreact_status()
    sub = args[0].lower()
    if sub in ("on", "off"):
        AUTOREACT["enabled"] = sub == "on"
        save_config()
        return autoreact_status()
    if sub == "emoji" and len(args) > 1:
        AUTOREACT["emoji"] = args[1]
        save_config()
        return r_ok(f"Auto react emoji set to {args[1]}", emoji=args[1])
    if sub == "users" and len(args) > 1:
        if [a.lower() for a in args[1:]] == ["all"]:
            AUTOREACT["users"] = []
        else:
            people, _rest = split_user_args(args[1:], mentions)
            # every word after "users" is a person here, not only the leading mentions
            names = [n for n, _e in people] + [resolve_user(a)[0] for a in _rest]
            AUTOREACT["users"] = [n for n in dict.fromkeys(names) if n]
        save_config()
        return autoreact_status()
    return r_warn(f"Usage: {p}autoreact on/off, {p}autoreact emoji <emoji>, {p}autoreact users <names, @mentions or all>")
