"""Permissions: ?grant, ?revoke, ?grants."""
from axion.features.grants import handle_grant, handle_revoke, list_grants
from axion.registry import command
from axion import views


@command("grant", "<@user> [cmds|all]", "Let others use commands, like {p}grant @gilbert ai,snipe,creds",
         section="Permissions")
def cmd_grant(ctx):
    ctx.reply(handle_grant(ctx.args, ctx.mentions))


@command("revoke", "<@user> [cmds]", "Take commands back", section="Permissions")
def cmd_revoke(ctx):
    ctx.reply(handle_revoke(ctx.args, ctx.mentions))


@command("grants", "", "List granted permissions", section="Permissions")
def cmd_grants(ctx):
    if ctx.local:
        views.show_grants()
    else:
        ctx.reply(list_grants())
