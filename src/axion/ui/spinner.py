"""Spinner for slow operations, plus the helpers that ask the person at the terminal a question."""
import getpass
import sys
import threading
from contextlib import contextmanager

from .editor import EDITOR
from .output import print_dim
from .theme import ANSI_OK, C_BRAND, C_DIM, OUT_LOCK, SPIN, UNICODE_OK, paint


class Spinner:
    """A small animated indicator for slow operations. Prompts pause it, output redraws around it."""

    def __init__(self, label):
        self.label = label
        self.animated = False
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        self.animated = ANSI_OK and not EDITOR.active and SPIN["obj"] is None
        if self.animated:
            SPIN["obj"] = self
            self.resume()
        else:
            print_dim(f"{self.label}...")
        return self

    def __exit__(self, *exc):
        if self.animated:
            self.pause()
            SPIN["obj"] = None
        return False

    def resume(self):
        if not self.animated:
            return
        self._stop.clear()
        SPIN["active"] = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        if not self.animated or self._thread is None:
            return
        self._stop.set()
        self._thread.join()
        self._thread = None
        with OUT_LOCK:
            SPIN["active"] = False
            sys.stdout.write("\r\x1b[K")
            sys.stdout.flush()

    def _run(self):
        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if UNICODE_OK else "|/-\\"
        i = 0
        while not self._stop.is_set():
            with OUT_LOCK:
                sys.stdout.write(
                    "\r\x1b[K" + paint(frames[i % len(frames)], C_BRAND) + " " + paint(self.label + "...", C_DIM)
                )
                sys.stdout.flush()
            i += 1
            self._stop.wait(0.1)


def spin(label):
    return Spinner(label)


@contextmanager
def prompting():
    """Pauses the spinner and the line editor while the user answers a question."""
    sp = SPIN["obj"]
    if sp:
        sp.pause()
    try:
        with EDITOR.cooked():
            yield
    finally:
        if sp:
            sp.resume()


def ask(label, default="", secret=False):
    """Asks in the terminal. Returns the default for an empty answer. Raises EOFError or
    KeyboardInterrupt like input() does."""
    hint = paint(f" [{default}]", C_DIM) if default else ""
    prompt = f"{paint('?', C_BRAND, bold=True)} {label}{hint}: "
    with prompting():
        value = getpass.getpass(prompt) if secret else input(prompt)
    return value.strip() or default
