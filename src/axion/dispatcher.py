"""Turns a message into a command run: parses the prefix, checks who may use it, calls the handler."""
import re

from . import commands  # noqa: F401  (importing it registers every command)
from .context import Ctx
from .features.autoreply import reply_for
from .net.http import send_message
from .registry import lookup
from .state import CONFIG, STATE, prefix
from .ui import chat_text, print_dim, print_error, r_err


def chat_sender(channel):
    """Chat replies go out as plain text, with the emoji of their level."""
    return lambda text: send_message(chat_text(text), channel)


def parse_command(ctx):
    """The command word without its prefix, or None when the message is not a command.
    A command is the prefix plus letters only, so "?", "??" and "?!" are ignored.
    ?prefix keeps working for owners with the default prefix, so a changed prefix can never lock them out."""
    first = ctx.raw.split()[0].lower()
    pfx = prefix()
    if first.startswith(pfx):
        name = first[len(pfx):]
    elif ctx.is_owner and first == "?prefix":
        name = "prefix"
    else:
        return None
    return name if re.fullmatch(r"[a-z]+", name) else None


def handle_message(m, rtt, reply=None, local=False):
    """Runs a command. In chat, answers go to the channel as plain text. With local=True (typed in
    the terminal) the same commands show formatted output instead."""
    channel = m.get("channel") or STATE["channel"]
    ctx = Ctx(m, rtt, reply or chat_sender(channel), local)
    if not ctx.raw:
        return

    # Never react to our own "isn't a command" reply, it can end with the bad command
    if ctx.raw.lower().endswith("isn't a command"):
        return

    name = parse_command(ctx)
    if name is None:
        return
    ctx.typed = ctx.raw.split()[0].lower()
    cmd = lookup(name, "terminal" if local else "chat")

    # only grantable commands count, so an old or hand-edited grants entry can never unlock ?warn, ?prefix and the like
    granted = cmd is not None and cmd.grantable and cmd.name in CONFIG["grants"].get(ctx.user, [])
    if not (ctx.is_owner or granted):
        if cmd is not None:
            reply_for("unauth", ctx)
        return

    if cmd is None:
        if local:
            print_error(f"Unknown command: {name}")
            print_dim("Type help to see the available commands")
        else:
            reply_for("unknown", ctx)
        return

    parts = ctx.raw.split(None, 1)
    ctx.name = cmd.name
    ctx.rest = parts[1].strip() if len(parts) > 1 else ""
    ctx.args = ctx.rest.split()
    if not local:
        print_dim(f"{ctx.user} ran {ctx.typed} in {channel}")

    try:
        cmd.handler(ctx)
    except Exception as e:  # a bug in one command must not stop the bot
        print_error(f"{ctx.typed} failed: {e}")
        ctx.reply(r_err(f"{ctx.typed} hit an error, check the terminal"))
