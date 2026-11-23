"""Profile: ?profile."""
from axion.features.profile import handle_profile
from axion.registry import command
from axion import views


@command("profile", "name|user|bio <text>", "Change your profile, or {p}profile show", section="Profile")
def cmd_profile(ctx):
    if ctx.local and ctx.args[:1] and ctx.args[0].lower() == "show":
        views.show_profile()
    else:
        ctx.reply(handle_profile(ctx.rest))
