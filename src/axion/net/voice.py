"""Voice channels: join, leave, and a background keepalive that holds the connection open.

The site identifies a voice connection by a random 20 character "client" id that we make up on
every join. The keepalive repeats the join request with that same id every few seconds. Only the
join and leave requests are known, so if the browser does something else to stay connected (a
separate heartbeat request, say), set "voice": {"keepalive_url": ...} in config.json."""
import random
import string
import threading
import time

import requests

from axion.constants import VOICE_JOIN_URL, VOICE_LEAVE_URL, VOICE_STATE_URL
from axion.state import CONFIG
from axion.ui import print_warning, r_err, r_info, r_ok, r_warn
from axion.utils.fmt import fmt_duration
from axion.utils.users import username_for_id

from .http import HEADERS, session

LOST_CODES = (401, 403, 404, 410)  # the site no longer accepts this connection, retrying won't help
STATUS = {"channel": None, "client": None, "since": 0.0, "stop": None, "thread": None,
          "muted": False, "deafened": False, "peers": []}


def new_client_id():
    return "".join(random.choices(string.digits + string.ascii_lowercase, k=20))


def connected():
    return STATUS["channel"] is not None


def _payload(channel, client):
    return {"channel": channel, "client": client, "muted": STATUS["muted"], "deafened": STATUS["deafened"]}


def read_peers(resp):
    """The join answer lists who is in the room: {"ok": true, "peers": [{"id": 1, "client": "..."}], "ice": [...]}.
    Only the peer list is kept. The "ice" part holds temporary TURN credentials, which are never stored or shown."""
    try:
        peers = resp.json().get("peers")
    except (ValueError, AttributeError):
        return None
    return [p for p in peers if isinstance(p, dict) and "id" in p] if isinstance(peers, list) else None


def peer_names(peers):
    names = []
    for p in peers:
        name = username_for_id(p["id"])
        names.append(f"@{name}" if name else f"user {p['id']}")
    return ", ".join(names)


def _explain(code, text):
    return {
        401: "The site rejected your session (401)",
        403: "The site refused the join (403)" + (f": {text.strip()[:150]}" if text.strip() else " with no explanation"),
        404: "No voice channel with that name (404)",
        429: "Slow down, the site is rate limiting you (429)",
    }.get(code, f"Voice request failed ({code}): {text[:120]}")


def _keepalive(stop, channel, client):
    sess = requests.Session()  # own session, never shared with the main thread
    sess.headers.update(HEADERS)
    fails = 0
    while not stop.wait(CONFIG["voice"]["keepalive_interval"]):
        url = CONFIG["voice"]["keepalive_url"]
        body = _payload(channel, client) if url == VOICE_JOIN_URL else {"channel": channel, "client": client}
        sess.headers["cookie"] = HEADERS["cookie"]
        try:
            r = sess.post(url, json=body, timeout=10)
            code = r.status_code
        except requests.RequestException:
            code = None
        if code is not None and code < 400:
            fails = 0
            peers = read_peers(r)
            if peers is not None and STATUS["client"] == client:
                STATUS["peers"] = peers
            continue
        if code in LOST_CODES:
            print_warning(f"Lost the voice connection to {channel} ({code}), not retrying. Join again with the vc command")
            if STATUS["client"] == client:
                STATUS.update(channel=None, client=None, thread=None, stop=None)
            return
        fails += 1
        if fails == 3:  # said once, it keeps trying quietly
            print_warning(f"Trouble keeping {channel} alive ({code or 'network error'}), still trying")


def join(channel):
    """Joins a voice channel and keeps the connection alive. Returns a Reply."""
    if connected():
        disconnect()  # one voice channel at a time
    client = new_client_id()
    STATUS.update(muted=False, deafened=False)
    try:
        r = session.post(VOICE_JOIN_URL, json=_payload(channel, client), timeout=15)
    except requests.RequestException as e:
        return r_err(f"Couldn't reach the site: {e}")
    if r.status_code >= 400:
        print_warning(f"Voice join to {channel} was refused: {r.status_code} {r.text.strip()[:300]}")  # the full answer, to see what the site wants
        return r_err(_explain(r.status_code, r.text))
    stop = threading.Event()
    thread = threading.Thread(target=_keepalive, args=(stop, channel, client), daemon=True)
    peers = read_peers(r) or []
    STATUS.update(channel=channel, client=client, since=time.time(), stop=stop, thread=thread, peers=peers)
    thread.start()
    every = CONFIG["voice"]["keepalive_interval"]
    room = f"\n👥 In the room: {len(peers)} ({peer_names(peers)})" if peers else "\n👥 Nobody else is in the room"
    return r_ok(f"Joined {channel}\nStaying connected, keepalive every {every}s{room}", emoji="🎙️")


def set_state(**flags):
    """Mutes or deafens: set_state(muted=True). Only the flags given change. Returns a Reply."""
    if not connected():
        return r_warn("Not in a voice channel")
    new = {**{k: STATUS[k] for k in ("muted", "deafened")}, **flags}
    try:
        r = session.post(VOICE_STATE_URL, json=new, timeout=15)
    except requests.RequestException as e:
        return r_err(f"Couldn't reach the site: {e}")
    if r.status_code >= 400:
        return r_err(_explain(r.status_code, r.text))
    STATUS.update(new)  # the keepalive sends these too, so they stick
    parts = [("🔇 Muted" if new["muted"] else "🎤 Unmuted"), ("🔕 Deafened" if new["deafened"] else "🔔 Not deafened")]
    return r_ok(" · ".join(parts), emoji="🎙️")


def leave():
    """Leaves the current voice channel. Returns a Reply."""
    if not connected():
        return r_warn("Not in a voice channel")
    channel, client = STATUS["channel"], STATUS["client"]
    stop, thread = STATUS["stop"], STATUS["thread"]
    stop.set()
    if thread is not None:
        thread.join(timeout=12)  # so a keepalive can't re-join after we leave
    STATUS.update(channel=None, client=None, thread=None, stop=None, peers=[])
    try:
        r = session.post(VOICE_LEAVE_URL, json={"client": client}, timeout=10)
    except requests.RequestException as e:
        return r_warn(f"Stopped the keepalive for {channel}, but the leave request failed: {e}")
    if r.status_code >= 400:
        return r_warn(f"Stopped the keepalive for {channel}, but the site answered {r.status_code}")
    return r_ok(f"Left {channel}", emoji="👋")


def disconnect():
    """Leaves quietly if connected. Used when switching accounts and when the bot stops."""
    if connected():
        leave()


def status():
    if not connected():
        return r_info("Not in a voice channel", emoji="🎙️")
    peers = STATUS["peers"]
    room = f"\n👥 In the room: {len(peers)} ({peer_names(peers)})" if peers else "\n👥 Nobody else is in the room"
    mic = ("🔇 muted" if STATUS["muted"] else "🎤 unmuted") + ", " + ("🔕 deafened" if STATUS["deafened"] else "🔔 not deafened")
    return r_info(
        f"In voice: {STATUS['channel']}\nConnected for {fmt_duration(time.time() - STATUS['since'])}\n{mic}{room}",
        emoji="🎙️",
    )
