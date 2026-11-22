import getpass
import json
import os
from collections import deque
import platform
import random
import re
import select
import shutil
import string
import sys
import subprocess
import threading
import time
import uuid
import requests

START_TIME = time.time()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SECRETS_PATH = os.path.join(BASE_DIR, "secrets.json")
# These live in secrets.json (keep it out of git). config.json holds no secrets and is safe to commit.
SECRET_KEYS = ("cookie", "accounts", "fingerprint", "quickacc_password", "gemini_api_key", "grants")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULTS = {
    "cookie": "",
    "channels": ["general", "media"],
    "target_user": "nivalos",
    "poll_interval": 0.5,
    "typing_interval": 3,
    "auto_reply": True,
    "max_message_length": 500,  # longer messages are split, lower it if the site rejects them
    "silent_typing": {
        "method": "DELETE",
        "url": "https://bikesense.org/api/chat/typing",
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
    "fingerprint": "",
    "accounts": {},
    "quickacc_password": "",
    "gemini_api_key": "",
    "grants": {},
}
NEEDS_MIGRATION = False
CONFIG_MISSING = not os.path.exists(CONFIG_PATH)
SECRETS_MISSING = not os.path.exists(SECRETS_PATH)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise SystemExit(f"{os.path.basename(path)} is not valid JSON: {e}")


def write_json(path, data, private=False):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        if private:
            os.chmod(path, 0o600)
    except OSError as e:
        print(f"Could not save {os.path.basename(path)}: {e}")


def load_config():
    global NEEDS_MIGRATION
    public = read_json(CONFIG_PATH)
    secrets = read_json(SECRETS_PATH)
    # Older config.json files kept secrets inline, they get moved out on the first save
    NEEDS_MIGRATION = any(public.get(k) for k in SECRET_KEYS)
    raw = {**public, **secrets}

    cfg = {**DEFAULTS, **raw}
    # Merge nested sections so a partial entry still gets the other defaults
    for key in ("silent_typing", "profile", "autoreact", "ai"):
        cfg[key] = {**DEFAULTS[key], **raw.get(key, {})}
    cfg["channels"] = [c.lower() for c in cfg["channels"]] or ["general"]
    cfg["accounts"] = dict(cfg["accounts"])
    cfg["grants"] = {k.lower(): list(v) for k, v in cfg["grants"].items()}
    return cfg


def sync_active_account():
    """Keeps the active account's cookie and profile stored under "accounts"."""
    key = CONFIG["target_user"].lower()
    acc = CONFIG.setdefault("accounts", {}).setdefault(key, {})
    acc["cookie"] = CONFIG["cookie"]
    acc["profile"] = dict(CONFIG["profile"])


def save_config():
    sync_active_account()
    secrets = {k: CONFIG[k] for k in SECRET_KEYS if k in CONFIG}
    public = {k: v for k, v in CONFIG.items() if k not in SECRET_KEYS}
    # Blank placeholders keep config.json the same shape while staying safe to commit
    public = {"cookie": "", **public, "quickacc_password": ""}
    write_json(CONFIG_PATH, public)
    write_json(SECRETS_PATH, secrets, private=True)


CONFIG = load_config()
sync_active_account()
if NEEDS_MIGRATION:
    save_config()
    print("Moved your secrets out of config.json into secrets.json")

STATE = {
    "rtt": 0.0,
    "terminal": True,
    "channel": CONFIG["channels"][0],  # where terminal commands reply and echo
    "typing_channel": CONFIG["channels"][0],
    "users": {},  # username -> user id, learned from messages
    "warned": set(),
    "ai_last": {},  # username -> time of their last ?ai, for the cooldown
}
LAST_ID = {}  # channel -> newest message id already handled

BASE = "https://bikesense.org/api/chat/messages"
TYPING_URL = "https://bikesense.org/api/chat/typing"
TYPING_INTERVAL = CONFIG["typing_interval"]  # seconds between typing pings, lower it if the indicator flickers

PROFILE_URL = "https://bikesense.org/api/chat/me"
SIGNUP_URL = "https://bikesense.org/api/chat/signup"
SIGNIN_URL = "https://bikesense.org/api/chat/signin"
# Local copy of your profile, stored in config.json. The PATCH sends all three fields,
# so it is updated and saved after every successful change.
PROFILE = CONFIG["profile"]
PROFILE_FIELDS = {"name": "display_name", "user": "username", "bio": "bio"}
PROFILE_USAGE = "Usage: ?profile name/user/bio <text> or ?profile show"

HELP = {
    "?ping": "shows the current ping",
    "?stats": "shows phone and Termux stats",
    "?snipe": "shows the latest deleted message in this channel",
    "?csnipe": "clears sniped messages, also ?clearsnipe",
    "?echo": "?echo <text> sends the text you typed",
    "?ai": "?ai <question> asks Gemini, answers in plain text",
    "?typing": "?typing on/off toggles the typing indicator",
    "?silenttyping": "?silenttyping on/off cancels your typing indicator",
    "?autoreact": "?autoreact on/off, emoji <e>, users <names or all> reacts to new messages",
    "?autoreply": "?autoreply on/off toggles the wrong command and unauthorized replies",
    "?channel": "?channel [add/remove <name>] lists or changes the watched channels",
    "?dm": "?dm <user id, username or dm name> starts watching a DM",
    "?profile": "?profile name/user/bio <text> changes your profile, ?profile show views it",
    "?grant": "?grant <user> [commands or all] lets others use some commands",
    "?revoke": "?revoke <user> [commands] takes commands back",
    "?grants": "lists who has been granted commands",
    "?signin": "signs in from the terminal and refreshes the session, also ?signing",
    "?signup": "creates an account, details are entered in the terminal",
    "?quickacc": "?quickacc [-c pass] creates a random account, signs in and saves it",
    "?creds": "shows credits",
    "?help": "?help [command] lists the commands or explains one",
}
HELP_ALIASES = {"?clearsnipe": "?csnipe", "?signing": "?signin"}


def help_text(args, is_owner, user, local):
    allowed = list(HELP) if is_owner else [c for c in HELP if c in CONFIG["grants"].get(user, [])]
    if args:
        name = "?" + args[0].lower().lstrip("?")
        name = HELP_ALIASES.get(name, name)
        return f"{name} : {HELP[name]}" if name in allowed else f"No help for {name}"
    if local:  # the terminal has no length limit, so show everything
        lines = [f"{c} : {d}" for c, d in HELP.items()]
        return "\n".join(lines) + "\n\nTerminal only:\n" + TERMINAL_HELP + "\n(made by nivalos in python)"
    label = "Commands" if is_owner else "Commands you can use"
    return f"{label}: {' '.join(allowed)}\n?help <command> for details\n(made by nivalos in python)"


CREDS_TEXT = (
    "Credits:\n"
    "Made by nivalos\n"
    "Written in python, running on Termux (Android)"
)
CHANNELS = CONFIG["channels"]  # general, media, plus any DM channels you add
TARGET_USER = CONFIG["target_user"].lower()
TRIGGER = "?ping"
POLL_INTERVAL = CONFIG["poll_interval"]  # seconds between polls

# Silent typing: spams a "stop typing" request to cancel your own typing indicator.
# I do not know the real stop request, so the config default is a GUESS. Capture the
# curl the site sends when you stop typing and fix "silent_typing" in config.json.
SILENT_METHOD = CONFIG["silent_typing"]["method"]
SILENT_URL = CONFIG["silent_typing"]["url"]
SILENT_PAYLOAD = CONFIG["silent_typing"]["payload"]
SILENT_INTERVAL = CONFIG["silent_typing"]["interval"]  # seconds between cancel requests

# Session cookie from secrets.json. Keep that file private, it logs in as you.
COOKIE = CONFIG["cookie"]

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US",
    "cookie": COOKIE,
    "origin": "https://bikesense.org",
    "referer": "https://bikesense.org/pages/chat.html",
    "sec-ch-ua": '"Chromium";v="127", "Not)A;Brand";v="99", "Microsoft Edge Simulate";v="127", "Lemur";v="127"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36"
    ),
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch_messages(channel=None, retry=True):
    """Returns (messages, round_trip_ms). On a 401 it offers a terminal sign in and retries once."""
    channel = channel or STATE["channel"]
    start = time.perf_counter()
    r = session.get(BASE, params={"channel": channel}, timeout=15)
    rtt = (time.perf_counter() - start) * 1000
    if r.status_code == 401:
        if retry:
            ok, _ = sign_in("The site rejected your session cookie (401). Sign in to get a new one.")
            if ok:
                return fetch_messages(channel, retry=False)
        raise SystemExit(
            "401 Unauthorized: the site rejected your cookie and no new sign in happened. "
            "Run the script again to sign in, or paste a fresh cookie into secrets.json."
        )
    r.raise_for_status()
    return r.json().get("messages", []), rtt


def split_message(text, limit):
    """Splits text into chunks of at most limit characters, preferring line and word breaks."""
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            cut = line.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:cut])
            line = line[cut:].lstrip()
        candidate = f"{cur}\n{line}" if cur else line
        if len(candidate) <= limit:
            cur = candidate
        else:
            chunks.append(cur)
            cur = line
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()] or [""]


def send_message(text, channel=None):
    """Posts a message, splitting it if it is too long. Errors are printed, never raised."""
    channel = channel or STATE["channel"]
    last = None
    for chunk in split_message(text, CONFIG["max_message_length"]):
        payload = {"text": chunk, "channel": channel, "attachment": None, "reply_to": None}
        try:
            r = session.post(BASE, json=payload, timeout=15)  # json= sets content-type
        except requests.RequestException as e:
            print(f"Could not send message: {e}")
            return last
        if r.status_code >= 400:
            print(f"Could not send message to {channel} ({r.status_code}): {r.text[:150]}")
            if r.status_code in (400, 413, 422):
                print("If the message was too long, lower max_message_length in config.json")
            return last
        last = r
    return last


typing_stop = threading.Event()
typing_thread = None


def typing_loop():
    # Own session so we never share one with the main thread
    s = requests.Session()
    s.headers.update(HEADERS)
    while not typing_stop.is_set():
        try:
            s.headers["cookie"] = HEADERS["cookie"]
            s.post(TYPING_URL, json={"channel": STATE["typing_channel"]}, timeout=10)
        except requests.RequestException as e:
            print(f"Typing error: {e}")
        typing_stop.wait(TYPING_INTERVAL)


def set_typing(on, channel=None):
    global typing_thread
    if on:
        STATE["typing_channel"] = channel or STATE["channel"]
        if typing_thread and typing_thread.is_alive():
            print(f"Typing now in {STATE['typing_channel']}")
            return
        typing_stop.clear()
        typing_thread = threading.Thread(target=typing_loop, daemon=True)
        typing_thread.start()
        print(f"Typing ON in {STATE['typing_channel']}")
    else:
        typing_stop.set()
        print("Typing OFF")


silent_stop = threading.Event()
silent_thread = None


def silent_loop():
    s = requests.Session()
    s.headers.update(HEADERS)
    warned = False
    while not silent_stop.is_set():
        try:
            s.headers["cookie"] = HEADERS["cookie"]
            for ch in list(CHANNELS):
                r = s.request(SILENT_METHOD, SILENT_URL, json={**SILENT_PAYLOAD, "channel": ch}, timeout=10)
                if r.status_code >= 400 and not warned:
                    print(f"Silent typing request returned {r.status_code}, the guessed request is probably wrong")
                    warned = True
        except requests.RequestException as e:
            if not warned:
                print(f"Silent typing error: {e}")
                warned = True
        silent_stop.wait(SILENT_INTERVAL)


def set_silent(on):
    global silent_thread
    if on:
        # Our own typing loop would fight the cancel loop
        set_typing(False)
        if silent_thread and silent_thread.is_alive():
            return
        silent_stop.clear()
        silent_thread = threading.Thread(target=silent_loop, daemon=True)
        silent_thread.start()
        print("Silent typing ON")
    else:
        silent_stop.set()
        print("Silent typing OFF")


seen = {}  # channel -> {id: message}, messages currently inside the fetched window
sniped = {}  # channel -> deque of deleted messages, newest last


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
            sniped.setdefault(channel, deque(maxlen=50)).append({"msg": msg, "deleted_at": time.time()})
            del store[mid]
            print(f"Deleted message caught in {channel} (id {mid}) from {msg.get('username')}")

    store.update(current)


def get_snipe(channel):
    if not sniped.get(channel):
        return "Nothing to snipe"
    rec = sniped[channel][-1]
    msg = rec["msg"]
    ago = fmt_duration(time.time() - rec["deleted_at"])
    name = msg.get("display_name") or msg.get("username") or "unknown"
    text = (msg.get("body") or "").strip()
    att = msg.get("attachment")
    if att and isinstance(att, dict) and att.get("url"):
        text = f"{text}\n{att['url']}".strip()
    if not text:
        text = "(no text)"
    return f"Sniped, deleted {ago} ago\n{name} (@{msg.get('username')}): {text}"


def handle_profile(raw):
    """raw is the original message, so the text you set keeps its casing."""
    global TARGET_USER
    parts = raw.split(None, 2)  # ["?profile", "name", "some text"]
    if len(parts) < 2:
        return PROFILE_USAGE

    sub = parts[1].lower()
    if sub == "show":
        return (
            f"Display name: {PROFILE['display_name']}\n"
            f"Username: {PROFILE['username']}\n"
            f"Bio: {PROFILE['bio']}"
        )

    field = PROFILE_FIELDS.get(sub)
    if not field or len(parts) < 3 or not parts[2].strip():
        return PROFILE_USAGE

    value = parts[2].strip()
    new = {k: v for k, v in PROFILE.items() if v}  # blank means unknown, leave it out
    new[field] = value
    try:
        r = session.patch(PROFILE_URL, json=new, timeout=15)
    except requests.RequestException as e:
        return f"Profile update failed: {e}"
    if r.status_code >= 400:
        return f"Profile update failed ({r.status_code}): {r.text[:150]}"

    PROFILE.update(new)
    if field == "username":
        # Keep recognizing you after the rename, and remember it across restarts
        CONFIG["accounts"].pop(TARGET_USER, None)
        TARGET_USER = value.lower()
        CONFIG["target_user"] = TARGET_USER
    save_config()
    label = {"display_name": "Display name", "username": "Username", "bio": "Bio"}[field]
    return f"{label} updated to: {value}"


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_duration(sec):
    sec = int(sec)
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    return f"{d}d {h}h {m}m {s}s" if d else f"{h}h {m}m {s}s"


def get_stats():
    lines = ["Termux stats:"]

    # Battery (needs the Termux:API app and `pkg install termux-api`)
    try:
        out = subprocess.run(
            ["termux-battery-status"], capture_output=True, text=True, timeout=10
        ).stdout
        b = json.loads(out)
        lines.append(
            f"Battery: {b.get('percentage')}% ({b.get('status', '?').lower()}, "
            f"plugged: {b.get('plugged', '?')})"
        )
        lines.append(f"Battery temp: {b.get('temperature')} C, health: {b.get('health')}")
    except Exception:
        lines.append("Battery: unavailable (install Termux:API and termux-api)")

    # RAM
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) * 1024
        total = info["MemTotal"]
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        lines.append(f"RAM: {fmt_bytes(total - avail)} / {fmt_bytes(total)} used")
    except Exception:
        lines.append("RAM: unavailable")

    # Storage
    try:
        du = shutil.disk_usage(os.path.expanduser("~"))
        lines.append(f"Storage: {fmt_bytes(du.used)} / {fmt_bytes(du.total)} used")
    except Exception:
        lines.append("Storage: unavailable")

    # CPU
    lines.append(f"CPU cores: {os.cpu_count()}")
    try:
        l1, l5, l15 = os.getloadavg()
        lines.append(f"Load avg: {l1:.2f} {l5:.2f} {l15:.2f}")
    except Exception:
        pass

    # Uptime
    try:
        with open("/proc/uptime") as f:
            lines.append(f"Uptime: {fmt_duration(float(f.read().split()[0]))}")
    except Exception:
        pass

    lines.append(f"Python: {platform.python_version()}")
    lines.append(f"Script uptime: {fmt_duration(time.time() - START_TIME)}")
    return "\n".join(lines)


def anon_session():
    """A fresh session without your login cookie, like the browser has before signing in."""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["cookie"] = "; ".join(
        p for p in COOKIE.split("; ") if p and not p.startswith("achroma-chat=")
    )
    return s


def set_full_cookie(cookie):
    """Makes a full cookie string the active one, in memory only."""
    global COOKIE
    COOKIE = cookie
    HEADERS["cookie"] = COOKIE
    session.headers["cookie"] = COOKIE
    CONFIG["cookie"] = COOKIE


def adopt_cookie(token):
    """Swaps a new login token into the running bot and saves it to secrets.json."""
    parts = [p for p in COOKIE.split("; ") if p and not p.startswith("achroma-chat=")]
    parts.append(f"achroma-chat={token}")
    set_full_cookie("; ".join(parts))
    save_config()


def login_with(username, password):
    """Posts the signin request. On success that account becomes the active one and is
    saved under accounts. Returns (ok, message for chat)."""
    global TARGET_USER
    if not CONFIG.get("fingerprint"):
        CONFIG["fingerprint"] = str(uuid.uuid4())
        save_config()

    payload = {
        "username": username,
        "password": password,
        "fingerprint": CONFIG["fingerprint"],
        "device": CONFIG["device"],
    }
    s = anon_session()
    try:
        r = s.post(SIGNIN_URL, json=payload, timeout=15)
    except requests.RequestException as e:
        print(f"[signin] Request error: {e}")
        return False, "Sign in failed, check the terminal"

    print(f"[signin] Status {r.status_code}: {r.text[:200]}")
    if r.status_code >= 400:
        return False, f"Sign in failed ({r.status_code}), check the terminal"

    token = next((c.value for c in s.cookies if c.name == "achroma-chat"), None)
    if not token:
        print("[signin] Signed in, but the response did not set an achroma-chat cookie.")
        return False, "Signed in, but no session cookie came back, check the terminal"

    if username.lower() != TARGET_USER:
        # The bot now acts as this account, so recognize its commands instead
        save_config()  # stores the account we are leaving
        set_typing(False)
        set_silent(False)
        saved = CONFIG["accounts"].get(username.lower(), {}).get("profile")
        PROFILE.clear()
        PROFILE.update(saved or {"display_name": "", "username": username, "bio": ""})
        TARGET_USER = username.lower()
        CONFIG["target_user"] = TARGET_USER
        print(f"[signin] Now acting as {username}")
    adopt_cookie(token)
    print("[signin] Session updated and saved to secrets.json")
    return True, "Signed in, session updated"


def sign_in(reason=None):
    """Asks for the password in the terminal, signs in, and continues with the new session.
    Returns (ok, message for chat)."""
    global TARGET_USER
    print(f"\n[signin] {reason or 'Sign in to refresh the session'} (leave the password empty to cancel)")
    try:
        username = input(f"Username [{TARGET_USER}]: ").strip() or TARGET_USER
        password = getpass.getpass("Password: ")
        if not password:
            print("Cancelled")
            return False, "Sign in cancelled"
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled")
        return False, "Sign in cancelled"

    return login_with(username, password)


def quick_account(args):
    """Creates an account with a random 10 letter username, signs in as it, and saves it
    to the accounts list. The default password comes from config, -c sets a custom one."""
    password = CONFIG["quickacc_password"]
    if args:
        if len(args) == 2 and args[0] == "-c":
            password = args[1]
        else:
            print("[quickacc] Usage: quickacc [-c <password>]")
            return
    if not password:
        print("[quickacc] No default password set. Use quickacc -c <password>, or set quickacc_password in secrets.json")
        return

    s = anon_session()  # no login cookie, so the signup is not tied to the active account
    username = None
    for _ in range(5):
        candidate = "".join(random.choices(string.ascii_lowercase, k=10))
        payload = {"username": candidate, "password": password, "device": CONFIG["device"]}
        try:
            r = s.post(SIGNUP_URL, json=payload, timeout=15)
        except requests.RequestException as e:
            print(f"[quickacc] Request error: {e}")
            return
        taken = r.status_code == 409 or (
            r.status_code == 400 and any(w in r.text.lower() for w in ("taken", "exist", "already"))
        )
        if taken:
            continue  # unlucky name, roll another
        print(f"[quickacc] Status {r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            return
        username = candidate
        break
    if not username:
        print("[quickacc] Could not find a free username after 5 tries")
        return

    print(f"[quickacc] Created account {username} with password {password}")
    ok, _ = login_with(username, password)
    if ok:
        print(f"[quickacc] Signed in as {username} and saved it. Use switch <name> to change accounts.")
    else:
        print("[quickacc] The account exists but sign in failed. Use addaccount with the details above.")


def signup_account():
    """Asks for a username and password in the terminal, then fires one signup request.
    The signup uses a fresh session without your login cookie, so it is a clean new account."""
    print("\n[signup] Enter the new account details (leave the username empty to cancel)")
    try:
        username = input("Username: ").strip()
        if not username:
            print("Cancelled")
            return "Account creation cancelled"
        password = getpass.getpass("Password: ")
        if not password:
            print("Cancelled")
            return "Account creation cancelled"
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled")
        return "Account creation cancelled"

    s = anon_session()  # no login cookie, so the signup is not tied to your main account
    payload = {"username": username, "password": password, "device": CONFIG["device"]}
    try:
        r = s.post(SIGNUP_URL, json=payload, timeout=15)
    except requests.RequestException as e:
        print(f"[signup] Request error: {e}")
        return "Account creation failed, check the terminal"

    print(f"[signup] Status {r.status_code}: {r.text[:200]}")
    if r.status_code >= 400:
        return f"Account creation failed ({r.status_code}), check the terminal"

    new_cookie = s.cookies.get("achroma-chat")
    if new_cookie:
        print(f"[signup] Login cookie for the new account: achroma-chat={new_cookie}")
    return "Account created, check the terminal"


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
            print(f"Auto react failed on {m['id']} ({r.status_code}): {r.text[:100]}")
    except requests.RequestException as e:
        print(f"Auto react error: {e}")


def autoreact_status():
    state = "on" if AUTOREACT["enabled"] else "off"
    users = ", ".join(AUTOREACT["users"]) or "everyone"
    return f"Auto react: {state}, emoji: {AUTOREACT['emoji']}, users: {users}"


def handle_autoreact(args):
    if not args or args[0].lower() == "show":
        return autoreact_status()
    sub = args[0].lower()
    if sub in ("on", "off"):
        AUTOREACT["enabled"] = sub == "on"
        save_config()
        return "Auto react is enabled" if AUTOREACT["enabled"] else "Auto react is disabled"
    if sub == "emoji" and len(args) > 1:
        AUTOREACT["emoji"] = args[1]
        save_config()
        return f"Auto react emoji set to {args[1]}"
    if sub == "users" and len(args) > 1:
        names = [a.lower().lstrip("@") for a in args[1:]]
        AUTOREACT["users"] = [] if names == ["all"] else names
        save_config()
        return autoreact_status()
    return "Usage: ?autoreact on/off, ?autoreact emoji <emoji>, ?autoreact users <names or all>"


COMMANDS = {
    "?ping", "?typing", "?silenttyping", "?profile", "?echo",
    "?snipe", "?csnipe", "?clearsnipe", "?stats", "?creds", "?help", "?autoreply", "?autoreact", "?channel", "?dm", "?ai", "?grant", "?revoke", "?grants", "?quickacc", "?signup", "?signin", "?signing",
}
AUTOREACT = CONFIG["autoreact"]  # enabled, emoji, users (empty list means everyone)
AUTO_REPLY = CONFIG["auto_reply"]  # when False, no "isn't a command" or "not authorized" replies
UNAUTH_TEXT = "you are not authorized to use this command."


def handle_message(m, rtt, reply=None, local=False):
    global AUTO_REPLY
    channel = m.get("channel") or STATE["channel"]
    reply = reply or (lambda t: send_message(t, channel))
    raw = (m.get("body") or "").strip()
    body = raw.lower()
    user = (m.get("username") or "").lower()
    parts = body.split()
    if not parts:
        return

    # Never react to our own "isn't a command" reply, it starts with the bad command
    if body.endswith("isn't a command"):
        return

    # A command is a first word of "?" plus letters only, so "?", "??" and "?!" are ignored
    cmd = parts[0]
    if not re.fullmatch(r"\?[a-z]+", cmd):
        return

    is_owner = user in CONFIG["accounts"]
    granted = cmd in CONFIG["grants"].get(user, [])
    if not (is_owner or granted):
        if cmd in COMMANDS and AUTO_REPLY:
            reply(UNAUTH_TEXT)
        return

    if cmd not in COMMANDS:
        if AUTO_REPLY or local:
            reply(f"{cmd} isn't a command")
        return

    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "?ping":
        print(f"Got ?ping (id {m['id']}), ping {rtt:.0f} ms")
        reply(f"ping: {rtt:.0f} ms")
    elif cmd == "?typing":
        if arg not in ("on", "off"):
            reply("Usage: ?typing on/off")
            return
        on = arg == "on"
        reply("Typing is enabled" if on else "Typing is disabled")
        if on:
            set_silent(False)
        set_typing(on, channel)
    elif cmd == "?silenttyping":
        if arg not in ("on", "off"):
            reply("Usage: ?silenttyping on/off")
            return
        on = arg == "on"
        reply("Silent typing is enabled" if on else "Silent typing is disabled")
        set_silent(on)
    elif cmd == "?profile":
        reply(handle_profile(raw))
    elif cmd == "?echo":
        text = raw[len("?echo"):].strip()
        if text:
            send_message(text, channel)  # echo always goes to the chat
            if local:
                print("[bot] sent to chat")
        else:
            reply("Usage: ?echo <text>")
    elif cmd == "?snipe":
        reply(get_snipe(channel))
    elif cmd in ("?csnipe", "?clearsnipe"):
        sniped.get(channel, deque()).clear()
        reply("Snipe cleared")
    elif cmd == "?stats":
        reply(get_stats())
    elif cmd == "?creds":
        reply(CREDS_TEXT)
    elif cmd == "?autoreply":
        if arg not in ("on", "off"):
            reply("Usage: ?autoreply on/off")
            return
        AUTO_REPLY = arg == "on"
        CONFIG["auto_reply"] = AUTO_REPLY
        save_config()
        reply("Auto replies are enabled" if AUTO_REPLY else "Auto replies are disabled")
    elif cmd in ("?signin", "?signing"):
        if not local:
            reply("Go back to the terminal to sign in")
        reply(sign_in()[1])
    elif cmd == "?signup":
        if not local:
            reply("Go back to the terminal to enter the account details")
        reply(signup_account())
    elif cmd == "?quickacc":
        if not local:
            reply("Creating a quick account, the details are in the terminal")
        quick_account(raw.split()[1:])  # prints its own result in the terminal
    elif cmd == "?ai":
        prompt = raw[len("?ai"):].strip()
        if not prompt:
            reply("Usage: ?ai <question>")
            return
        wait = 0 if is_owner else ai_wait(user)
        if wait > 0:
            reply(f"Slow down, try again in {wait:.0f}s")
            return
        STATE["ai_last"][user] = time.time()
        print(f"[ai] {user} in {channel}: {prompt[:80]}")
        reply(ask_gemini(prompt))
    elif cmd == "?grant":
        reply(handle_grant(raw.split()[1:]))
    elif cmd == "?revoke":
        reply(handle_revoke(raw.split()[1:]))
    elif cmd == "?grants":
        reply(list_grants())
    elif cmd == "?channel":
        reply(handle_channel(raw.split()[1:]))
    elif cmd == "?dm":
        reply(handle_dm(raw.split()[1:]))
    elif cmd == "?autoreact":
        reply(handle_autoreact(raw.split()[1:]))
    elif cmd == "?help":
        reply(help_text(raw.split()[1:], is_owner, user, local))


def get_ai_key():
    return CONFIG["gemini_api_key"] or os.environ.get("GEMINI_API_KEY", "")


def gemini_headers():
    # Only the API key goes to Google, never the bikesense cookie
    return {"x-goog-api-key": get_ai_key(), "content-type": "application/json"}


def clean_reply(text, max_chars):
    """Plain text only, one line, never longer than max_chars."""
    text = re.sub(r"[*`]", "", text)
    text = re.sub(r"(?m)^\s*#+\s*", "", text)
    text = " ".join(text.split())
    if len(text) > max_chars:
        cut = text[:max_chars]
        space = cut.rfind(" ")
        text = cut[:space] if space > max_chars * 0.6 else cut
    return text.strip()


def ask_gemini(prompt):
    if not get_ai_key():
        return "AI is not set up yet, add the API key in the terminal with aikey"
    ai = CONFIG["ai"]
    system = ai["system_prompt"].replace("{max_chars}", str(ai["max_chars"]))
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt[:1000]}]}],
    }
    try:
        r = requests.post(
            f"{GEMINI_BASE}/models/{ai['model']}:generateContent",
            headers=gemini_headers(),
            json=body,
            timeout=20,
        )
    except requests.RequestException as e:
        print(f"[ai] Request error: {e}")
        return "AI request failed, try again"
    if r.status_code != 200:
        print(f"[ai] Gemini returned {r.status_code}: {r.text[:200]}")
        return f"AI error ({r.status_code})"
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    except (KeyError, IndexError, TypeError, ValueError):
        print(f"[ai] No usable answer: {r.text[:200]}")
        return "AI gave no answer for that"
    text = clean_reply(text, ai["max_chars"])
    return text or "AI gave no answer for that"


def ai_wait(user):
    return CONFIG["ai"]["cooldown"] - (time.time() - STATE["ai_last"].get(user, 0))


def ai_status():
    key = "set" if get_ai_key() else "not set (use aikey)"
    return f"Model: {CONFIG['ai']['model']}\nAPI key: {key}\nUse aimodels to list models and aimodel <name> to switch"


def set_ai_key(args):
    if args and args[0].lower() == "remove":
        CONFIG["gemini_api_key"] = ""
        save_config()
        return "API key removed"
    try:
        key = getpass.getpass("Gemini API key (hidden, leave empty to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        return "Cancelled"
    if not key:
        return "Cancelled"
    CONFIG["gemini_api_key"] = key
    save_config()
    return "API key saved to secrets.json"


def list_ai_models():
    if not get_ai_key():
        return "Set the API key first with aikey"
    names, token = [], None
    try:
        for _ in range(5):  # a few pages is plenty
            params = {"pageSize": 100}
            if token:
                params["pageToken"] = token
            r = requests.get(f"{GEMINI_BASE}/models", headers=gemini_headers(), params=params, timeout=15)
            if r.status_code != 200:
                return f"Could not list models ({r.status_code}): {r.text[:150]}"
            data = r.json()
            for m in data.get("models", []):
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    names.append(m["name"].removeprefix("models/"))
            token = data.get("nextPageToken")
            if not token:
                break
    except (requests.RequestException, ValueError) as e:
        return f"Could not list models: {e}"
    active = CONFIG["ai"]["model"]
    return "\n".join(f"{'*' if n == active else ' '} {n}" for n in sorted(names)) + "\n(* is active)"


def set_ai_model(name):
    name = name.strip().removeprefix("models/")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
        return "That does not look like a model name"
    note = ""
    if get_ai_key():
        try:
            r = requests.get(f"{GEMINI_BASE}/models/{name}", headers=gemini_headers(), timeout=15)
            if r.status_code == 404:
                return f"Model {name} was not found, use aimodels to see what is available"
            if r.status_code != 200:
                note = f" (could not verify it, status {r.status_code})"
        except requests.RequestException:
            note = " (could not verify it, network error)"
    CONFIG["ai"]["model"] = name
    save_config()
    return f"Model set to {name}{note}"


GRANTABLE = {"?ping", "?help", "?creds", "?snipe", "?stats", "?ai", "?echo"}
DEFAULT_GRANT = ["?ping", "?help", "?creds", "?ai"]


def list_grants():
    if not CONFIG["grants"]:
        return "No one has been granted commands"
    return "\n".join(f"{u}: {' '.join(c)}" for u, c in sorted(CONFIG["grants"].items()))


def handle_grant(args):
    usage = "Usage: ?grant <user> [commands or all]. Grantable: " + " ".join(sorted(GRANTABLE))
    if not args:
        return usage
    user = args[0].lower().lstrip("@")
    if user in CONFIG["accounts"]:
        return f"{user} is already one of your accounts"
    names = ["?" + a.lower().lstrip("?") for a in args[1:]]
    if not names:
        cmds = DEFAULT_GRANT
    elif names == ["?all"]:
        cmds = sorted(GRANTABLE)
    else:
        bad = [n for n in names if n not in GRANTABLE]
        if bad:
            return f"Can't grant {' '.join(bad)}. Grantable: " + " ".join(sorted(GRANTABLE))
        cmds = names
    merged = sorted(set(CONFIG["grants"].get(user, [])) | set(cmds))
    CONFIG["grants"][user] = merged
    save_config()
    return f"{user} can now use: {' '.join(merged)}"


def handle_revoke(args):
    if not args:
        return "Usage: ?revoke <user> [commands]"
    user = args[0].lower().lstrip("@")
    if user not in CONFIG["grants"]:
        return f"{user} has no granted commands"
    names = ["?" + a.lower().lstrip("?") for a in args[1:]]
    if not names:
        del CONFIG["grants"][user]
        save_config()
        return f"Revoked everything from {user}"
    left = [c for c in CONFIG["grants"][user] if c not in names]
    if left:
        CONFIG["grants"][user] = left
    else:
        del CONFIG["grants"][user]
    save_config()
    return f"{user} can now use: {' '.join(left)}" if left else f"Revoked everything from {user}"


TERMINAL_HELP = (
    "accounts : lists saved accounts\n"
    "switch <name> : switches to a saved account\n"
    "addaccount : signs in to another account and switches to it\n"
    "removeaccount <name> : forgets a saved account\n"
    "aikey : sets the Gemini API key (hidden input, saved to secrets.json)\n"
    "aimodel [name] : shows or sets the Gemini model\n"
    "aimodels : lists the models your key can use\n"
    "use <channel> : sets the channel terminal commands reply and echo in\n"
    "quit : stops the bot\n"
    "Every chat command also works here, with or without the ?"
)


def terminal_reply(text):
    print("[bot] " + str(text).replace("\n", "\n      "))


def list_accounts():
    names = sorted(CONFIG["accounts"])
    return "\n".join(f"{'*' if n == TARGET_USER else ' '} {n}" for n in names) + "\n(* is active)"


def apply_account(key):
    """Makes a saved account the active one, in memory and on disk."""
    global TARGET_USER, COOKIE
    acc = CONFIG["accounts"][key]
    set_typing(False)
    set_silent(False)
    TARGET_USER = key
    CONFIG["target_user"] = key
    COOKIE = acc["cookie"]
    CONFIG["cookie"] = COOKIE
    HEADERS["cookie"] = COOKIE
    session.headers["cookie"] = COOKIE
    PROFILE.clear()
    PROFILE.update(acc.get("profile") or {"display_name": "", "username": key, "bio": ""})


def switch_account(name):
    key = name.lower().lstrip("@")
    if key not in CONFIG["accounts"]:
        return f"No saved account named {key}. Use accounts to list them or addaccount to add one."
    if key == TARGET_USER:
        return f"Already acting as {key}"
    save_config()  # stores the current account first, including a refreshed cookie
    previous = TARGET_USER
    apply_account(key)
    try:
        fetch_messages()  # checks the cookie, and offers a terminal sign in on a 401
    except SystemExit:
        apply_account(previous)
        save_config()
        return f"Could not switch to {key}, staying on {previous}"
    except requests.RequestException as e:
        save_config()
        return f"Now acting as {TARGET_USER}, but the check request failed: {e}"
    save_config()
    return f"Now acting as {TARGET_USER}"


def remove_account(name):
    key = name.lower().lstrip("@")
    if key == TARGET_USER:
        return "Can't remove the active account, switch to another one first"
    if CONFIG["accounts"].pop(key, None) is None:
        return f"No saved account named {key}"
    save_config()
    return f"Removed {key}"


def handle_terminal(line):
    line = line.strip()
    if not line:
        return
    if not line.startswith("?"):
        line = "?" + line
    parts = line.split()
    cmd, args = parts[0].lower(), parts[1:]

    if cmd == "?accounts":
        terminal_reply(list_accounts())
    elif cmd == "?switch":
        terminal_reply(switch_account(args[0]) if args else "Usage: switch <name>")
    elif cmd == "?addaccount":
        terminal_reply(sign_in("Add an account: type its username, or press enter for the current one")[1])
    elif cmd == "?removeaccount":
        terminal_reply(remove_account(args[0]) if args else "Usage: removeaccount <name>")
    elif cmd == "?aikey":
        terminal_reply(set_ai_key(args))
    elif cmd == "?aimodel":
        terminal_reply(set_ai_model(args[0]) if args else ai_status())
    elif cmd == "?aimodels":
        terminal_reply(list_ai_models())
    elif cmd == "?use":
        if not args:
            terminal_reply(f"Terminal channel: {STATE['channel']} (watching {', '.join(CHANNELS)})")
        elif args[0].lower() in CHANNELS:
            STATE["channel"] = args[0].lower()
            terminal_reply(f"Terminal now uses {STATE['channel']}")
        else:
            terminal_reply(f"Not watching {args[0]}, add it with channel add <name> first")
    elif cmd in ("?quit", "?exit"):
        raise KeyboardInterrupt
    else:
        # Same handler as chat, run as the active account, with replies printed here
        msg = {"id": 0, "username": TARGET_USER, "body": line, "channel": STATE["channel"]}
        handle_message(msg, STATE["rtt"], reply=terminal_reply, local=True)


def poll_terminal(timeout):
    """Waits up to timeout seconds, running any terminal commands typed in the meantime."""
    if not STATE["terminal"]:
        time.sleep(timeout)
        return
    try:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return
        data = os.read(sys.stdin.fileno(), 4096)
    except (OSError, ValueError):
        STATE["terminal"] = False  # no usable terminal, fall back to plain sleeping
        time.sleep(timeout)
        return
    if not data:
        STATE["terminal"] = False
        print("Terminal input closed, chat commands still work")
        return
    for line in data.decode(errors="replace").splitlines():
        handle_terminal(line)


def learn_users(msgs):
    """Remembers username -> user id, and your own accounts' ids (needed to build DM names)."""
    dirty = False
    for m in msgs:
        name = (m.get("username") or "").lower()
        uid = m.get("user_id")
        if not name or uid is None:
            continue
        STATE["users"][name] = uid
        acc = CONFIG["accounts"].get(name)
        if acc is not None and acc.get("user_id") != uid:
            acc["user_id"] = uid
            dirty = True
    if dirty:
        save_config()


def poll_channel(ch):
    """Fetches one channel and handles anything new. The first successful fetch only sets the baseline."""
    msgs, rtt = fetch_messages(ch)
    STATE["rtt"] = rtt
    learn_users(msgs)
    track_deletions(ch, msgs)
    if ch not in LAST_ID:
        LAST_ID[ch] = max((m["id"] for m in msgs), default=0)
        return
    for m in sorted((m for m in msgs if m["id"] > LAST_ID[ch]), key=lambda m: m["id"]):
        LAST_ID[ch] = m["id"]
        m["channel"] = ch
        auto_react(m)
        handle_message(m, rtt)


def warn_channel(ch, err):
    if ch not in STATE["warned"]:
        STATE["warned"].add(ch)
        code = err.response.status_code if err.response is not None else "?"
        print(f"Cannot read channel {ch} ({code}), will keep retrying quietly")


def add_channel(name):
    name = name.lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", name):
        return "Channel names are letters, numbers, - and _"
    if name in CHANNELS:
        return f"Already watching {name}"
    try:
        poll_channel(name)  # also proves the channel can be read, and sets its baseline
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        return f"Could not open {name} ({code})"
    except requests.RequestException as e:
        return f"Could not open {name}: {e}"
    CHANNELS.append(name)
    save_config()
    return f"Now watching {name}"


def remove_channel(name):
    name = name.lower()
    if name not in CHANNELS:
        return f"Not watching {name}"
    if len(CHANNELS) == 1:
        return "Can't remove the last channel"
    CHANNELS.remove(name)
    for store in (LAST_ID, seen, sniped):
        store.pop(name, None)
    if STATE["channel"] == name:
        STATE["channel"] = CHANNELS[0]
    save_config()
    return f"Stopped watching {name}"


def handle_channel(args):
    if not args or args[0].lower() in ("list", "show"):
        return "Watching: " + ", ".join(CHANNELS)
    sub = args[0].lower()
    if sub == "add" and len(args) > 1:
        return add_channel(args[1])
    if sub in ("remove", "rm") and len(args) > 1:
        return remove_channel(args[1])
    return "Usage: ?channel, ?channel add <name>, ?channel remove <name>"


def resolve_dm(target):
    """Turns a user id, a known username, or a full dm-a-b name into a DM channel name.
    Returns (channel, error)."""
    t = target.lower().lstrip("@")
    if re.fullmatch(r"dm-\d+-\d+", t):
        return t, None
    other = int(t) if t.isdigit() else STATE["users"].get(t)
    if other is None:
        return None, f"Don't know {t} yet. Use their numeric id, or wait until they post in a watched channel."
    mine = CONFIG["accounts"].get(TARGET_USER, {}).get("user_id") or STATE["users"].get(TARGET_USER)
    if mine is None:
        return None, "Your own user id is not known yet. Post in a watched channel first, or use the full dm-... name."
    if mine == other:
        return None, "That is your own account"
    a, b = sorted((mine, other))  # assumes the lower id comes first, like dm-6898-15939
    return f"dm-{a}-{b}", None


def handle_dm(args):
    if not args:
        return "Usage: ?dm <user id, username or dm-a-b name>"
    channel, err = resolve_dm(args[0])
    return err or add_channel(channel)


def normalize_cookie(raw):
    """Accepts a full cookie header, a copied "cookie: ..." line, or just the token."""
    raw = raw.strip().strip("'\"")
    raw = re.sub(r"^(-H\s+)?['\"]?cookie:\s*", "", raw, flags=re.I).strip("'\" ")
    if re.fullmatch(r"[0-9a-fA-F]{32,}", raw):
        return f"achroma-chat={raw}"
    return raw if "achroma-chat=" in raw else None


def setup_cookie():
    print("Paste your session cookie: the whole cookie header, or just the achroma-chat value.")
    print("Leave it empty to sign in with your username and password instead.")
    for _ in range(3):
        raw = getpass.getpass("Cookie (hidden): ").strip()
        if not raw:
            break
        cookie = normalize_cookie(raw)
        if cookie:
            set_full_cookie(cookie)
            print("Cookie accepted")
            return
        print("No achroma-chat cookie found in that, try again or leave it empty to sign in")
    ok, _ = sign_in("Sign in to create a session")
    if not ok:
        print("No session yet, the bot will ask again once it starts polling")


def first_run_setup():
    """Creates config.json and secrets.json when they are missing and asks for what the bot needs."""
    global TARGET_USER
    need_user = CONFIG_MISSING
    need_cookie = not CONFIG["cookie"]
    need_key = SECRETS_MISSING and not NEEDS_MIGRATION and not get_ai_key()
    if not (need_user or need_cookie or need_key):
        return

    print("\n=== First time setup ===")
    if CONFIG_MISSING:
        print("config.json not found, creating it")
    if SECRETS_MISSING:
        print("secrets.json not found, creating it")
    try:
        if need_user:
            name = input(f"Your bikesense username [{TARGET_USER}]: ").strip().lower().lstrip("@")
            if name and name != TARGET_USER:
                CONFIG["accounts"].pop(TARGET_USER, None)
                TARGET_USER = name
                CONFIG["target_user"] = name
                PROFILE["username"] = name
        if need_cookie:
            setup_cookie()
        if need_key:
            key = getpass.getpass("Gemini API key for ?ai (optional, leave empty to skip): ").strip()
            if key:
                CONFIG["gemini_api_key"] = key
    except (EOFError, KeyboardInterrupt):
        print("\nSetup skipped, you can finish it later")
    save_config()
    print("Saved config.json and secrets.json\n")


def main():
    first_run_setup()
    # Baseline: ignore everything that already exists when we start
    for ch in list(CHANNELS):
        try:
            poll_channel(ch)
        except requests.HTTPError as e:
            warn_channel(ch, e)
    print(f"Started. Watching {', '.join(CHANNELS)}. Commands run for {TARGET_USER}.")
    print("Terminal commands are on: type help, accounts, switch <name>, use <channel>, quit")

    while True:
        try:
            for ch in list(CHANNELS):
                try:
                    poll_channel(ch)
                except requests.HTTPError as e:
                    if e.response is not None and e.response.status_code in (403, 404):
                        warn_channel(ch, e)
                        continue
                    raise
            poll_terminal(POLL_INTERVAL)  # replaces the sleep and runs terminal commands
        except requests.RequestException as e:
            print(f"Request error: {e}")
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            print("Stopped.")
            break


if __name__ == "__main__":
    main()
