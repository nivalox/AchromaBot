"""The command table. Command modules register handlers with @command, the dispatcher, the help
screens and ?grant all read from here, so a new command only has to be declared once.

scope "chat"     works in chat and in the terminal
scope "terminal" only works when typed in the terminal"""
from dataclasses import dataclass

SECTION_ORDER = [
    "General", "Messaging", "Profile", "Automation", "Account Management",
    "AI / Gemini", "Permissions", "Terminal-only commands",
]
SECTION_ORDER.insert(2, "Social")  # after Messaging
SECTION_EMOJI = {
    "General": "🧭", "Messaging": "💬", "Social": "🤝", "Profile": "🪪", "Automation": "⚙️",
    "Account Management": "👤", "AI / Gemini": "🤖", "Permissions": "🔑",
}


@dataclass
class Command:
    name: str
    handler: object
    args: str = ""
    desc: str = ""
    section: str = "General"
    aliases: tuple = ()
    scope: str = "chat"
    grantable: bool = False  # can the owner hand it to other people with ?grant
    default_grant: bool = False  # included when ?grant is used without a command list
    toggle: bool = False  # has an on/off switch, ?help marks these

    def description(self, prefix):
        """The description with {p} replaced by the current prefix, so examples stay correct after ?prefix."""
        return self.desc.replace("{p}", prefix)


COMMANDS = {}  # canonical name -> Command
ALIASES = {}  # alias -> canonical name


def command(name, args="", desc="", section="General", aliases=(), scope="chat", grantable=False, default_grant=False, toggle=False):
    def register(fn):
        cmd = Command(name, fn, args, desc, section, tuple(aliases), scope, grantable, default_grant, toggle)
        COMMANDS[name] = cmd
        for alias in cmd.aliases:
            ALIASES[alias] = name
        return fn
    return register


def lookup(name, scope="chat"):
    """The Command for a typed name (aliases work), or None. Chat commands are visible from the
    terminal as well, terminal-only commands are not visible from chat."""
    name = ALIASES.get(name, name)
    cmd = COMMANDS.get(name)
    if cmd is None:
        return None
    if cmd.scope == "terminal" and scope != "terminal":
        return None
    return cmd


def chat_commands():
    return [c for c in COMMANDS.values() if c.scope == "chat"]


def grantable_names():
    return sorted(c.name for c in COMMANDS.values() if c.grantable)


def default_grant_names():
    return [c.name for c in COMMANDS.values() if c.default_grant]


def help_sections(prefix):
    """[(section, [(shown name, args, description)])]. Chat commands show the prefix, terminal ones do not."""
    out = []
    for section in SECTION_ORDER:
        rows = [
            ((prefix + c.name) if c.scope == "chat" else c.name, c.args, c.description(prefix))
            for c in COMMANDS.values() if c.section == section
        ]
        if rows:
            out.append((section, rows))
    return out
