"""Terminal views: formatted versions of what the chat commands answer in plain text."""
import os
import platform
import textwrap
import time

from axion.constants import AUTHOR, AXION_VERSION, POWERED_BY
from axion.features.ai import fetch_ai_models, get_ai_key
from axion.features.grants import shown
from axion.features.info import help_text
from axion.features.snipe import empty_text, snipe_fields
from axion.features.stats import START_TIME
from axion.registry import help_sections, lookup
from axion.state import CHANNELS, CONFIG, PROFILE, STATE, prefix, target_user
from axion.ui import (
    ANSI_OK, C_BRAND, C_CMD, C_DIM, C_ERR, C_HOST, C_OK, C_TEXT, C_USER, C_WARN, UNICODE_OK, emit, paint,
    print_dim, print_info, print_kv, print_success, print_table, spin, term_width, terminal_reply,
)
from axion.utils.fmt import fmt_bytes, fmt_duration
from axion.utils.sysinfo import platform_name, read_battery, read_load, read_memory, read_storage, read_uptime


def usage_color(pct):
    return C_ERR if pct >= 85 else C_WARN if pct >= 65 else C_OK


def print_help_box():
    HELP_SECTIONS = help_sections(prefix())
    w = term_width()
    inner = w - 4  # one border and one space on each side
    name_w = min(14, max(len(n) for _t, rows in HELP_SECTIONS for n, _a, _d in rows))
    desc_w = inner - 2 - name_w - 2
    stacked = desc_w < 16  # very narrow screen: name on one line, description under it
    if stacked:
        desc_w = inner - 4
    tl, tr, bl, br, h, v = ("╭", "╮", "╰", "╯", "─", "│") if UNICODE_OK else ("+", "+", "+", "+", "-", "|")

    def row(segments):
        used = sum(len(t) for t, _c in segments)
        body = "".join(paint(t, c) for t, c in segments) + " " * max(0, inner - used)
        emit(paint(v, C_DIM) + " " + body + " " + paint(v, C_DIM))

    title = " AXION COMMANDS "
    side = max(2, w - 2 - len(title))
    emit("")
    emit(paint(tl + h * (side // 2), C_DIM) + paint(title, C_BRAND, bold=True) + paint(h * (side - side // 2) + tr, C_DIM))
    for i, (section, rows) in enumerate(HELP_SECTIONS):
        if i:
            row([])
        row([(section.upper(), C_BRAND)])
        for name, cmd_args, desc in rows:
            if stacked:
                row([("  " + name, C_CMD)])
                for extra in textwrap.wrap(desc + (" " + cmd_args if cmd_args else ""), desc_w):
                    row([("    " + extra, "")])
                continue
            lines = textwrap.wrap(desc, desc_w) or [""]
            args_line = None
            if cmd_args:
                if len(lines[-1]) + 1 + len(cmd_args) <= desc_w:
                    lines[-1] += " " + cmd_args  # shown dim below
                else:
                    args_line = cmd_args
            for j, text in enumerate(lines):
                head = ("  " + name.ljust(name_w) + "  ") if j == 0 else " " * (2 + name_w + 2)
                if cmd_args and args_line is None and j == len(lines) - 1:
                    plain, dim = text[: -len(cmd_args)], cmd_args
                    row([(head, C_CMD if j == 0 else ""), (plain, ""), (dim, C_DIM)])
                else:
                    row([(head, C_CMD if j == 0 else ""), (text, "")])
            if args_line:
                for extra in textwrap.wrap(args_line, desc_w):
                    row([(" " * (2 + name_w + 2), ""), (extra, C_DIM)])
    emit(paint(bl + h * (w - 2) + br, C_DIM))
    print_dim(f"Type a command with or without {prefix()}. made by {AUTHOR} in python")
    print_dim(POWERED_BY)


def show_help(args):
    if not args:
        print_help_box()
        return
    name = args[0].lower().lstrip("?" + prefix())
    cmd = lookup(name, "terminal")
    if cmd and cmd.scope == "terminal":
        print_info(f"{cmd.name} {cmd.args}".strip() + f" : {cmd.description(prefix())}")
    else:
        terminal_reply(help_text(args, True, ""))


def ping_label(ms):
    if ms < 120:
        return "good", C_OK
    if ms < 300:
        return "fair", C_WARN
    return "slow", C_ERR


def show_ping(result):
    """result is {"client": ms, "site": ms, "api": ms}, None meaning that one could not be reached."""
    rows = []
    for label, key in (("Your connection", "client"), ("bikesense.org", "site"), ("Chat API", "api")):
        ms = result.get(key)
        if ms is None:
            rows.append((label, ("unreachable", C_ERR)))
        else:
            quality, color = ping_label(ms)
            rows.append((label, (f"{ms:.0f}ms ({quality})", color)))
    print_kv(rows, title="Ping")
    print_dim("Your connection is a TCP connect to public DNS, bikesense.org is a full HTTPS request")


def show_profile():
    unset = ("(not set)", C_DIM)
    print_kv([
        ("Display name", PROFILE.get("display_name") or unset),
        ("Username", PROFILE.get("username") or unset),
        ("Bio", PROFILE.get("bio") or unset),
    ], title="Profile")


def show_credits():
    print_kv([
        ("Project", "Axion, an Achroma toolkit"),
        ("Author", AUTHOR),
        ("Version", f"v{AXION_VERSION}"),
        ("Runs on", platform_name()),
        ("Repo", "github.com/nivalox/AchromaBot"),
        ("Powered by", "Marin, Alya, Konata & Mimi Typh"),
    ], title="Credits")


def show_snipe(channel, n=1):
    f, total = snipe_fields(channel, n)
    if not f:
        print_info(empty_text(channel, n, total) if total else f"Nothing to snipe in {channel}")
        return
    pairs = [
        ("Channel", channel),
        ("Position", f"#{f['n']} of {f['total']} (1 is the newest)"),
        ("Author", f"{f['name']} (@{f['user']})"),
        ("Deleted", f"{f['ago']} ago"),
        ("Message", f["text"] or ("(no text)", C_DIM)),
    ]
    if f["att"]:
        pairs.append(("Attachment", f["att"]))
    print_kv(pairs, title="Sniped message")


def show_stats():
    with spin("Gathering stats"):
        bat, mem, disk, load, up = read_battery(), read_memory(), read_storage(), read_load(), read_uptime()
    device = [
        ("Platform", platform_name()),
        ("System", f"{platform.system()} {platform.release()}".strip()),
        ("Machine", platform.machine() or "unknown"),
        ("CPU cores", str(os.cpu_count())),
    ]
    if load:
        device.append(("Load avg", f"{load[0]:.2f} {load[1]:.2f} {load[2]:.2f}"))
    if up is not None:
        device.append(("Uptime", fmt_duration(up)))
    print_kv(device, title="Device")

    memory = []
    for label, pair in (("RAM", mem), ("Storage", disk)):
        if pair:
            pct = pair[0] / pair[1] * 100
            memory.append((label, (f"{fmt_bytes(pair[0])} / {fmt_bytes(pair[1])} ({pct:.0f}%)", usage_color(pct))))
        else:
            memory.append((label, ("unavailable", C_DIM)))
    print_kv(memory, title="Memory")

    if bat:
        pct = bat.get("percentage") or 0
        level_color = C_OK if pct >= 50 else C_WARN if pct >= 20 else C_ERR
        termux = [
            ("Battery", (f"{pct}%", level_color)),
            ("Status", str(bat.get("status", "?")).lower()),
            ("Plugged", str(bat.get("plugged", "?"))),
            ("Temperature", f"{bat.get('temperature')} C"),
            ("Health", str(bat.get("health"))),
        ]
    else:
        termux = [("Battery", ("unavailable, needs Termux:API and termux-api", C_DIM))]
    print_kv(termux, title="Termux")

    print_kv([
        ("Version", platform.python_version()),
        ("Implementation", platform.python_implementation()),
        ("Bot uptime", fmt_duration(time.time() - START_TIME)),
        ("Watching", ", ".join(CHANNELS)),
    ], title="Python")


def show_accounts():
    dot = "●" if UNICODE_OK else "*"
    rows = []
    for name in sorted(CONFIG["accounts"]):
        acc = CONFIG["accounts"][name]
        active = name == target_user()
        has_cookie = "achroma-chat=" in acc.get("cookie", "")
        rows.append([
            (dot, C_OK) if active else "",
            (name, C_USER) if active else name,
            str(acc.get("user_id", "-")),
            ("saved", C_OK) if has_cookie else ("missing", C_WARN),
        ])
    print_table(["", "Account", "User ID", "Session"], rows, title="Accounts")
    print_dim("Switch with: switch <name>")


def show_ai_status():
    key_set = bool(get_ai_key())
    ai = CONFIG["ai"]
    print_kv([
        ("Model", (ai["model"], C_CMD)),
        ("API key", ("set", C_OK) if key_set else ("not set, use aikey", C_WARN)),
        ("Max reply", f"{ai['max_chars']} characters"),
        ("Cooldown", f"{ai['cooldown']}s for granted users"),
    ], title="Gemini")
    print_dim("aimodels lists models, aimodel <name> switches")


def show_ai_models():
    with spin("Fetching models"):
        names, err = fetch_ai_models()
    if err:
        terminal_reply(err)
        return
    dot = "●" if UNICODE_OK else "*"
    active = CONFIG["ai"]["model"]
    rows = [[(dot, C_OK) if n == active else "", (n, C_CMD) if n == active else n] for n in names]
    print_table(["", "Model"], rows, title="Gemini models")
    print_dim(f"{len(names)} models, the active one is marked. Switch with: aimodel <name>")


def show_ai_answer(prompt, answer):
    if getattr(answer, "level", "info") in ("error", "warn"):
        terminal_reply(answer)
        return
    print_kv([
        ("Question", prompt),
        ("Model", (CONFIG["ai"]["model"], C_CMD)),
        ("Response", (str(answer), C_TEXT)),
    ], title="Gemini")


def show_grants():
    if not CONFIG["grants"]:
        print_info("No one has been granted commands")
        return
    rows = [[(user, C_USER), shown(cmds)] for user, cmds in sorted(CONFIG["grants"].items())]
    print_table(["User", "Commands"], rows, title="Granted permissions")


def show_channels():
    rows = []
    for ch in CHANNELS:
        status = ("unreachable", C_ERR) if ch in STATE["warned"] else ("watching", C_OK)
        here = ch == STATE["channel"]
        rows.append([
            (ch, C_HOST) if here else ch,
            "DM" if ch.startswith("dm-") else "public",
            status,
            ("●" if UNICODE_OK else "*", C_OK) if here else "",
        ])
    print_table(["Channel", "Type", "Status", "Terminal"], rows, title="Channels")
    print_dim("Change the terminal channel with: use <channel>")


def show_user_info(rows):
    pairs = [(label, value) for _emoji, label, value in rows]
    print_kv(pairs, title="User info")
