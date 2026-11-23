"""Automation: ?typing, ?silenttyping, ?autoreact, ?autoreply."""
from axion.features.autoreact import handle_autoreact
from axion.features.autoreply import handle_autoreply
from axion.net.indicators import set_silent, set_typing
from axion.registry import command
from axion.ui import r_ok, r_warn


def toggled(label, on):
    return r_ok(f"{label} {'enabled' if on else 'disabled'}", emoji="✅" if on else "❌")


@command("typing", "on|off", "Toggle the typing indicator", section="Automation", toggle=True)
def cmd_typing(ctx):
    arg = ctx.args[0].lower() if ctx.args else ""
    if arg not in ("on", "off"):
        ctx.reply(r_warn(f"Usage: {ctx.p}typing on/off"))
        return
    on = arg == "on"
    ctx.reply(toggled("Typing", on))
    if on:
        set_silent(False)
    set_typing(on, ctx.channel)


@command("silenttyping", "on|off", "Cancel your typing indicator", section="Automation", toggle=True)
def cmd_silenttyping(ctx):
    arg = ctx.args[0].lower() if ctx.args else ""
    if arg not in ("on", "off"):
        ctx.reply(r_warn(f"Usage: {ctx.p}silenttyping on/off"))
        return
    on = arg == "on"
    ctx.reply(toggled("Silent typing", on))
    set_silent(on)


@command("autoreact", "on|off|emoji|users", "React to new messages", section="Automation", toggle=True)
def cmd_autoreact(ctx):
    ctx.reply(handle_autoreact(ctx.args, ctx.mentions))


@command("autoreply", "on|off|users|types|text", "Auto replies: who gets them and what they say", section="Automation", toggle=True)
def cmd_autoreply(ctx):
    ctx.reply(handle_autoreply(ctx.args, ctx.rest, ctx.mentions))
