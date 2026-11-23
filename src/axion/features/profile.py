"""?profile: change your display name, username and bio on the site."""
import requests

from axion.config import save_config
from axion.constants import PROFILE_URL
from axion.net.http import session
from axion.state import CONFIG, PROFILE, prefix, target_user
from axion.ui import r_err, r_info, r_ok, r_warn

PROFILE_FIELDS = {"name": "display_name", "user": "username", "bio": "bio"}


def profile_usage():
    p = prefix()
    return f"Usage: {p}profile name/user/bio <text> or {p}profile show"


def profile_text():
    return (
        f"Display name: {PROFILE['display_name']}\n"
        f"Username: {PROFILE['username']}\n"
        f"Bio: {PROFILE['bio']}"
    )


def handle_profile(rest):
    """rest is what came after the command, so the text you set keeps its casing."""
    parts = rest.split(None, 1)  # ["name", "some text"]
    if not parts:
        return r_warn(profile_usage())

    sub = parts[0].lower()
    if sub == "show":
        return r_info(profile_text(), emoji="🪪")

    field = PROFILE_FIELDS.get(sub)
    if not field or len(parts) < 2 or not parts[1].strip():
        return r_warn(profile_usage())

    value = parts[1].strip()
    new = {k: v for k, v in PROFILE.items() if v}  # blank means unknown, leave it out
    new[field] = value
    try:
        r = session.patch(PROFILE_URL, json=new, timeout=15)
    except requests.RequestException as e:
        return r_err(f"Profile update failed: {e}")
    if r.status_code >= 400:
        return r_err(f"Profile update failed ({r.status_code}): {r.text[:150]}")

    PROFILE.update(new)
    if field == "username":
        # Keep recognizing you after the rename, and remember it across restarts
        CONFIG["accounts"].pop(target_user(), None)
        CONFIG["target_user"] = value.lower()
    save_config()
    label = {"display_name": "Display name", "username": "Username", "bio": "Bio"}[field]
    return r_ok(f"{label} updated to: {value}")
