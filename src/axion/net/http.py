"""Talking to the chat site: headers, the shared session, reading and sending messages."""
import time

import requests

from axion.constants import BASE
from axion.state import CONFIG, STATE, cookie
from axion.ui import print_error, print_warning

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US",
    "cookie": cookie(),
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


def anon_session():
    """A fresh session without your login cookie, like the browser has before signing in."""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["cookie"] = "; ".join(
        p for p in cookie().split("; ") if p and not p.startswith("achroma-chat=")
    )
    return s


def set_full_cookie(full_cookie):
    """Makes a full cookie string the active one, in memory only."""
    CONFIG["cookie"] = full_cookie
    HEADERS["cookie"] = full_cookie
    session.headers["cookie"] = full_cookie


class Unauthorized(Exception):
    """The site rejected the session cookie (401)."""


def fetch_raw(sess, channel):
    """One fetch with the given session. Returns (messages, round_trip_ms). Never prompts, so it is
    safe in a background thread. Raises Unauthorized on a 401 and requests.HTTPError on other errors."""
    start = time.perf_counter()
    r = sess.get(BASE, params={"channel": channel}, timeout=15)
    rtt = (time.perf_counter() - start) * 1000
    if r.status_code == 401:
        raise Unauthorized()
    r.raise_for_status()
    return r.json().get("messages", []), rtt


def reauthenticate():
    """Offers a terminal sign in after a 401. Returns True when a new session is active,
    otherwise raises SystemExit with a message for the person."""
    from axion.features.accounts import sign_in  # lazy: accounts imports this module
    ok, _ = sign_in("The site rejected your session cookie (401). Sign in to get a new one.")
    if ok:
        return True
    raise SystemExit(
        "401 Unauthorized: the site rejected your cookie and no new sign in happened. "
        "Run the script again to sign in, or paste a fresh cookie into secrets.json."
    )


def fetch_messages(channel=None, retry=True):
    """Returns (messages, round_trip_ms) using the main session. On a 401 it offers a terminal
    sign in and retries once."""
    channel = channel or STATE["channel"]
    try:
        return fetch_raw(session, channel)
    except Unauthorized:
        if retry:
            reauthenticate()
            return fetch_messages(channel, retry=False)
        raise SystemExit(
            "401 Unauthorized: the site rejected your cookie and no new sign in happened. "
            "Run the script again to sign in, or paste a fresh cookie into secrets.json."
        )


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
            print_error(f"Could not send message: {e}")
            return last
        if r.status_code >= 400:
            print_error(f"Could not send message to {channel} ({r.status_code}): {r.text[:150]}")
            if r.status_code in (400, 413, 422):
                print_warning("If the message was too long, lower max_message_length in config.json")
            return last
        last = r
    return last
