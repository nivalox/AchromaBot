"""Terminal capabilities, colors and the small drawing helpers everything else builds on."""
import os
import re
import shutil
import sys
import threading

try:
    import colorama
except ImportError:  # colors are optional, the bot still runs without colorama
    colorama = None


def _supports_color():
    if colorama is None or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _supports_unicode():
    try:
        "╭─╮│╰╯⠋…".encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


ANSI_OK = _supports_color()
UNICODE_OK = _supports_unicode()
try:
    sys.stdout.reconfigure(errors="replace")  # never crash on a character the terminal cannot show
except (AttributeError, ValueError):
    pass

if ANSI_OK:
    if hasattr(colorama, "just_fix_windows_console"):
        colorama.just_fix_windows_console()
    else:
        colorama.init()
    C_BRAND = C_CMD = colorama.Fore.LIGHTCYAN_EX
    C_OK = C_USER = colorama.Fore.LIGHTGREEN_EX
    C_ERR = colorama.Fore.LIGHTRED_EX
    C_WARN = colorama.Fore.LIGHTYELLOW_EX
    C_INFO = colorama.Fore.LIGHTBLUE_EX
    C_DIM = colorama.Fore.LIGHTBLACK_EX
    C_HOST = colorama.Fore.LIGHTMAGENTA_EX
    C_TEXT = colorama.Fore.WHITE
    C_BOLD = colorama.Style.BRIGHT
    C_RESET = colorama.Style.RESET_ALL
else:  # no colorama or no color support: every color is empty and paint() returns the plain text
    C_BRAND = C_CMD = C_OK = C_USER = C_ERR = C_WARN = C_INFO = C_DIM = C_HOST = C_TEXT = C_BOLD = C_RESET = ""

OUT_LOCK = threading.RLock()
SPIN = {"active": False, "obj": None}
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ELLIPSIS = "…" if UNICODE_OK else "~"
RULE = "─" if UNICODE_OK else "-"


def paint(text, color="", bold=False):
    if not ANSI_OK or not (color or bold):
        return text
    return f"{C_BOLD if bold else ''}{color}{text}{C_RESET}"


def visible_len(text):
    return len(ANSI_RE.sub("", text))


def term_width():
    cols = shutil.get_terminal_size((60, 20)).columns
    return max(32, min(cols, 64))  # small phone screens stay readable, wide ones do not stretch


def erase_line():
    """Returns the characters that wipe the current terminal line. Without ANSI support
    (an old Windows console, for example) it overwrites the line with spaces instead."""
    if ANSI_OK:
        return "\r\x1b[K"
    return "\r" + " " * (term_width() - 1) + "\r"
