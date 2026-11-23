"""General: ?help, ?ping, ?stats, ?creds, ?prefix."""
from axion.config import save_config
from axion.constants import DEFAULT_PREFIX
from axion.features.info import creds_text, help_text
from axion.features.linkgen import handle_linkgen
from axion.features.stats import get_stats
from axion.net.ping import measure_all
from axion.registry import command
from axion.state import CONFIG, valid_prefix
from axion.ui import r_info, r_ok, r_warn, spin
from axion.utils.fmt import ping_line
from axion import views


@command("help", "[command]", "Show available commands", section="General", grantable=True, default_grant=True)
def cmd_help(ctx):
    if ctx.local:
        views.show_help(ctx.args)
    else:
        ctx.reply(help_text(ctx.args, ctx.is_owner, ctx.user))


@command("ping", "", "Ping of your connection, bikesense.org and the chat API", section="General",
         grantable=True, default_grant=True)
def cmd_ping(ctx):
    with spin("Pinging"):
        result = measure_all(ctx.rtt)
    if ctx.local:
        views.show_ping(result)
        return
    ctx.reply(r_info(
        "Pong!\n"
        + ping_line("Your connection", result["client"], "📡") + "\n"
        + ping_line("bikesense.org", result["site"], "🌐") + "\n"
        + ping_line("Chat API", result["api"], "💬"),
        emoji="🏓",
    ))


@command("stats", "", "Display device statistics", section="General", grantable=True)
def cmd_stats(ctx):
    if ctx.local:
        views.show_stats()
    else:
        ctx.reply(get_stats())


@command("creds", "", "Show credits", section="General", grantable=True, default_grant=True)
def cmd_creds(ctx):
    if ctx.local:
        views.show_credits()
    else:
        ctx.reply(creds_text())


@command("prefix", "[symbol|reset]", "Show or change the command prefix", section="General")
def cmd_prefix(ctx):
    p = ctx.p
    if not ctx.args:
        ctx.reply(r_info(f"Current prefix: {p}\nTry {p}help. Change it with {p}prefix <symbol>, or {p}prefix reset", emoji="🔣"))
        return
    new = ctx.args[0]
    if new.lower() in ("reset", "default"):
        new = DEFAULT_PREFIX
    if not valid_prefix(new):
        ctx.reply(r_warn("A prefix is 1 to 3 symbols, like ! or . or $. No letters, digits, spaces or @"))
        return
    if new == p:
        ctx.reply(r_warn(f"The prefix is already {p}"))
        return
    CONFIG["prefix"] = new
    save_config()
    note = ""
    if new != DEFAULT_PREFIX:
        note = f"\n💡 {DEFAULT_PREFIX}prefix always keeps working for you, so you can't lock yourself out"
    ctx.reply(r_ok(f"Prefix changed to {new}\nCommands are now {new}help, {new}ping and so on{note}", emoji="🔣"))


@command("linkgen", "[filters] [count]", "Get links from the link generator, like {p}linkgen goguardian 2",
         section="General", grantable=True)
def cmd_linkgen(ctx):
    with spin("Generating"):
        reply = handle_linkgen(ctx.args)
    ctx.reply(reply)
