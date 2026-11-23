"""?grant, ?revoke and ?grants: let other people use some of your commands.

Grants are stored without the prefix (so "ai", not "?ai") and survive a prefix change.
?grant @gilbert ai,snipe,creds   several commands at once, separated by commas and/or spaces
?grant @a @b ai                  several people at once
?grant gilbert                   a plain username works too"""
from axion.config import save_config
from axion.registry import default_grant_names, grantable_names, lookup
from axion.state import CONFIG, prefix
from axion.ui import r_err, r_info, r_ok, r_warn
from axion.utils.fmt import split_list
from axion.utils.users import split_user_args


def shown(cmds):
    p = prefix()
    return " ".join(p + c for c in cmds)


def grantable_text():
    return shown(grantable_names())


def parse_command_names(tokens):
    """['ai,snipe', '?creds'] -> (['ai', 'snipe', 'creds'], []). Unknown words come back in the second list."""
    names, bad = [], []
    for word in split_list(tokens):
        word = word.lower().lstrip("?" + prefix())
        cmd = lookup(word)
        if cmd and cmd.name not in names:
            names.append(cmd.name)
        elif not cmd:
            bad.append(word)
    return names, bad


def list_grants():
    if not CONFIG["grants"]:
        return r_info("No one has been granted commands", emoji="🔑")
    lines = [f"@{u}: {shown(c)}" for u, c in sorted(CONFIG["grants"].items())]
    return r_info("Granted permissions\n" + "\n".join(lines), emoji="🔑")


def _people(args, mentions):
    """Returns (usernames, error Reply or None, remaining args)."""
    people, rest = split_user_args(args, mentions)
    errors = [e for _n, e in people if e]
    if errors:
        return [], r_err("; ".join(errors)), rest
    return list(dict.fromkeys(n for n, _e in people)), None, rest


def handle_grant(args, mentions=()):
    p = prefix()
    usage = f"Usage: {p}grant <@user> [commands or all], like {p}grant @gilbert ai,snipe,creds. Grantable: {grantable_text()}"
    if not args:
        return r_warn(usage)
    users, err, rest = _people(args, mentions)
    if err:
        return err
    if not users:
        return r_warn(usage)

    words = [w.lower().lstrip("?" + p) for w in split_list(rest)]
    if not words:
        cmds = default_grant_names()
    elif words == ["all"]:
        cmds = grantable_names()
    else:
        cmds, bad = parse_command_names(rest)
        notgrantable = [c for c in cmds if c not in grantable_names()]
        bad += notgrantable
        if bad:
            return r_err(f"Can't grant {' '.join(p + b for b in bad)}. Grantable: {grantable_text()}")

    lines = []
    for user in users:
        if user in CONFIG["accounts"]:
            lines.append(f"@{user} is already one of your accounts")
            continue
        merged = sorted(set(CONFIG["grants"].get(user, [])) | set(cmds))
        CONFIG["grants"][user] = merged
        lines.append(f"@{user} can now use: {shown(merged)}")
    save_config()
    return r_ok("\n".join(lines))


def handle_revoke(args, mentions=()):
    p = prefix()
    usage = f"Usage: {p}revoke <@user> [commands], like {p}revoke @gilbert snipe,creds"
    if not args:
        return r_warn(usage)
    users, err, rest = _people(args, mentions)
    if err:
        return err
    if not users:
        return r_warn(usage)

    names = [w.lower().lstrip("?" + p) for w in split_list(rest)]
    names = [lookup(n).name if lookup(n) else n for n in names]  # aliases count
    lines, level_warn = [], True
    for user in users:
        if user not in CONFIG["grants"]:
            lines.append(f"@{user} has no granted commands")
            continue
        level_warn = False
        if not names:
            del CONFIG["grants"][user]
            lines.append(f"Revoked everything from @{user}")
            continue
        left = [c for c in CONFIG["grants"][user] if c not in names]
        if left:
            CONFIG["grants"][user] = left
            lines.append(f"@{user} can now use: {shown(left)}")
        else:
            del CONFIG["grants"][user]
            lines.append(f"Revoked everything from @{user}")
    save_config()
    text = "\n".join(lines)
    return r_warn(text) if level_warn else r_ok(text)
