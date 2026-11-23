"""The prompt and the raw-mode line editor, so bot output never corrupts what you are typing."""
import atexit
import codecs
import os
import re
import select
import sys
import time
from contextlib import contextmanager

from axion.state import STATE, cookie, target_user

from .theme import ANSI_OK, C_BRAND, C_ERR, C_HOST, C_TEXT, C_USER, OUT_LOCK, erase_line, paint, term_width


# ----- prompt -----
def prompt_parts():
    signed_in = "achroma-chat=" in cookie()
    user = target_user() if signed_in and target_user() else "guest"
    channel = STATE["channel"]
    return user, ("DM" if channel.startswith("dm-") else channel)


def prompt_plain():
    user, chan = prompt_parts()
    return f"axion@{user}:{chan}{'' if STATE['online'] else '!'}$ "


def prompt_colored():
    user, chan = prompt_parts()
    mark = "" if STATE["online"] else paint("!", C_ERR, bold=True)  # ! means the connection is down
    return (
        paint("axion", C_BRAND, bold=True) + paint(f"@{user}", C_USER) + paint(f":{chan}", C_HOST)
        + mark + paint("$", C_TEXT, bold=True) + " "
    )


class LineEditor:
    """Raw mode single line editor. Output from other threads redraws the prompt and whatever
    you have typed, so incoming bot activity never corrupts the command line.
    It is only used on real ANSI terminals, everything else falls back to plain reading."""

    def __init__(self):
        self.enabled = False  # set by setup()
        self.active = False  # raw mode on and the prompt is showing
        self.buf = ""
        self.history = []
        self.hpos = None
        self.draft = ""
        self.pending = ""  # an unfinished escape sequence such as an arrow key
        self.saved = None
        self.decoder = None
        self.win = False

    def setup(self):
        # Without ANSI only Windows uses the editor (its plain input path cannot read a console),
        # drawing with spaces instead of escape codes. Elsewhere plain reading works fine.
        if not ANSI_OK and os.name != "nt":
            return
        try:
            if not sys.stdin.isatty():
                return
            if os.name == "nt":
                import msvcrt  # noqa: F401
                self.win = True
            else:
                import termios
                termios.tcgetattr(sys.stdin.fileno())
                self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        except Exception:
            return
        self.enabled = True
        atexit.register(self.shutdown)

    def start(self):
        if not self.enabled or self.active:
            return
        if not self.win:
            import termios
            import tty
            fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(fd)
            tty.setcbreak(fd)  # no echo and no line buffering, Ctrl+C still works
        self.active = True
        self.draw()

    def stop(self, erase=True):
        if not self.active:
            return
        with OUT_LOCK:
            if erase:
                sys.stdout.write(erase_line())
                sys.stdout.flush()
            if not self.win and self.saved is not None:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved)
            self.active = False

    def shutdown(self):
        try:
            self.stop(erase=False)
        except Exception:
            pass

    @contextmanager
    def cooked(self):
        """Normal terminal mode for input() and getpass(), the prompt comes back afterwards."""
        was_active = self.active
        if was_active:
            self.stop()
        try:
            yield
        finally:
            if was_active:
                self.start()

    def draw(self):
        with OUT_LOCK:
            room = max(5, term_width() - len(prompt_plain()) - 1)
            sys.stdout.write(erase_line() + prompt_colored() + paint(self.buf[-room:], C_TEXT))
            sys.stdout.flush()

    def commit(self, line):
        """Leaves the typed command on screen and returns to normal mode so it can run."""
        with OUT_LOCK:
            sys.stdout.write(erase_line() + prompt_colored() + paint(line, C_TEXT) + "\n")
            sys.stdout.flush()
        self.stop(erase=False)

    def _remember(self, line):
        if line.strip() and (not self.history or self.history[-1] != line):
            self.history.append(line)
        self.hpos = None

    def _escape(self, seq):
        if seq[-1] == "A" and self.history:  # up
            if self.hpos is None:
                self.draft = self.buf
                self.hpos = len(self.history)
            self.hpos = max(0, self.hpos - 1)
            self.buf = self.history[self.hpos]
        elif seq[-1] == "B" and self.hpos is not None:  # down
            self.hpos += 1
            if self.hpos >= len(self.history):
                self.hpos = None
                self.buf = self.draft
            else:
                self.buf = self.history[self.hpos]

    def feed(self, text):
        """Applies typed characters. Returns the lines that were completed with Enter."""
        done = []
        for ch in text:
            if self.pending:
                if self.pending == "\x1b":
                    if ch in "[O":
                        self.pending += ch
                        continue
                    self.pending = ""  # a lone ESC, treat ch as a normal key below
                else:
                    self.pending += ch
                    if "@" <= ch <= "~":  # last byte of the escape sequence
                        self._escape(self.pending)
                        self.pending = ""
                    continue
            if ch == "\x1b":
                self.pending = ch
            elif ch in "\r\n":
                done.append(self.buf)
                self._remember(self.buf)
                self.buf = ""
            elif ch in ("\x7f", "\b"):
                self.buf = self.buf[:-1]
            elif ch == "\x03":
                raise KeyboardInterrupt
            elif ch == "\x04":
                if not self.buf:
                    raise KeyboardInterrupt
            elif ch == "\x15":  # Ctrl+U
                self.buf = ""
            elif ch == "\x17":  # Ctrl+W
                self.buf = re.sub(r"\S+\s*$", "", self.buf)
            elif ch >= " ":
                self.buf += ch
        if self.active and not done:
            self.draw()
        return done

    def read(self, timeout):
        """Waits up to timeout seconds for typing. Returns the lines completed meanwhile."""
        if self.win:
            import msvcrt
            end = time.time() + timeout
            lines = []
            while True:
                while msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):  # arrow keys come as two characters
                        ch = {"H": "\x1b[A", "P": "\x1b[B"}.get(msvcrt.getwch(), "")
                    lines += self.feed(ch)
                if lines or time.time() >= end:
                    return lines
                time.sleep(0.02)
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return []
        data = os.read(sys.stdin.fileno(), 1024)
        if not data:
            raise EOFError
        return self.feed(self.decoder.decode(data))


EDITOR = LineEditor()
