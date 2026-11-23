"""Background loops for the typing indicator and for cancelling it ("silent typing")."""
import threading

import requests

from axion.constants import TYPING_URL
from axion.state import CHANNELS, CONFIG, STATE
from axion.ui import print_info, print_warning

from .http import HEADERS

TYPING_INTERVAL = CONFIG["typing_interval"]  # seconds between typing pings, lower it if the indicator flickers

# Silent typing: spams a "stop typing" request to cancel your own typing indicator.
# I do not know the real stop request, so the config default is a GUESS. Capture the
# curl the site sends when you stop typing and fix "silent_typing" in config.json.
SILENT_METHOD = CONFIG["silent_typing"]["method"]
SILENT_URL = CONFIG["silent_typing"]["url"]
SILENT_PAYLOAD = CONFIG["silent_typing"]["payload"]
SILENT_INTERVAL = CONFIG["silent_typing"]["interval"]  # seconds between cancel requests

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
            print_warning(f"Typing error: {e}")
        typing_stop.wait(TYPING_INTERVAL)


def set_typing(on, channel=None):
    global typing_thread
    if on:
        STATE["typing_channel"] = channel or STATE["channel"]
        if typing_thread and typing_thread.is_alive():
            print_info(f"Typing now in {STATE['typing_channel']}")
            return
        typing_stop.clear()
        typing_thread = threading.Thread(target=typing_loop, daemon=True)
        typing_thread.start()
        print_info(f"Typing ON in {STATE['typing_channel']}")
    else:
        typing_stop.set()
        print_info("Typing OFF")


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
                    print_warning(f"Silent typing request returned {r.status_code}, the guessed request is probably wrong")
                    warned = True
        except requests.RequestException as e:
            if not warned:
                print_warning(f"Silent typing error: {e}")
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
        print_info("Silent typing ON")
    else:
        silent_stop.set()
        print_info("Silent typing OFF")

