"""Account management: ?signin, ?signup, ?quickacc."""
from axion.features.accounts import parse_quickacc, quick_account, sign_in, signup_account
from axion.registry import command
from axion.state import CONFIG
from axion.ui import r_info, r_warn


@command("signin", "", "Sign in from the terminal, also {p}signing", section="Account Management", aliases=("signing",))
def cmd_signin(ctx):
    if not ctx.local:
        ctx.reply(r_info("Go back to the terminal to sign in", emoji="🔐"))
    msg = sign_in()[1]  # prints its own result in the terminal
    if not ctx.local:
        ctx.reply(r_info(msg, emoji="🔐"))


@command("signup", "", "Create an account, asks in the terminal", section="Account Management")
def cmd_signup(ctx):
    if not ctx.local:
        ctx.reply(r_info("Go back to the terminal to enter the account details", emoji="📝"))
    msg = signup_account()
    if not ctx.local:
        ctx.reply(msg)


@command("quickacc", "[-u name] [-c pass]",
         "Create an account and sign in. -u sets the username, -c the password, like {p}quickacc -u cool",
         section="Account Management")
def cmd_quickacc(ctx):
    username, password, err = parse_quickacc(ctx.args)
    if err:
        p = ctx.p
        ctx.reply(r_warn(
            f"Usage: {p}quickacc [-u <username>] [-c <password>]\n"
            f"{p}quickacc makes a random account, -u picks the username, -c the password.\n"
            f"Careful: a password typed in chat is visible to everyone here, the saved default is safer"
        ))
        return
    if not (password or CONFIG["quickacc_password"]):
        ctx.reply(r_warn(f"No default password is saved. Use {ctx.p}quickacc -c <password> or set quickacc_password in secrets.json"))
        return
    if not ctx.local:
        ctx.reply(r_info("Creating a quick account, the details are in the terminal", emoji="⚡"))
    quick_account(ctx.args)  # prints its own result in the terminal
