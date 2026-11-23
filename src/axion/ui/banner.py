"""The startup banner."""
import platform

from axion.constants import AUTHOR, AXION_VERSION
from axion.state import cookie, target_user
from axion.utils.sysinfo import platform_name

from .output import emit, print_kv, print_separator, print_warning
from .theme import C_BRAND, C_DIM, C_OK, C_USER, C_WARN, colorama, paint


def print_banner():
    art = [
        r"    _   __  __ ___  ___  _  _ ",
        r"   /_\  \ \/ /|_ _|/ _ \| \| |",
        r"  / _ \  >  <  | || (_) | .` |",
        r" /_/ \_\/_/\_\|___|\___/|_|\_|",
    ]
    emit("")
    for line in art:
        emit(paint(line, C_BRAND, bold=True))
    emit(paint(" A C H R O M A   T O O L K I T", C_DIM))
    emit("")
    signed_in = "achroma-chat=" in cookie()
    print_kv([
        ("Version", f"v{AXION_VERSION}"),
        ("Author", AUTHOR),
        ("Platform", platform_name()),
        ("Python", platform.python_version()),
        ("Account", (target_user(), C_USER) if signed_in and target_user() else ("guest", C_DIM)),
        ("Session", ("signed in", C_OK) if signed_in else ("not signed in", C_WARN)),
    ])
    print_separator()
    if colorama is None:
        print_warning("colorama is not installed, running without colors. Install it with: pip install colorama")
