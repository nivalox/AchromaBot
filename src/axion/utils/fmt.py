"""Small formatting helpers shared by the chat replies and the terminal views."""
import re


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_duration(sec):
    sec = int(sec)
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    return f"{d}d {h}h {m}m {s}s" if d else f"{h}h {m}m {s}s"


def ping_quality(ms):
    """(label, emoji) for a ping in milliseconds."""
    if ms is None:
        return "unreachable", "🔴"
    if ms < 120:
        return "good", "🟢"
    if ms < 300:
        return "fair", "🟡"
    return "slow", "🔴"


def ping_line(label, ms, icon):
    """One chat line such as '📡 Your connection: 23 ms (good)'."""
    quality, _dot = ping_quality(ms)
    if ms is None:
        return f"{icon} {label}: unreachable"
    return f"{icon} {label}: {ms:.0f} ms ({quality})"


def split_list(tokens):
    """Flattens ['ai,snipe', 'creds'] into ['ai', 'snipe', 'creds']. Commas and spaces both separate."""
    out = []
    for token in tokens:
        out += [piece for piece in re.split(r"[,\s]+", token) if piece]
    return out
