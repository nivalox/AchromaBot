"""?stats: device statistics as chat text."""
import os
import platform
import time

from axion.ui import r_info
from axion.utils.fmt import fmt_bytes, fmt_duration
from axion.utils.sysinfo import read_battery, read_load, read_memory, read_storage, read_uptime

START_TIME = time.time()


def get_stats():
    """Stats for the chat, one topic per line."""
    lines = []
    b = read_battery()
    if b:
        lines.append(
            f"🔋 Battery: {b.get('percentage')}% ({str(b.get('status', '?')).lower()}, "
            f"plugged: {b.get('plugged', '?')})"
        )
        lines.append(f"🌡️ Battery temp: {b.get('temperature')} C, health: {b.get('health')}")
    else:
        lines.append("🔋 Battery: unavailable (install Termux:API and termux-api)")

    mem = read_memory()
    lines.append(f"🧠 RAM: {fmt_bytes(mem[0])} / {fmt_bytes(mem[1])} used" if mem else "🧠 RAM: unavailable")
    disk = read_storage()
    lines.append(f"💾 Storage: {fmt_bytes(disk[0])} / {fmt_bytes(disk[1])} used" if disk else "💾 Storage: unavailable")

    cpu = f"⚙️ CPU: {os.cpu_count()} cores"
    load = read_load()
    if load:
        cpu += f", load {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}"
    lines.append(cpu)
    up = read_uptime()
    if up is not None:
        lines.append(f"⏱️ Device uptime: {fmt_duration(up)}")

    lines.append(f"🐍 Python {platform.python_version()}, bot up {fmt_duration(time.time() - START_TIME)}")
    return r_info("Device stats\n" + "\n".join(lines), emoji="📊")
