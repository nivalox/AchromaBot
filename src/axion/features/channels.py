"""Which channels and DMs the bot watches."""
import re

import requests

from axion.config import save_config
from axion.state import CHANNELS, CONFIG, LAST_ID, STATE, prefix, target_user
from axion.ui import print_warning, r_err, r_info, r_ok, r_warn

from .snipe import seen, sniped


def add_channel(name):
    name = name.lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", name):
        return r_err("Channel names are letters, numbers, - and _")
    if name in CHANNELS:
        return r_warn(f"Already watching {name}")
    from axion.poller import poll_channel  # lazy: the poller imports the command layer
    try:
        poll_channel(name)  # also proves the channel can be read, and sets its baseline
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        return r_err(f"Could not open {name} ({code})")
    except requests.RequestException as e:
        return r_err(f"Could not open {name}: {e}")
    CHANNELS.append(name)
    save_config()
    return r_ok(f"Now watching {name}")


def remove_channel(name):
    name = name.lower()
    if name not in CHANNELS:
        return r_warn(f"Not watching {name}")
    if len(CHANNELS) == 1:
        return r_err("Can't remove the last channel")
    CHANNELS.remove(name)
    for store in (LAST_ID, seen, sniped):
        store.pop(name, None)
    if STATE["channel"] == name:
        STATE["channel"] = CHANNELS[0]
    save_config()
    return r_ok(f"Stopped watching {name}")


def handle_channel(args):
    if not args or args[0].lower() in ("list", "show"):
        return r_info("Watching: " + ", ".join(CHANNELS), emoji="📡")
    sub = args[0].lower()
    if sub == "add" and len(args) > 1:
        return add_channel(args[1])
    if sub in ("remove", "rm") and len(args) > 1:
        return remove_channel(args[1])
    p = prefix()
    return r_warn(f"Usage: {p}channel, {p}channel add <name>, {p}channel remove <name>")


def resolve_dm(target):
    """Turns a user id, a known username, or a full dm-a-b name into a DM channel name.
    Returns (channel, error)."""
    t = target.lower().lstrip("@")
    if re.fullmatch(r"dm-\d+-\d+", t):
        return t, None
    other = int(t) if t.isdigit() else STATE["users"].get(t)
    if other is None:
        return None, f"Don't know {t} yet. Use their numeric id, or wait until they post in a watched channel."
    mine = CONFIG["accounts"].get(target_user(), {}).get("user_id") or STATE["users"].get(target_user())
    if mine is None:
        return None, "Your own user id is not known yet. Post in a watched channel first, or use the full dm-... name."
    if mine == other:
        return None, "That is your own account"
    a, b = sorted((mine, other))  # assumes the lower id comes first, like dm-6898-15939
    return f"dm-{a}-{b}", None


def handle_dm(args):
    if not args:
        return r_warn(f"Usage: {prefix()}dm <user id, username or dm-a-b name>")
    channel, err = resolve_dm(args[0])
    return r_err(err) if err else add_channel(channel)
