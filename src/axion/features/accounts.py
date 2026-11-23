"""Accounts: signing in, signing up, quick accounts, switching and the first-run setup."""
import random
import re
import string
import uuid

import requests

from axion.config import save_config
from axion.constants import SIGNIN_URL, SIGNUP_URL
from axion.net.http import anon_session, fetch_messages, set_full_cookie, session
from axion.net import voice
from axion.net.indicators import set_silent, set_typing
from axion.state import (
    CONFIG, CONFIG_MISSING, NEEDS_MIGRATION, PROFILE, SECRETS_MISSING, STATE, cookie, prefix, target_user,
)
from axion.ui import (
    ask, print_dim, print_error, print_header, print_info, print_kv, print_success, print_warning,
    r_err, r_ok, r_warn, spin,
)

from .ai import get_ai_key

QUICKACC_USAGE = "quickacc [-u <username>] [-c <password>]"


def adopt_cookie(token):
    """Swaps a new login token into the running bot and saves it to secrets.json."""
    parts = [p for p in cookie().split("; ") if p and not p.startswith("achroma-chat=")]
    parts.append(f"achroma-chat={token}")
    set_full_cookie("; ".join(parts))
    save_config()


def login_with(username, password):
    """Posts the signin request. On success that account becomes the active one and is
    saved under accounts. Returns (ok, message for chat)."""
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
        with spin("Signing in"):
            r = s.post(SIGNIN_URL, json=payload, timeout=15)
    except requests.RequestException as e:
        print_error(f"Sign in request failed: {e}")
        return False, "Sign in failed, check the terminal"

    if r.status_code >= 400:
        print_error(f"Sign in failed ({r.status_code}): {r.text[:120]}")
        return False, f"Sign in failed ({r.status_code}), check the terminal"

    token = next((c.value for c in s.cookies if c.name == "achroma-chat"), None)
    if not token:
        print_warning("Signed in, but the response did not set an achroma-chat cookie")
        return False, "Signed in, but no session cookie came back, check the terminal"

    if username.lower() != target_user():
        # The bot now acts as this account, so recognize its commands instead
        save_config()  # stores the account we are leaving
        set_typing(False)
        set_silent(False)
        voice.disconnect()
        saved = CONFIG["accounts"].get(username.lower(), {}).get("profile")
        PROFILE.clear()
        PROFILE.update(saved or {"display_name": "", "username": username, "bio": ""})
        CONFIG["target_user"] = username.lower()
        print_info(f"Now acting as {username}")
    adopt_cookie(token)
    print_success(f"Signed in as {username}. Session saved to secrets.json")
    return True, "Signed in, session updated"


def sign_in(reason=None):
    """Asks for the password in the terminal, signs in, and continues with the new session.
    Returns (ok, message for chat)."""
    print_header("Sign in")
    print_info(reason or "Sign in to refresh the session")
    print_dim("Leave the password empty to cancel")
    try:
        username = ask("Username", default=target_user())
        password = ask("Password", secret=True)
        if not password:
            print_warning("Cancelled")
            return False, "Sign in cancelled"
    except (EOFError, KeyboardInterrupt):
        print_warning("Cancelled")
        return False, "Sign in cancelled"

    return login_with(username, password)


def parse_quickacc(args):
    """Reads -u and -c in any order. Returns (username, password, error). A missing value stays None."""
    username = password = None
    i = 0
    while i < len(args):
        flag = args[i].lower()
        if flag in ("-u", "-c") and i + 1 < len(args):
            value = args[i + 1]
            if flag == "-u":
                username = value.lstrip("@")
            else:
                password = value
            i += 2
        else:
            return None, None, f"Usage: {QUICKACC_USAGE}"
    if username is not None and not re.fullmatch(r"\S{1,32}", username):
        return None, None, "Usernames can't contain spaces and are at most 32 characters"
    return username, password, None


def quick_account(args):
    """Creates an account, signs in as it, and saves it to the accounts list. The username is random
    (10 letters) unless -u sets one. The password comes from secrets.json unless -c sets one."""
    custom_name, custom_pass, error = parse_quickacc(args)
    if error:
        print_warning(error)
        return
    password = custom_pass or CONFIG["quickacc_password"]
    if not password:
        print_error("No default password set. Use quickacc -c <password>, or set quickacc_password in secrets.json")
        return

    s = anon_session()  # no login cookie, so the signup is not tied to the active account
    username = None
    with spin("Creating account"):
        for _ in range(1 if custom_name else 5):  # a chosen name gets one try, random names are re-rolled
            candidate = custom_name or "".join(random.choices(string.ascii_lowercase, k=10))
            payload = {"username": candidate, "password": password, "device": CONFIG["device"]}
            try:
                r = s.post(SIGNUP_URL, json=payload, timeout=15)
            except requests.RequestException as e:
                print_error(f"Signup request failed: {e}")
                return
            taken = r.status_code == 409 or (
                r.status_code == 400 and any(w in r.text.lower() for w in ("taken", "exist", "already"))
            )
            if taken:
                if custom_name:
                    print_error(f"The username {custom_name} is already taken, pick another one with -u")
                    return
                continue  # unlucky name, roll another
            if r.status_code >= 400:
                print_error(f"Signup failed ({r.status_code}): {r.text[:120]}")
                return
            username = candidate
            break
    if not username:
        print_error("Could not find a free username after 5 tries")
        return

    print_success(f"Created account {username}")
    print_kv([
        ("Username", username + (" (chosen with -u)" if custom_name else " (random)")),
        ("Password", "the one you typed" if custom_pass else "default from secrets.json"),
    ])
    ok, _ = login_with(username, password)
    if ok:
        print_info("Saved to your accounts, change accounts with: switch <name>")
    else:
        print_error("The account exists but sign in failed. Use addaccount with its username and password.")


def signup_account():
    """Asks for a username and password in the terminal, then fires one signup request.
    The signup uses a fresh session without your login cookie, so it is a clean new account.
    Returns the message for chat."""
    print_header("Sign up")
    print_dim("Leave the username empty to cancel")
    try:
        username = ask("Username")
        if not username:
            print_warning("Cancelled")
            return r_warn("Account creation cancelled")
        password = ask("Password", secret=True)
        if not password:
            print_warning("Cancelled")
            return r_warn("Account creation cancelled")
    except (EOFError, KeyboardInterrupt):
        print_warning("Cancelled")
        return r_warn("Account creation cancelled")

    s = anon_session()  # no login cookie, so the signup is not tied to your main account
    payload = {"username": username, "password": password, "device": CONFIG["device"]}
    try:
        with spin("Creating account"):
            r = s.post(SIGNUP_URL, json=payload, timeout=15)
    except requests.RequestException as e:
        print_error(f"Signup request failed: {e}")
        return r_err("Account creation failed, check the terminal")

    if r.status_code >= 400:
        print_error(f"Signup failed ({r.status_code}): {r.text[:120]}")
        return r_err(f"Account creation failed ({r.status_code}), check the terminal")

    print_success(f"Account {username} created")
    print_dim("Sign in to it with: addaccount")
    return r_ok("Account created, check the terminal")


def apply_account(key):
    """Makes a saved account the active one, in memory and on disk."""
    acc = CONFIG["accounts"][key]
    set_typing(False)
    set_silent(False)
    voice.disconnect()
    CONFIG["target_user"] = key
    set_full_cookie(acc["cookie"])
    PROFILE.clear()
    PROFILE.update(acc.get("profile") or {"display_name": "", "username": key, "bio": ""})


def switch_account(name):
    key = name.lower().lstrip("@")
    if key not in CONFIG["accounts"]:
        return r_err(f"No saved account named {key}. Use accounts to list them or addaccount to add one.")
    if key == target_user():
        return r_warn(f"Already acting as {key}")
    save_config()  # stores the current account first, including a refreshed cookie
    previous = target_user()
    apply_account(key)
    try:
        with spin("Checking session"):
            fetch_messages()  # checks the cookie, and offers a terminal sign in on a 401
    except SystemExit:
        apply_account(previous)
        save_config()
        return r_err(f"Could not switch to {key}, staying on {previous}")
    except requests.RequestException as e:
        save_config()
        return r_warn(f"Now acting as {target_user()}, but the check request failed: {e}")
    save_config()
    return r_ok(f"Now acting as {target_user()}")


def remove_account(name):
    key = name.lower().lstrip("@")
    if key == target_user():
        return r_err("Can't remove the active account, switch to another one first")
    if CONFIG["accounts"].pop(key, None) is None:
        return r_err(f"No saved account named {key}")
    save_config()
    return r_ok(f"Removed {key}")


def normalize_cookie(raw):
    """Accepts a full cookie header, a copied "cookie: ..." line, or just the token."""
    raw = raw.strip().strip("'\"")
    raw = re.sub(r"^(-H\s+)?['\"]?cookie:\s*", "", raw, flags=re.I).strip("'\" ")
    if re.fullmatch(r"[0-9a-fA-F]{32,}", raw):
        return f"achroma-chat={raw}"
    return raw if "achroma-chat=" in raw else None


def setup_cookie():
    print_info("Paste your session cookie: the whole cookie header, or just the achroma-chat value")
    print_dim("Leave it empty to sign in with your username and password instead")
    for _ in range(3):
        raw = ask("Cookie (hidden)", secret=True)
        if not raw:
            break
        cookie_value = normalize_cookie(raw)
        if cookie_value:
            set_full_cookie(cookie_value)
            print_success("Cookie accepted")
            return
        print_warning("No achroma-chat cookie found in that, try again or leave it empty to sign in")
    ok, _ = sign_in("Sign in to create a session")
    if not ok:
        print_warning("No session yet, the bot will ask again once it starts polling")


def first_run_setup():
    """Creates config.json and secrets.json when they are missing and asks for what the bot needs."""
    need_user = CONFIG_MISSING
    need_cookie = not CONFIG["cookie"]
    need_key = SECRETS_MISSING and not NEEDS_MIGRATION and not get_ai_key()
    if not (need_user or need_cookie or need_key):
        return

    print_header("First time setup")
    if CONFIG_MISSING:
        print_info("config.json not found, creating it")
    if SECRETS_MISSING:
        print_info("secrets.json not found, creating it")
    try:
        if need_user:
            name = ask("Your bikesense username", default=target_user()).lower().lstrip("@")
            if name != target_user():
                CONFIG["accounts"].pop(target_user(), None)
                CONFIG["target_user"] = name
                PROFILE["username"] = name
        if need_cookie:
            setup_cookie()
        if need_key:
            key = ask("Gemini API key for ?ai (optional, leave empty to skip)", secret=True)
            if key:
                CONFIG["gemini_api_key"] = key
    except (EOFError, KeyboardInterrupt):
        print_warning("Setup skipped, you can finish it later")
    save_config()
    print_success("Saved config.json and secrets.json")
