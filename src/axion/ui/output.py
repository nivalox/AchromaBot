"""Everything the terminal prints goes through here, so the look stays consistent.
Also holds Reply, the small str subclass commands use to answer both in chat and in the terminal."""
import os
import re
import sys
import textwrap

from axion.state import CONFIG

from .editor import EDITOR
from .theme import (
    C_BRAND, C_CMD, C_DIM, C_ERR, C_INFO, C_OK, C_WARN, ELLIPSIS, RULE, SPIN, OUT_LOCK,
    erase_line, paint, term_width, visible_len,
)

SECRET_RE = re.compile(r"achroma-chat=[^\s;]+|\b[0-9a-fA-F]{32,}\b")


def scrub(text):
    """Safety net: cookies, tokens and keys never reach the terminal, whatever called print."""
    text = SECRET_RE.sub(lambda m: "achroma-chat=***" if m.group(0).startswith("achroma") else "***", text)
    for secret in (CONFIG.get("gemini_api_key"), os.environ.get("GEMINI_API_KEY"), CONFIG.get("quickacc_password")):
        if secret and len(secret) >= 6:
            text = text.replace(secret, "***")
    return text


def emit(text=""):
    """Prints one line without breaking the prompt you are typing at."""
    text = scrub(str(text))
    with OUT_LOCK:
        if EDITOR.active or SPIN["active"]:
            sys.stdout.write(erase_line())
        sys.stdout.write(text + "\n")
        if EDITOR.active:
            EDITOR.draw()
        sys.stdout.flush()


def _emit_tagged(label, color, msg):
    tag = paint(f"[{label}]", color, bold=True)
    pad = " " * (len(label) + 3)
    avail = max(10, term_width() - len(pad))
    first = True
    for line in scrub(str(msg)).split("\n"):
        pieces = textwrap.wrap(line, avail) if visible_len(line) > avail else [line]
        for piece in pieces or [""]:
            emit((tag + " " if first else pad) + piece)
            first = False


def print_info(msg):
    _emit_tagged("INFO", C_INFO, msg)


def print_success(msg):
    _emit_tagged(" OK ", C_OK, msg)


def print_error(msg):
    _emit_tagged("ERROR", C_ERR, msg)


def print_warning(msg):
    _emit_tagged("WARN", C_WARN, msg)


def print_dim(msg):
    emit(paint(msg, C_DIM))


def print_separator():
    emit(paint(RULE * term_width(), C_DIM))


def print_header(title):
    label = f" {title.upper()} "
    emit("")
    emit(paint(RULE * 2 + label + RULE * max(2, term_width() - len(label) - 2), C_BRAND, bold=True))


def print_kv(pairs, title=None, indent=2):
    """Aligned key/value lines. A value can be (text, color) to color it."""
    if title:
        print_header(title)
    kw = max(len(k) for k, _ in pairs)
    vw = max(10, term_width() - indent - kw - 2)
    for key, value in pairs:
        color = ""
        if isinstance(value, tuple):
            value, color = value
        lines = []
        for part in scrub(str(value)).split("\n"):
            lines += textwrap.wrap(part, vw) or [""]
        emit(" " * indent + paint(key.ljust(kw), C_DIM) + "  " + paint(lines[0], color))
        for extra in lines[1:]:
            emit(" " * (indent + kw + 2) + paint(extra, color))


def print_table(headers, rows, title=None):
    """Aligned columns. A cell can be (text, color). Wide tables shrink their widest columns."""
    if title:
        print_header(title)
    if not rows:
        print_dim("(nothing to show)")
        return
    cells = [[(scrub(c[0]), c[1]) if isinstance(c, tuple) else (scrub(str(c)), "") for c in row] for row in rows]
    widths = [max([len(h)] + [len(r[i][0]) for r in cells]) for i, h in enumerate(headers)]
    room = term_width() - 2 * (len(headers) - 1)
    while sum(widths) > room and max(widths) > 6:
        widths[widths.index(max(widths))] -= 1

    def fit(text, width):
        return text if len(text) <= width else text[: max(1, width - 1)] + ELLIPSIS

    emit("  ".join(paint(fit(h, w).ljust(w), C_CMD, bold=True) for h, w in zip(headers, widths)).rstrip())
    emit(paint("  ".join(RULE * w for w in widths), C_DIM))
    for row in cells:
        emit("  ".join(paint(fit(t, w).ljust(w), c) for (t, c), w in zip(row, widths)).rstrip())


# ----- replies -----
# Commands answer with a Reply. In chat it goes out as plain text with a leading emoji, in the
# terminal it is printed through the tagged helpers above (the emoji is dropped, the tag says it).
DEFAULT_EMOJI = {"ok": "✅", "error": "🚫", "warn": "⚠️", "info": "ℹ️"}
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d]")


def strip_emoji(text):
    """Drops emoji for the terminal, which may not be able to show them."""
    text = EMOJI_RE.sub("", text)
    return "\n".join(re.sub(r"[ \t]{2,}", " ", line).strip() for line in text.split("\n")).strip()


class Reply(str):
    """Chat text that also remembers how it should look: a level (ok, error, warn, info) and an emoji."""
    level = "info"
    emoji = ""

    def chat_text(self):
        body = str(self)
        return f"{self.emoji} {body}" if self.emoji else body


def _reply(text, level, emoji):
    r = Reply(text)
    r.level = level
    r.emoji = DEFAULT_EMOJI[level] if emoji is None else emoji
    return r


def r_ok(text, emoji=None):
    return _reply(text, "ok", emoji)


def r_err(text, emoji=None):
    return _reply(text, "error", emoji)


def r_warn(text, emoji=None):
    return _reply(text, "warn", emoji)


def r_info(text, emoji=None):
    return _reply(text, "info", emoji)


def chat_text(text):
    """What actually gets posted for a reply, whether it is a Reply or a plain string."""
    return text.chat_text() if isinstance(text, Reply) else str(text)


def terminal_reply(text):
    level = getattr(text, "level", "info")
    {"ok": print_success, "error": print_error, "warn": print_warning}.get(level, print_info)(
        strip_emoji(str(text))
    )
