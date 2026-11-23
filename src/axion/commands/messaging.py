"""Messaging: ?echo, ?snipe, ?csnipe, ?channel, ?dm."""
from axion.features.channels import handle_channel, handle_dm
from axion.features.snipe import clear_snipes, get_snipe, parse_index
from axion.net.http import send_message
from axion.registry import command
from axion.ui import print_success, r_ok, r_warn
from axion import views


@command("echo", "<text>", "Send a message", section="Messaging", grantable=True)
def cmd_echo(ctx):
    if ctx.rest:
        send_message(ctx.rest, ctx.channel)  # echo always goes to the chat
        if ctx.local:
            print_success(f"Message sent to {ctx.channel}")
    else:
        ctx.reply(r_warn(f"Usage: {ctx.p}echo <text>"))


@command("snipe", "[number]", "Show the latest deleted message, or the Nth last one like {p}snipe 5",
         section="Messaging", grantable=True)
def cmd_snipe(ctx):
    n, err = parse_index(ctx.args)
    if err:
        ctx.reply(err)
    elif ctx.local:
        views.show_snipe(ctx.channel, n)
    else:
        ctx.reply(get_snipe(ctx.channel, n))


@command("csnipe", "", "Clear sniped messages, also {p}clearsnipe", section="Messaging", aliases=("clearsnipe",))
def cmd_csnipe(ctx):
    clear_snipes(ctx.channel)
    ctx.reply(r_ok("Snipe cleared", emoji="🧹"))


@command("channel", "[add|remove <name>]", "List or change watched channels", section="Messaging")
def cmd_channel(ctx):
    if ctx.local and (not ctx.args or ctx.args[0].lower() in ("list", "show")):
        views.show_channels()
    else:
        ctx.reply(handle_channel(ctx.args))


@command("dm", "<id|user|dm-name>", "Start watching a DM", section="Messaging")
def cmd_dm(ctx):
    ctx.reply(handle_dm(ctx.args))
