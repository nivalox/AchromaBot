"""Fixed values: version info, URLs, file paths and the default configuration."""
import os

AXION_VERSION = "1.1.0"
AUTHOR = "nivalos"
POWERED_BY = "(Powered by Marin, Alya, Konata & Mimi Typh)"

# config.json and secrets.json live next to main.py, one level above this package
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SECRETS_PATH = os.path.join(BASE_DIR, "secrets.json")
# These live in secrets.json (keep it out of git). config.json holds no secrets and is safe to commit.
SECRET_KEYS = ("cookie", "accounts", "fingerprint", "quickacc_password", "gemini_api_key", "grants")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
SITE_URL = "https://bikesense.org"
BASE = f"{SITE_URL}/api/chat/messages"
TYPING_URL = f"{SITE_URL}/api/chat/typing"
PROFILE_URL = f"{SITE_URL}/api/chat/me"
SIGNUP_URL = f"{SITE_URL}/api/chat/signup"
SIGNIN_URL = f"{SITE_URL}/api/chat/signin"
USERS_URL = f"{SITE_URL}/api/chat/users"
VOICE_JOIN_URL = f"{SITE_URL}/api/chat/voice/join"
VOICE_LEAVE_URL = f"{SITE_URL}/api/chat/voice/leave"
VOICE_STATE_URL = f"{SITE_URL}/api/chat/voice/state"
LINKGEN_URL = f"{SITE_URL}/api/linkgen/auto"
LINKGEN_REFERER = f"{SITE_URL}/pages/linkgen.html"

DEFAULT_PREFIX = "?"

# Hosts used for the "your connection" ping: a plain TCP connect, no ICMP or root needed
CLIENT_PING_HOSTS = (("1.1.1.1", 443), ("8.8.8.8", 443))

# What the auto reply can say. The text is editable with ?autoreply text <kind> <message>
AUTOREPLY_KINDS = {"unauth": "not authorized", "unknown": "unknown command"}
AUTOREPLY_ALIASES = {
    "unauth": "unauth", "unauthorized": "unauth", "unauthorised": "unauth", "auth": "unauth",
    "notauthorized": "unauth", "denied": "unauth",
    "unknown": "unknown", "command": "unknown", "commands": "unknown", "invalid": "unknown",
}

DEFAULTS = {
    "cookie": "",
    "channels": ["general", "media"],
    "target_user": "nivalos",
    "poll_interval": 0.5,
    "typing_interval": 3,
    "prefix": DEFAULT_PREFIX,
    "autoreply": {
        "enabled": True,
        "users": [],  # empty list means everyone
        "types": ["unauth", "unknown"],
        # {user} becomes @name and {cmd} the command that was typed
        "texts": {
            "unauth": "{user} you are not authorized to use this command.",
            "unknown": "{user} {cmd} isn't a command",
        },
    },
    "max_message_length": 500,  # longer messages are split, lower it if the site rejects them
    "silent_typing": {
        "method": "DELETE",
        "url": f"{SITE_URL}/api/chat/typing",
        "payload": {"channel": "general"},
        "interval": 0.3,
    },
    "profile": {"display_name": "", "username": "", "bio": ""},
    "autoreact": {"enabled": False, "emoji": "\U0001F62D", "users": []},
    "device": {"tz": "America/New_York", "screen": "431x958", "platform": "Android", "touch": True},
    "ai": {
        "model": "gemini-3.6-flash",
        "max_chars": 500,
        "cooldown": 10,
        "system_prompt": (
            "You are a helpful assistant replying in a chat room. "
            "Never go over {max_chars} characters when responding. "
            "Use no specific formatting, only plain text responses."
        ),
    },
    # Staying in a voice channel. I only know the join and leave requests, so the keepalive is a GUESS:
    # it repeats the join request. If the site uses a different heartbeat, put its URL in keepalive_url.
    "voice": {"keepalive_interval": 20, "keepalive_url": VOICE_JOIN_URL},
    "linkgen": {"filters": "goguardian", "links": 1},  # what ?linkgen asks for when you give no arguments
    "fingerprint": "",
    "accounts": {},
    "quickacc_password": "",
    "gemini_api_key": "",
    "grants": {},
}
