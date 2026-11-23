"""?ai: asking Gemini, plus the terminal-side key and model management."""
import os
import re
import time

import requests

from axion.config import save_config
from axion.constants import GEMINI_BASE
from axion.state import CONFIG, STATE
from axion.ui import ask, print_error, print_warning, r_err, r_ok, r_warn, spin


def get_ai_key():
    return CONFIG["gemini_api_key"] or os.environ.get("GEMINI_API_KEY", "")


def gemini_headers():
    # Only the API key goes to Google, never the bikesense cookie
    return {"x-goog-api-key": get_ai_key(), "content-type": "application/json"}


def clean_reply(text, max_chars):
    """Plain text only, one line, never longer than max_chars."""
    text = re.sub(r"[*`]", "", text)
    text = re.sub(r"(?m)^\s*#+\s*", "", text)
    text = " ".join(text.split())
    if len(text) > max_chars:
        cut = text[:max_chars]
        space = cut.rfind(" ")
        text = cut[:space] if space > max_chars * 0.6 else cut
    return text.strip()


def ask_gemini(prompt):
    """Asks Gemini. Returns a Reply, level ok for an answer and error or warn for a problem."""
    if not get_ai_key():
        return r_warn("AI is not set up yet, add the API key in the terminal with aikey")
    ai = CONFIG["ai"]
    system = ai["system_prompt"].replace("{max_chars}", str(ai["max_chars"]))
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt[:1000]}]}],
    }
    try:
        with spin("Asking Gemini"):
            r = requests.post(
                f"{GEMINI_BASE}/models/{ai['model']}:generateContent",
                headers=gemini_headers(),
                json=body,
                timeout=20,
            )
    except requests.RequestException as e:
        print_error(f"Gemini request failed: {e}")
        return r_err("AI request failed, try again")
    if r.status_code != 200:
        print_error(f"Gemini returned {r.status_code}: {r.text[:200]}")
        return r_err(f"AI error ({r.status_code})")
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    except (KeyError, IndexError, TypeError, ValueError):
        print_warning(f"Gemini gave no usable answer: {r.text[:200]}")
        return r_warn("AI gave no answer for that")
    text = clean_reply(text, ai["max_chars"])
    return r_ok(text, emoji="") if text else r_warn("AI gave no answer for that")


def ai_wait(user):
    return CONFIG["ai"]["cooldown"] - (time.time() - STATE["ai_last"].get(user, 0))


def set_ai_key(args):
    if args and args[0].lower() == "remove":
        CONFIG["gemini_api_key"] = ""
        save_config()
        return r_ok("API key removed")
    try:
        key = ask("Gemini API key (hidden, leave empty to cancel)", secret=True)
    except (EOFError, KeyboardInterrupt):
        return r_warn("Cancelled")
    if not key:
        return r_warn("Cancelled")
    CONFIG["gemini_api_key"] = key
    save_config()
    return r_ok("API key saved to secrets.json")


def fetch_ai_models():
    """Returns (model names, None) or (None, error Reply)."""
    if not get_ai_key():
        return None, r_warn("Set the API key first with aikey")
    names, token = [], None
    try:
        for _ in range(5):  # a few pages is plenty
            params = {"pageSize": 100}
            if token:
                params["pageToken"] = token
            r = requests.get(f"{GEMINI_BASE}/models", headers=gemini_headers(), params=params, timeout=15)
            if r.status_code != 200:
                return None, r_err(f"Could not list models ({r.status_code}): {r.text[:150]}")
            data = r.json()
            for m in data.get("models", []):
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    names.append(m["name"].removeprefix("models/"))
            token = data.get("nextPageToken")
            if not token:
                break
    except (requests.RequestException, ValueError) as e:
        return None, r_err(f"Could not list models: {e}")
    return sorted(names), None


def set_ai_model(name):
    name = name.strip().removeprefix("models/")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
        return r_err("That does not look like a model name")
    note = ""
    if get_ai_key():
        try:
            with spin("Checking model"):
                r = requests.get(f"{GEMINI_BASE}/models/{name}", headers=gemini_headers(), timeout=15)
            if r.status_code == 404:
                return r_err(f"Model {name} was not found, use aimodels to see what is available")
            if r.status_code != 200:
                note = f" (could not verify it, status {r.status_code})"
        except requests.RequestException:
            note = " (could not verify it, network error)"
    CONFIG["ai"]["model"] = name
    save_config()
    return r_ok(f"Model set to {name}{note}")
