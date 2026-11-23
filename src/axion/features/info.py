"""Chat text for ?help and ?creds."""
from axion.constants import AUTHOR, POWERED_BY
from axion.registry import SECTION_EMOJI, SECTION_ORDER, chat_commands, lookup
from axion.state import CONFIG, prefix
from axion.ui import r_info, r_warn

TOGGLE_MARK = "🔘"


def help_text(args, is_owner, user):
    """Chat help, grouped by section. 🔘 marks commands with an on/off switch.
    People only see the commands they may use."""
    p = prefix()
    allowed = [c for c in chat_commands() if is_owner or (c.grantable and c.name in CONFIG["grants"].get(user, []))]
    if args:
        name = args[0].lower().lstrip("?" + p)
        cmd = lookup(name)
        if cmd is None or cmd not in allowed:
            return r_warn(f"No help for {p}{name}")
        text = f"{p}{cmd.name} {cmd.args}".strip() + f" : {cmd.description(p)}"
        if cmd.toggle:
            text += f"\n{TOGGLE_MARK} Has an on/off switch: {p}{cmd.name} on, {p}{cmd.name} off"
        return r_info(text, emoji="📖")

    lines = ["Commands" if is_owner else "Commands you can use"]
    for section in SECTION_ORDER:
        names = [c for c in allowed if c.section == section]
        if names:
            shown = " ".join(f"{p}{c.name}{TOGGLE_MARK if c.toggle else ''}" for c in names)
            lines.append(f"{SECTION_EMOJI.get(section, '•')} {section}: {shown}")
    if any(c.toggle for c in allowed):
        lines.append(f"{TOGGLE_MARK} = has an on/off switch, like {p}typing on")
    lines.append(f"💡 {p}help <command> for details")
    lines.append(f"🐍 made by {AUTHOR} in python")
    lines.append(POWERED_BY)
    return r_info("\n".join(lines), emoji="📖")


def creds_text():
    return r_info(
        f"Credits\n👤 Made by {AUTHOR}\n🐍 Written in python, running on Termux (Android)\n{POWERED_BY}",
        emoji="✨",
    )
