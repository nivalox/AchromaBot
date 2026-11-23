"""?info: everything the site knows about a user, from GET /api/chat/users/<id>."""
import time
from datetime import datetime, timezone

import requests

from axion.constants import USERS_URL
from axion.net.http import session
from axion.state import STATE, prefix, target_user
from axion.ui import r_err, r_info, r_warn
from axion.utils.fmt import fmt_duration
from axion.utils.users import resolve_target, user_id_for

MAX_BIO = 300


def fetch_user(uid):
    """Returns (data, error text). data is the site's JSON: {"user": ..., "friend": ..., "moderation": ...}."""
    try:
        r = session.get(f"{USERS_URL}/{uid}", timeout=15)
    except requests.RequestException as e:
        return None, f"Couldn't reach the site: {e}"
    if r.status_code == 404:
        return None, f"No user with id {uid} (404)"
    if r.status_code == 401:
        return None, "The site rejected your session (401)"
    if r.status_code >= 400:
        return None, f"Couldn't look that user up ({r.status_code}): {r.text[:120]}"
    try:
        return r.json(), None
    except ValueError:
        return None, "The site sent something that isn't JSON"


def when(ms):
    """A millisecond timestamp as 'YYYY-MM-DD HH:MM UTC'."""
    try:
        return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(ms)


def ago(ms):
    try:
        return fmt_duration(max(0, time.time() - ms / 1000)) + " ago"
    except (TypeError, ValueError):
        return str(ms)


def clip(text, limit):
    text = " / ".join(part.strip() for part in str(text).split("\n") if part.strip())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe_timeout(t):
    if isinstance(t, dict):
        until = next((t[k] for k in ("until", "expires_at", "ends_at", "expires") if isinstance(t.get(k), (int, float))), None)
        reason = t.get("reason")
        bits = [f"until {when(until)}" if until else "active"]
        if reason:
            bits.append(f"reason: {reason}")
        return ", ".join(bits)
    return clip(t, 120)


def info_rows(data):
    """[(emoji, label, value)] for everything worth showing. Missing fields are skipped."""
    u = data.get("user") or {}
    mod = data.get("moderation") or {}
    rows = []

    name = u.get("display_name") or u.get("username") or "?"
    rows.append(("🪪", "Name", f"{name} (@{u.get('username')})"))
    rows.append(("🆔", "ID", f"{u.get('id')}" + (" · 🤖 bot" if u.get("bot") else "")))

    la = u.get("last_active") or {}
    if la.get("online"):
        rows.append(("🟢", "Active", "online now"))
    else:
        seen = next((la[k] for k in ("at", "time", "timestamp", "last_seen") if isinstance(la.get(k), (int, float))), None)
        rows.append(("⚫", "Active", f"offline, last seen {ago(seen)}" if seen else "offline"))

    status = " ".join(x for x in (u.get("status"), clip(u["status_text"], 120) if u.get("status_text") else None) if x)
    if status:
        rows.append(("💭", "Status", status))
    if u.get("title"):
        rows.append(("🏷️", "Title", u["title"]))
    if u.get("bio"):
        rows.append(("📝", "Bio", clip(u["bio"], MAX_BIO)))
    if u.get("streak") is not None:
        rows.append(("🔥", "Streak", f"{u['streak']} day{'s' if u['streak'] != 1 else ''}"))
    if u.get("message_count") is not None:
        rows.append(("💬", "Messages", str(u["message_count"])))
    if u.get("created_at"):
        rows.append(("📅", "Joined", f"{when(u['created_at'])} ({ago(u['created_at'])})"))

    roles = [r for r in [(u.get("role") or {}).get("name")] + [(x or {}).get("name") if isinstance(x, dict) else x for x in u.get("roles") or []] if r]
    if roles:
        rows.append(("🎭", "Roles", ", ".join(dict.fromkeys(roles))))
    if data.get("friend"):
        rows.append(("🤝", "Friend", str(data["friend"])))

    conns = [
        f"{c.get('service')}: {c.get('handle')}" + (f" ({c['url']})" if c.get("url") else "")
        for c in u.get("connections") or []
    ]
    if conns:
        rows.append(("🔗", "Connections", "; ".join(conns)))
    games = [g.get("name") for g in u.get("favorite_games") or [] if g.get("name")]
    if games:
        rows.append(("🎮", "Favorite games", ", ".join(games)))

    look = []
    if (u.get("name_style") or {}).get("color"):
        look.append(f"name color {u['name_style']['color']}")
    if u.get("avatar_decoration"):
        look.append(f"decoration {u['avatar_decoration']}")
    if u.get("profile_effect"):
        look.append(f"effect {u['profile_effect']}")
    if u.get("avatar_image"):
        look.append("custom avatar")
    if u.get("banner_image"):
        look.append("banner")
    if look:
        rows.append(("🎨", "Look", ", ".join(look)))

    warnings = mod.get("warnings") or []
    if warnings:
        rows.append(("⚠️", "Warnings", f"{len(warnings)}"))
        for w in warnings:
            state = "acknowledged" if w.get("acknowledged_at") else "not acknowledged"
            rows.append(("▫️", f"#{w.get('id')}", f"\"{clip(w.get('reason', ''), 120)}\" by @{w.get('by_username')}, {when(w.get('created_at'))}, {state}"))
    else:
        rows.append(("✅", "Warnings", "none"))
    if mod.get("timeout"):
        rows.append(("⏳", "Timeout", describe_timeout(mod["timeout"])))
    return rows


def info_text(rows):
    first, rest = rows[0], rows[1:]
    body = "\n".join(f"{e} {label}: {value}" for e, label, value in rest)
    return r_info(f"User info\n{first[0]} {first[2]}\n{body}", emoji="🔎")


def lookup(args, mentions, requester):
    """Returns (data, error Reply). No argument means the person who asked."""
    p = prefix()
    if args:
        uid, label, err = resolve_target(args[0], mentions[0] if mentions else None)
        if err:
            return None, r_warn(err)
    else:
        uid = user_id_for(requester or target_user())
        if uid is None:
            return None, r_warn(f"Usage: {p}info <@user or id>, like {p}info @gilbert")
    data, err = fetch_user(uid)
    if err:
        return None, r_err(err)
    return data, None
