"""Ctx: everything a command handler needs to know about the message that triggered it."""
from .state import STATE, is_owner, prefix
from .utils.users import message_mentions


class Ctx:
    def __init__(self, msg, rtt, send, local):
        self.msg = msg
        self.rtt = rtt
        self.local = local  # True when typed in the terminal
        self._send = send
        self.channel = msg.get("channel") or STATE["channel"]
        self.raw = (msg.get("body") or "").strip()
        self.user = (msg.get("username") or "").lower()
        self.is_owner = is_owner(self.user)
        self.name = ""  # canonical command name
        self.typed = ""  # the command as typed, with the prefix
        self.rest = ""  # everything after the command, original casing
        self.args = []  # rest split on spaces

    @property
    def p(self):
        return prefix()

    @property
    def mentions(self):
        return message_mentions(self.msg)

    def reply(self, text):
        self._send(text)
