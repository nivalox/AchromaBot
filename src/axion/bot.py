"""Startup and the main polling loop."""
import sys

import requests

from .config import startup
from .net import voice
from .features.accounts import first_run_setup
from .poller import Fetcher, poll_channel, warn_channel
from .state import CHANNELS, CONFIG, STATE, target_user
from .terminal import poll_terminal
from .ui import EDITOR, print_banner, print_dim, print_error, print_info, print_success, print_warning, spin

POLL_INTERVAL = CONFIG["poll_interval"]  # seconds between polls
TICK = 0.05  # how often the main thread looks for typed keys and fetched messages


def main():
    startup()
    print_banner()
    first_run_setup()
    EDITOR.setup()
    # Baseline: ignore everything that already exists when we start
    with spin("Connecting"):
        for ch in list(CHANNELS):
            try:
                poll_channel(ch)
            except requests.HTTPError as e:
                warn_channel(ch, e)
            except requests.RequestException as e:
                print_warning(f"Could not reach {ch} yet ({e}), will keep trying")
    print_success(f"Connected. Watching {', '.join(CHANNELS)}")
    print_dim(f"Commands run for {target_user()}. Type help for the command list, quit to stop.")

    fetcher = Fetcher(POLL_INTERVAL)
    fetcher.start()
    try:
        while True:
            fetcher.drain()
            poll_terminal(TICK)  # waits for keys, so typing is handled as soon as it happens
    except KeyboardInterrupt:
        pass
    finally:
        fetcher.stop()
        voice.disconnect()  # leave the voice channel properly instead of just vanishing
        EDITOR.stop()
    print_info("Stopped")


def run():
    try:
        main()
    except SystemExit as e:
        if isinstance(e.code, str):  # a message such as the rejected cookie
            print_error(e.code)
            sys.exit(1)
        raise
