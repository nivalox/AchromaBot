"""Shared runtime data: the loaded config, the live STATE dict and small accessors.

Nothing here imports the UI, so every other module can import it safely. Values that used to be
rebound globals (the active username, the cookie, the prefix) are read through the accessors
below, which always look at CONFIG, so every module sees the current value."""
import copy
import json
import os

from .constants import CONFIG_PATH, DEFAULT_PREFIX, DEFAULTS, SECRET_KEYS, SECRETS_PATH


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise SystemExit(f"{os.path.basename(path)} is not valid JSON: {e}")


def valid_prefix(p):
    """1 to 3 characters, no letters, digits or spaces. @ and brackets are taken by mentions."""
    return (
        isinstance(p, str) and 1 <= len(p) <= 3
        and not any(c.isalnum() or c.isspace() or c in "@<>[]()\"'`\\" for c in p)
    )


def load_config():
    """Returns (config, needs_migration)."""
    public = read_json(CONFIG_PATH)
    secrets = read_json(SECRETS_PATH)
    # Older config.json files kept secrets inline, they get moved out on the first save
    needs_migration = any(public.get(k) for k in SECRET_KEYS)
    raw = {**public, **secrets}

    defaults = copy.deepcopy(DEFAULTS)
    cfg = {**defaults, **copy.deepcopy(raw)}
    # Merge nested sections so a partial entry still gets the other defaults
    for key in ("silent_typing", "profile", "autoreact", "ai", "autoreply", "voice", "linkgen"):
        cfg[key] = {**defaults[key], **copy.deepcopy(raw.get(key, {}))}
    raw_auto = raw.get("autoreply", {})
    cfg["autoreply"]["texts"] = {**defaults["autoreply"]["texts"], **raw_auto.get("texts", {})}
    if "auto_reply" in raw and "autoreply" not in raw:  # the old on/off switch
        cfg["autoreply"]["enabled"] = bool(raw["auto_reply"])
    cfg.pop("auto_reply", None)
    cfg["autoreply"]["users"] = [str(u).lower().lstrip("@") for u in cfg["autoreply"]["users"]]
    cfg["autoreply"]["types"] = [t for t in cfg["autoreply"]["types"] if t in defaults["autoreply"]["texts"]]

    cfg["channels"] = [c.lower() for c in cfg["channels"]] or ["general"]
    cfg["accounts"] = dict(cfg["accounts"])
    # Grants are stored without the prefix, so changing the prefix never breaks them
    cfg["grants"] = {
        k.lower(): list(dict.fromkeys(c.lower().lstrip("?") for c in v)) for k, v in cfg["grants"].items()
    }
    if not valid_prefix(cfg.get("prefix")):
        cfg["prefix"] = DEFAULT_PREFIX
    return cfg, needs_migration


CONFIG_MISSING = not os.path.exists(CONFIG_PATH)
SECRETS_MISSING = not os.path.exists(SECRETS_PATH)
CONFIG, NEEDS_MIGRATION = load_config()

PROFILE = CONFIG["profile"]  # local copy of your profile, kept in place so it is never rebound
AUTOREACT = CONFIG["autoreact"]  # enabled, emoji, users (empty list means everyone)
CHANNELS = CONFIG["channels"]  # general, media, plus any DM channels you add
LAST_ID = {}  # channel -> newest message id already handled

STATE = {
    "rtt": 0.0,
    "terminal": True,
    "channel": CONFIG["channels"][0],  # where terminal commands reply and echo
    "typing_channel": CONFIG["channels"][0],
    "users": {},  # username -> user id, learned from messages
    "warned": set(),
    "online": True,  # False while the connection is down, the prompt shows a !
    "ai_last": {},  # username -> time of their last ?ai, for the cooldown
}


def target_user():
    return CONFIG["target_user"].lower()


def cookie():
    return CONFIG["cookie"]


def prefix():
    return CONFIG["prefix"]


def is_owner(username):
    """Owners are the accounts saved in secrets.json, the bot answers all of them."""
    return username in CONFIG["accounts"]
