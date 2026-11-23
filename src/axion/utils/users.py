"""Turns whatever a person typed into a username: plain names, @mentions, mention markup and ids.

The site's exact mention format is not known here, so the common shapes are all understood:
@name, <@name>, <@123>, @[name], @[Name](123), [@name](/u/123) and bare numeric ids. Display names are
NOT matched on purpose: anyone can set a display name, so a grant could land on an impersonator.
If a message carries a "mentions" list, that is used too."""
import re

from axion.state import CONFIG, STATE

_PUNCT = ",.:;!?"
MENTION_RES = (
    re.compile(r"^<@!?([^>\s]+)>$"),                          # <@name> <@123>
    re.compile(r"^@\[([^\]]+)\](?:\([^)]*\))?$"),             # @[name] @[Name](123)
    re.compile(r"^\[@?([^\]]+)\]\([^)]*\)$"),                 # [@name](/u/123)
    re.compile(r"^@([A-Za-z0-9_.\-]*[A-Za-z0-9_\-])[" + re.escape(_PUNCT) + r"]*$"),  # @name  @name,
)
NAME_RE = re.compile(r"[a-z0-9_.\-]{1,40}")


def looks_like_mention(token):
    return token.startswith(("@", "<@", "[@"))


def username_for_id(uid):
    for name, known in STATE["users"].items():
        if str(known) == str(uid):
            return name
    return None


def message_mentions(msg):
    """Usernames from the message's own mentions list, if the site sends one."""
    found = []
    for item in msg.get("mentions") or []:
        if isinstance(item, dict):
            name = (item.get("username") or "").lower()
            uid = item.get("user_id", item.get("id"))
            if name and uid is not None:
                STATE["users"].setdefault(name, uid)
            if not name and uid is not None:
                name = username_for_id(uid) or ""
            if name:
                found.append(name)
        elif isinstance(item, (str, int)):
            text = str(item).lower().lstrip("@")
            found.append((username_for_id(text) or text) if text.isdigit() else text)
    return found


def extract_ident(token):
    """The name or id inside mention markup, or None when the token is not mention markup."""
    token = token.strip()
    for rx in MENTION_RES:
        m = rx.match(token)
        if m:
            return m.group(1)
    return None


def resolve_user(token, fallback=None):
    """Returns (username, None) or (None, error text). fallback is a username to use when the
    token itself cannot be understood, such as an id nobody has been seen with yet."""
    ident = extract_ident(token)
    if ident is None:
        ident = token.strip().lstrip("@")
    ident = ident.strip().lower()
    if not ident:
        return (fallback, None) if fallback else (None, "No username given")
    if ident.isdigit():
        name = username_for_id(ident)
        if name:
            return name, None
        return (fallback, None) if fallback else (None, f"Don't know user id {ident} yet")
    if ident in STATE["users"] or ident in CONFIG["accounts"]:
        return ident, None
    if NAME_RE.fullmatch(ident):
        return ident, None  # nobody by that name has posted yet, trust the spelling
    return (fallback, None) if fallback else (None, f"Can't tell who {token} is")


def split_user_args(args, mentions=()):
    """Splits '@a @b ai,snipe' into the people and the rest.
    Leading tokens that look like mentions are people ('@a,@b' counts as two). Without any
    mention the first word is the person. Returns (people, rest) where people is a list of
    (username, error) pairs."""
    args = list(args)
    tokens = []
    while args and looks_like_mention(args[0]):
        tokens += [piece for piece in args.pop(0).split(",") if piece]
    if not tokens and args:
        tokens.append(args.pop(0))
    people = []
    for i, token in enumerate(tokens):
        fallback = mentions[i] if i < len(mentions) else None
        people.append(resolve_user(token, fallback))
    return people, args


def user_id_for(username):
    """The numeric site id of a username, from messages seen so far or from your own accounts."""
    if username in STATE["users"]:
        return STATE["users"][username]
    return CONFIG["accounts"].get(username, {}).get("user_id")


def resolve_target(token, fallback=None):
    """For commands that need the numeric id. Returns (user id, label, error text).
    A numeric id works even when nobody has seen that person yet."""
    ident = extract_ident(token)
    if ident is None:
        ident = token.strip().lstrip("@")
    if ident.isdigit():
        return int(ident), "@" + (username_for_id(ident) or f"user {ident}").lstrip("@"), None
    name, err = resolve_user(token, fallback)
    if err:
        return None, token, err
    uid = user_id_for(name)
    if uid is None:
        return None, "@" + name, f"Don't know @{name}'s id yet. Use their numeric id, or wait until they post in a watched channel."
    return uid, "@" + name, None
