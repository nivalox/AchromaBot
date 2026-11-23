"""Remembers deleted messages so ?snipe can show them."""
import time
from collections import deque

from axion.state import prefix
from axion.ui import print_dim, r_info, r_warn
from axion.utils.fmt import fmt_duration

seen = {}  # channel -> {id: message}, messages currently inside the fetched window
sniped = {}  # channel -> deque of deleted messages, newest last
MAX_SNIPES = 50


def track_deletions(channel, msgs):
    """A seen message counts as deleted if its id sits inside the current window
    but is missing from it. Ids below the window start just aged out, so they are skipped."""
    if not msgs:
        return
    store = seen.setdefault(channel, {})
    current = {m["id"]: m for m in msgs}
    window_start = min(current)

    for mid, msg in list(store.items()):
        if mid < window_start:
            del store[mid]
        elif mid not in current:
            sniped.setdefault(channel, deque(maxlen=MAX_SNIPES)).append({"msg": msg, "deleted_at": time.time()})
            del store[mid]
            print_dim(f"Caught a deleted message in {channel} from {msg.get('username')}")

    store.update(current)


def parse_index(args):
    """'?snipe 5' -> (5, None). Returns (n, error Reply). No argument means the latest one."""
    if not args:
        return 1, None
    word = args[0].lstrip("#")
    if not word.isdigit() or int(word) < 1:
        p = prefix()
        return None, r_warn(f"Usage: {p}snipe [number], for example {p}snipe 5 for the 5th last deleted message")
    return int(word), None


def snipe_fields(channel, n=1):
    """The n-th newest deleted message of a channel (1 is the newest) as plain fields, or None.
    Also returns how many are stored, so callers can explain a number that is too high."""
    q = sniped.get(channel)
    total = len(q) if q else 0
    if not total or n > total:
        return None, total
    rec = q[-n]
    msg = rec["msg"]
    att = msg.get("attachment")
    return {
        "n": n,
        "total": total,
        "name": msg.get("display_name") or msg.get("username") or "unknown",
        "user": msg.get("username"),
        "ago": fmt_duration(time.time() - rec["deleted_at"]),
        "text": (msg.get("body") or "").strip(),
        "att": att["url"] if isinstance(att, dict) and att.get("url") else "",
    }, total


def empty_text(channel, n, total):
    if not total:
        return "Nothing to snipe"
    return f"Only {total} deleted message{'s' if total != 1 else ''} saved in {channel}, so #{n} doesn't exist"


def get_snipe(channel, n=1):
    f, total = snipe_fields(channel, n)
    if not f:
        return r_info(empty_text(channel, n, total), emoji="🎯")
    text = f"{f['text']}\n{f['att']}".strip() if f["att"] else f["text"]
    return r_info(
        f"Sniped #{f['n']} of {f['total']}, deleted {f['ago']} ago\n"
        f"👤 {f['name']} (@{f['user']})\n💬 {text or '(no text)'}",
        emoji="🎯",
    )


def clear_snipes(channel):
    sniped.get(channel, deque()).clear()
