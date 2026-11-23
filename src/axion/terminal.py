"""Reading what you type in the terminal and running it."""
import os
import select
import sys
import time

from .dispatcher import handle_message
from .state import STATE, prefix, target_user
from .ui import EDITOR, print_error, print_warning, terminal_reply


def run_terminal_line(line):
    """Runs one typed command. A bug in a command prints an error instead of stopping the bot."""
    try:
        handle_terminal(line)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        print_error(f"Command failed: {e}")



def handle_terminal(line):
    """Typed commands run as the active account. The prefix is optional: help, ?help and !help all work."""
    line = line.strip()
    if not line:
        return
    for pfx in (prefix(), "?"):
        if line.startswith(pfx):
            line = line[len(pfx):].strip()
            break
    if not line:
        return
    # Same handler as chat, with formatted output here
    msg = {"id": 0, "username": target_user(), "body": prefix() + line, "channel": STATE["channel"]}
    handle_message(msg, STATE["rtt"], reply=terminal_reply, local=True)


def poll_terminal(timeout):
    """Waits up to timeout seconds and runs any command typed meanwhile."""
    if EDITOR.enabled:
        try:
            EDITOR.start()
            lines = EDITOR.read(timeout)
        except EOFError:
            EDITOR.stop()
            EDITOR.enabled = False
            print_warning("Terminal input closed, chat commands still work")
            return
        for line in lines:
            EDITOR.commit(line)  # keeps the typed command on screen and leaves raw mode
            run_terminal_line(line)
        return

    # Plain reading: no ANSI terminal, or input is piped
    if not STATE["terminal"]:
        time.sleep(timeout)
        return
    try:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return
        data = os.read(sys.stdin.fileno(), 4096)
    except (OSError, ValueError):
        STATE["terminal"] = False  # no usable terminal, fall back to plain sleeping
        time.sleep(timeout)
        return
    if not data:
        STATE["terminal"] = False
        print_warning("Terminal input closed, chat commands still work")
        return
    for line in data.decode(errors="replace").splitlines():
        run_terminal_line(line)
