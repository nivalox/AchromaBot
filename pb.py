import getpass
import json
import os
from collections import deque
import platform
import re
import select
import shutil
import sys
import subprocess
import threading
import time
import uuid
import requests

START_TIME = time.time()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEFAULTS = {
    "cookie": "",
    "channel": "general",
    "target_user": "nivalos",
    "poll_interval": 0.5,
    "typing_interval": 3,
    "auto_reply": True,
    "silent_typing": {
        "method": "DELETE",
        "url": "https://bikesense.org/api/chat/typing",
        "payload": {"channel": "general"},
        "interval": 0.3,
    },
    "profile": {"display_name": "", "username": "", "bio": ""},
    "autoreact": {"enabled": False, "emoji": "\U0001F62D", "users": []},
    "device": {"tz": "America/New_York", "screen": "431x958", "platform": "Android", "touch": True},
    "fingerprint": "",
    "accounts": {},
}


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            loaded = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"config.json not found, put it next to the script: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"config.json is not valid JSON: {e}")
    cfg = {**DEFAULTS, **loaded}
    # Merge nested sections so a partial entry still gets the other defaults
    for key in ("silent_typing", "profile", "autoreact"):
        cfg[key] = {**DEFAULTS[key], **loaded.get(key, {})}
    if not cfg["cookie"]:
        raise SystemExit("config.json has no cookie set")
    return cfg


def sync_active_account():
    """Keeps the active account's cookie and profile stored under "accounts"."""
    key = CONFIG["target_user"].lower()
    CONFIG.setdefault("accounts", {})[key] = {
        "cookie": CONFIG["cookie"],
        "profile": dict(CONFIG["profile"]),
    }


def save_config():
    sync_active_account()
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        print(f"Could not save config.json: {e}")


CONFIG = load_config()
sync_active_account()

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

HELP_TEXT = (
    "Commands:\n"
    "?ping : shows the current ping\n"
    "?typing on/off : toggles the typing indicator\n"
    "?silenttyping on/off : toggles cancelling your typing indicator\n"
    "?profile name/user/bio <text> : changes your profile (?profile show to view)\n"
    "?echo <text> : sends the text you typed\n"
    "?snipe : shows the latest deleted message\n"
    "?csnipe/?clearsnipe : clears sniped messages\n"
    "?autoreply on/off : toggles the wrong command and unauthorized replies\n"
    "?autoreact on/off : reacts to new messages (also: emoji <e>, users <names/all>)\n"
    "?signin : signs in from the terminal and refreshes the session\n"
    "?quickacc : creates an account, details are entered in the terminal\n"
    "?stats : shows phone and Termux stats\n"
    "?creds : shows credits\n"
    "?help : shows this message\n"
    "(made by nivalos in python)"
)

CREDS_TEXT = (
    "Credits:\n"
    "Made by nivalos\n"
    "Written in python, running on Termux (Android)"
)
CHANNEL = CONFIG["channel"]
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

# Session cookie from config.json. Keep that file private, it logs in as you.
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


def fetch_messages(retry=True):
    """Returns (messages, round_trip_ms). On a 401 it offers a terminal sign in and retries once."""
    start = time.perf_counter()
    r = session.get(BASE, params={"channel": CHANNEL}, timeout=15)
    rtt = (time.perf_counter() - start) * 1000
    if r.status_code == 401:
        if retry:
            ok, _ = sign_in("The site rejected your session cookie (401). Sign in to get a new one.")
            if ok:
                return fetch_messages(retry=False)
        raise SystemExit(
            "401 Unauthorized: the site rejected your cookie and no new sign in happened. "
            "Run the script again to sign in, or paste a fresh cookie into config.json."
        )
    r.raise_for_status()
    return r.json().get("messages", []), rtt


def send_message(text):
    payload = {"text": text, "channel": CHANNEL, "attachment": None, "reply_to": None}
    r = session.post(
        BASE,
        json=payload,  # sets content-type: application/json
        timeout=15,
    )
    r.raise_for_status()
    return r


typing_stop = threading.Event()
typing_thread = None


def typing_loop():
    # Own session so we never share one with the main thread
    s = requests.Session()
    s.headers.update(HEADERS)
    while not typing_stop.is_set():
        try:
            s.headers["cookie"] = HEADERS["cookie"]
            s.post(TYPING_URL, json={"channel": CHANNEL}, timeout=10)
        except requests.RequestException as e:
            print(f"Typing error: {e}")
        typing_stop.wait(TYPING_INTERVAL)


def set_typing(on):
    global typing_thread
    if on:
        if typing_thread and typing_thread.is_alive():
            return
        typing_stop.clear()
        typing_thread = threading.Thread(target=typing_loop, daemon=True)
        typing_thread.start()
        print("Typing ON")
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
            r = s.request(SILENT_METHOD, SILENT_URL, json=SILENT_PAYLOAD, timeout=10)
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


seen = {}  # id -> message, for messages currently inside the fetched window
sniped = deque(maxlen=50)  # deleted messages, newest last


def track_deletions(msgs):
    """A seen message counts as deleted if its id sits inside the current window
    but is missing from it. Ids below the window start just aged out, so they are skipped."""
    if not msgs:
        return
    current = {m["id"]: m for m in msgs}
    window_start = min(current)

    for mid, msg in list(seen.items()):
        if mid < window_start:
            del seen[mid]
        elif mid not in current:
            sniped.append({"msg": msg, "deleted_at": time.time()})
            del seen[mid]
            print(f"Deleted message caught (id {mid}) from {msg.get('username')}")

    seen.update(current)


def get_snipe():
    if not sniped:
        return "Nothing to snipe"
    rec = sniped[-1]
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
        p for p in COOKIE.split("; ") if not p.startswith("achroma-chat=")
    )
    return s


def adopt_cookie(token):
    """Swaps a new login token into the running bot and saves it to config.json."""
    global COOKIE
    parts = [p for p in COOKIE.split("; ") if not p.startswith("achroma-chat=")]
    parts.append(f"achroma-chat={token}")
    COOKIE = "; ".join(parts)
    HEADERS["cookie"] = COOKIE
    session.headers["cookie"] = COOKIE
    CONFIG["cookie"] = COOKIE
    save_config()


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
    print("[signin] Session updated and saved to config.json")
    return True, "Signed in, session updated"


def quick_account():
    """Asks for a username and password in the terminal, then fires one signup request.
    The signup uses a fresh session without your login cookie, so it is a clean new account."""
    print("\n[quickacc] Enter the new account details (leave the username empty to cancel)")
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
        print(f"[quickacc] Request error: {e}")
        return "Account creation failed, check the terminal"

    print(f"[quickacc] Status {r.status_code}: {r.text[:200]}")
    if r.status_code >= 400:
        return f"Account creation failed ({r.status_code}), check the terminal"

    new_cookie = s.cookies.get("achroma-chat")
    if new_cookie:
        print(f"[quickacc] Login cookie for the new account: achroma-chat={new_cookie}")
    return "Account created, check the terminal"


def auto_react(m):
    """Reacts to a new message with the configured emoji. Never reacts to your own messages."""
    if not AUTOREACT["enabled"]:
        return
    user = (m.get("username") or "").lower()
    if user == TARGET_USER:
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
    "?snipe", "?csnipe", "?clearsnipe", "?stats", "?creds", "?help", "?autoreply", "?autoreact", "?quickacc", "?signin", "?signing",
}
AUTOREACT = CONFIG["autoreact"]  # enabled, emoji, users (empty list means everyone)
AUTO_REPLY = CONFIG["auto_reply"]  # when False, no "isn't a command" or "not authorized" replies
UNAUTH_TEXT = "you are not authorized to use this command."


def handle_message(m, rtt, reply=None, local=False):
    global AUTO_REPLY
    reply = reply or send_message
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

    if user != TARGET_USER:
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
        set_typing(on)
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
            send_message(text)  # echo always goes to the chat
            if local:
                print("[bot] sent to chat")
        else:
            reply("Usage: ?echo <text>")
    elif cmd == "?snipe":
        reply(get_snipe())
    elif cmd in ("?csnipe", "?clearsnipe"):
        sniped.clear()
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
    elif cmd == "?quickacc":
        if not local:
            reply("Go back to the terminal to enter the account details")
        reply(quick_account())
    elif cmd == "?autoreact":
        reply(handle_autoreact(raw.split()[1:]))
    elif cmd == "?help":
        reply(HELP_TEXT + ("\n\nTerminal only:\n" + TERMINAL_HELP if local else ""))


TERMINAL_HELP = (
    "accounts : lists saved accounts\n"
    "switch <name> : switches to a saved account\n"
    "addaccount : signs in to another account and switches to it\n"
    "removeaccount <name> : forgets a saved account\n"
    "quit : stops the bot\n"
    "Every chat command also works here, with or without the ?"
)
STATE = {"rtt": 0.0, "terminal": True}


def terminal_reply(text):
    print("[bot] " + str(text).replace("\n", "\n      "))


def list_accounts():
    names = sorted(CONFIG["accounts"])
    return "\n".join(f"{'*' if n == TARGET_USER else ' '} {n}" for n in names) + "\n(* is active)"


def apply_account(key):
    """Makes a saved account the active one, in memory and in config.json."""
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
    elif cmd in ("?quit", "?exit"):
        raise KeyboardInterrupt
    else:
        # Same handler as chat, run as the active account, with replies printed here
        msg = {"id": 0, "username": TARGET_USER, "body": line}
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


def main():
    # Baseline: ignore everything that already exists when we start
    msgs, rtt = fetch_messages()
    STATE["rtt"] = rtt
    track_deletions(msgs)
    last_id = max((m["id"] for m in msgs), default=0)
    print(f"Started. Baseline message id: {last_id}. Waiting for {TRIGGER} from {TARGET_USER}...")
    print("Terminal commands are on: type help, accounts, switch <name>, quit")

    while True:
        try:
            msgs, rtt = fetch_messages()
            STATE["rtt"] = rtt
            track_deletions(msgs)
            new = sorted((m for m in msgs if m["id"] > last_id), key=lambda m: m["id"])

            for m in new:
                last_id = m["id"]
                auto_react(m)
                handle_message(m, rtt)
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
