"""Reads facts about the device the bot runs on. Every reader returns None when it cannot know."""
import json
import os
import platform
import shutil
import subprocess


def platform_name():
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.isdir("/data/data/com.termux"):
        return "Android (Termux)"
    system = platform.system()
    return {"Windows": "Windows", "Linux": "Linux", "Darwin": "macOS"}.get(system, system or "Unknown")


def read_battery():
    """Battery info, needs the Termux:API app and `pkg install termux-api`. None if unavailable."""
    try:
        out = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=10).stdout
        return json.loads(out)
    except Exception:
        return None


def read_memory():
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) * 1024
        total = info["MemTotal"]
        return total - info.get("MemAvailable", info.get("MemFree", 0)), total
    except Exception:
        return None


def read_storage():
    try:
        du = shutil.disk_usage(os.path.expanduser("~"))
        return du.used, du.total
    except Exception:
        return None


def read_load():
    try:
        return os.getloadavg()
    except Exception:
        return None


def read_uptime():
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:
        return None
