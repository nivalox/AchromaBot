"""Social: ?info, ?friend, ?warn, ?vc. Everything except ?info is owner-only and can't be granted."""
from axion.features.social import handle_friend, handle_warn
from axion.features.userinfo import info_rows, info_text, lookup
import re

from axion.registry import command
from axion.ui import r_err, r_warn
from axion import views


@command("info", "[@user|id]", "Show everything about a user, or about you with no name", section="Social",
         grantable=True)
def cmd_info(ctx):
    data, err = lookup(ctx.args, ctx.mentions, ctx.user)
    if err:
        ctx.reply(err)
    elif ctx.local:
        views.show_user_info(info_rows(data))
    else:
        ctx.reply(info_text(info_rows(data)))


@command("friend", "[add|remove] <@user|id>", "Send a friend request, or unfriend with {p}friend remove @user (a / r for short)", section="Social")
def cmd_friend(ctx):
    ctx.reply(handle_friend(ctx.args, ctx.mentions))


@command("warn", "<@user|id> [reason]", "Warn a user, like {p}warn @gilbert spamming", section="Social")
def cmd_warn(ctx):
    ctx.reply(handle_warn(ctx.args, ctx.mentions))


@command("vc", "<j|l|mute|unmute|deafen|undeafen> [name]", "Join or leave a voice channel and stay connected, like {p}vc j voice", section="Social")
def cmd_vc(ctx):
    from axion.net import voice
    p = ctx.p
    sub = ctx.args[0].lower() if ctx.args else ""
    if not sub or sub in ("status", "s"):
        ctx.reply(voice.status())
    elif sub in ("j", "join"):
        name = ctx.args[1].lower() if len(ctx.args) > 1 else ""
        if not name:
            ctx.reply(r_warn(f"Usage: {p}vc j <name>, like {p}vc j voice"))
        elif not re.fullmatch(r"[a-z0-9_-]{1,40}", name):
            ctx.reply(r_err("Voice channel names are letters, numbers, - and _"))
        else:
            ctx.reply(voice.join(name))
    elif sub in ("l", "leave"):
        ctx.reply(voice.leave())
    elif sub in ("mute", "unmute", "deafen", "undeafen"):
        flag = "muted" if sub.endswith("mute") else "deafened"
        ctx.reply(voice.set_state(**{flag: not sub.startswith("un")}))
    else:
        ctx.reply(r_warn(f"Usage: {p}vc j <name>, {p}vc l, {p}vc mute/unmute/deafen/undeafen, or {p}vc for the status"))
