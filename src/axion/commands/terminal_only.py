"""Commands that only work when typed in the terminal."""
from axion.features.accounts import remove_account, sign_in, switch_account
from axion.features.ai import fetch_ai_models, set_ai_key, set_ai_model  # noqa: F401
from axion.registry import command
from axion.state import CHANNELS, STATE
from axion.ui import print_error, print_kv, print_success, r_warn
from axion import views

SEC = "Terminal-only commands"


@command("accounts", "", "List saved accounts", section=SEC, scope="terminal")
def cmd_accounts(ctx):
    views.show_accounts()


@command("switch", "<name>", "Switch to a saved account", section=SEC, scope="terminal")
def cmd_switch(ctx):
    ctx.reply(switch_account(ctx.args[0]) if ctx.args else r_warn("Usage: switch <name>"))


@command("addaccount", "", "Sign in to another account", section=SEC, scope="terminal")
def cmd_addaccount(ctx):
    sign_in("Add an account: type its username, or press enter for the current one")


@command("removeaccount", "<name>", "Forget a saved account", section=SEC, scope="terminal")
def cmd_removeaccount(ctx):
    ctx.reply(remove_account(ctx.args[0]) if ctx.args else r_warn("Usage: removeaccount <name>"))


@command("aikey", "[remove]", "Set the Gemini API key", section=SEC, scope="terminal")
def cmd_aikey(ctx):
    ctx.reply(set_ai_key(ctx.args))


@command("aimodel", "[name]", "Show or set the Gemini model", section=SEC, scope="terminal")
def cmd_aimodel(ctx):
    if ctx.args:
        ctx.reply(set_ai_model(ctx.args[0]))
    else:
        views.show_ai_status()


@command("aimodels", "", "List models your key can use", section=SEC, scope="terminal")
def cmd_aimodels(ctx):
    views.show_ai_models()


@command("use", "<channel>", "Set the terminal channel", section=SEC, scope="terminal")
def cmd_use(ctx):
    if not ctx.args:
        print_kv([("Terminal channel", STATE["channel"]), ("Watching", ", ".join(CHANNELS))])
    elif ctx.args[0].lower() in CHANNELS:
        STATE["channel"] = ctx.args[0].lower()
        print_success(f"Terminal now uses {STATE['channel']}")
    else:
        print_error(f"Not watching {ctx.args[0]}, add it with channel add <name> first")


@command("quit", "", "Stop the bot", section=SEC, scope="terminal", aliases=("exit",))
def cmd_quit(ctx):
    raise KeyboardInterrupt
