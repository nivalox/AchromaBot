"""Polling the watched channels and handing new messages to the dispatcher.

Fetching happens in a background thread (Fetcher), everything else in the main thread. That way a slow
request never freezes the prompt: keys keep echoing while the network is busy."""
import queue
import threading

import requests

from .dispatcher import handle_message
from .config import save_config
from .features.autoreact import auto_react
from .features.snipe import track_deletions
from .net.http import HEADERS, Unauthorized, fetch_messages, fetch_raw, reauthenticate
from .state import CHANNELS, CONFIG, LAST_ID, STATE
from .ui import print_success, print_warning


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


def handle_fetched(ch, msgs, rtt):
    """Handles one fetched channel. The first result for a channel only sets the baseline."""
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


def poll_channel(ch):
    """Fetches one channel right now (main thread) and handles it. Used for baselines and ?channel add."""
    msgs, rtt = fetch_messages(ch)
    handle_fetched(ch, msgs, rtt)


class Fetcher:
    """Fetches every watched channel in a loop on its own thread, with its own session.
    Results wait in a queue and the main thread handles them with drain()."""

    def __init__(self, interval):
        self.interval = interval
        self.results = queue.Queue()
        self.stop_event = threading.Event()
        self.resume = threading.Event()  # set by the main thread after it dealt with a 401
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.resume.set()

    def _run(self):
        sess = requests.Session()
        sess.headers.update(HEADERS)
        pause = self.interval
        while not self.stop_event.is_set():
            pause = self.interval
            for ch in list(CHANNELS):
                if self.stop_event.is_set():
                    return
                sess.headers["cookie"] = HEADERS["cookie"]  # follows account switches and new sign ins
                try:
                    msgs, rtt = fetch_raw(sess, ch)
                    self.results.put(("ok", ch, msgs, rtt))
                except Unauthorized:
                    self.resume.clear()
                    self.results.put(("401", ch))
                    self.resume.wait()  # the main thread signs in, then sets this
                    break
                except requests.HTTPError as e:
                    code = e.response.status_code if e.response is not None else None
                    self.results.put(("http", ch, e))
                    if code not in (403, 404):
                        pause = 5
                        break
                except requests.RequestException as e:
                    self.results.put(("net", ch, e))
                    pause = 5
                    break
            self.stop_event.wait(pause)

    def drain(self):
        """Handles everything the thread has fetched so far. Runs in the main thread."""
        while True:
            try:
                item = self.results.get_nowait()
            except queue.Empty:
                return
            kind, ch = item[0], item[1]
            if kind == "ok":
                if not STATE["online"]:
                    STATE["online"] = True
                    print_success("Connection restored")
                if ch in CHANNELS:  # a removed channel can still have a result in flight
                    handle_fetched(ch, item[2], item[3])
            elif kind == "401":
                reauthenticate()  # raises SystemExit when nobody signs in
                self.resume.set()
            elif kind == "http":
                err = item[2]
                code = err.response.status_code if err.response is not None else None
                if code in (403, 404):
                    warn_channel(ch, err)
                else:
                    self._offline(err)
            elif kind == "net":
                self._offline(item[2])

    @staticmethod
    def _offline(err):
        if STATE["online"]:
            STATE["online"] = False
            print_warning(f"Connection problem: {err}. Retrying every 5s")


def warn_channel(ch, err):
    if ch not in STATE["warned"]:
        STATE["warned"].add(ch)
        code = err.response.status_code if err.response is not None else "?"
        print_warning(f"Cannot read channel {ch} ({code}), will keep retrying quietly")
