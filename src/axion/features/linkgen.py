"""?linkgen: asks the site's link generator for links, like the linkgen page does."""
import re

import requests

from axion.constants import LINKGEN_REFERER, LINKGEN_URL
from axion.net.http import session
from axion.state import CONFIG, prefix
from axion.ui import r_err, r_info, r_warn

MAX_LINKS = 10  # keeps one reply from flooding the chat


def parse_args(args):
    """'goguardian,lightspeed 3' -> ('goguardian,lightspeed', 3). A number is the link count, anything
    else is a filter name (commas or spaces both work). No arguments uses the config defaults."""
    defaults = CONFIG["linkgen"]
    filters, count = [], None
    for word in args:
        if word.isdigit():
            count = int(word)
        else:
            filters += [f for f in re.split(r"[,\s]+", word.lower()) if f]
    if count is not None and not 1 <= count <= MAX_LINKS:
        return None, None, f"Ask for between 1 and {MAX_LINKS} links"
    bad = [f for f in filters if not re.fullmatch(r"[a-z0-9_-]{1,32}", f)]
    if bad:
        return None, None, f"Filter names are letters, numbers, - and _ (not {bad[0]})"
    return (",".join(dict.fromkeys(filters)) or defaults["filters"]), (count or defaults["links"]), None


def handle_linkgen(args):
    p = prefix()
    filters, count, err = parse_args(args)
    if err:
        return r_warn(f"{err}. Usage: {p}linkgen [filters] [count], like {p}linkgen goguardian 2")
    try:
        r = session.get(
            LINKGEN_URL, params={"links": count, "filters": filters},
            headers={"referer": LINKGEN_REFERER}, timeout=20,
        )
    except requests.RequestException as e:
        return r_err(f"Couldn't reach the link generator: {e}")
    if r.status_code == 401:
        return r_err("The site rejected your session (401)")
    if r.status_code == 429:
        return r_err("The link generator is rate limiting you (429), try again in a bit")
    if r.status_code >= 400:
        return r_err(f"The link generator answered {r.status_code}: {r.text.strip()[:120]}")
    try:
        data = r.json()
    except ValueError:
        return r_err("The link generator sent something that isn't JSON")

    links = [l for l in data.get("links") or [] if isinstance(l, dict) and l.get("url")]
    problems = [str(e) for e in data.get("errors") or []]
    if not data.get("ok", True) and not links:
        return r_err("The link generator said no" + (": " + "; ".join(problems) if problems else ""))
    if not links:
        return r_warn("No links came back" + (": " + "; ".join(problems) if problems else ""))

    shown = ",".join(data.get("requested_filters") or filters.split(","))
    lines = [f"{len(links)} link{'s' if len(links) != 1 else ''} ({shown})"]
    for l in links:
        detail = ", ".join(x for x in (l.get("type"), l.get("domain")) if x)
        lines.append(l["url"] + (f"  [{detail}]" if detail else ""))
    if problems:
        lines.append("⚠️ " + "; ".join(problems))
    return r_info("\n".join(lines), emoji="🔗")
