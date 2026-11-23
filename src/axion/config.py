"""Saving the config. Secrets go to secrets.json (mode 600), everything else to config.json."""
import json
import os

from .constants import CONFIG_PATH, SECRET_KEYS, SECRETS_PATH
from .state import CONFIG, NEEDS_MIGRATION, target_user
from .ui import print_error, print_info


def write_json(path, data, private=False):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        if private:
            os.chmod(path, 0o600)
    except OSError as e:
        print_error(f"Could not save {os.path.basename(path)}: {e}")


def sync_active_account():
    """Keeps the active account's cookie and profile stored under "accounts"."""
    acc = CONFIG.setdefault("accounts", {}).setdefault(target_user(), {})
    acc["cookie"] = CONFIG["cookie"]
    acc["profile"] = dict(CONFIG["profile"])


def save_config():
    sync_active_account()
    secrets = {k: CONFIG[k] for k in SECRET_KEYS if k in CONFIG}
    public = {k: v for k, v in CONFIG.items() if k not in SECRET_KEYS}
    # Blank placeholders keep config.json the same shape while staying safe to commit
    public = {"cookie": "", **public, "quickacc_password": ""}
    write_json(CONFIG_PATH, public)
    write_json(SECRETS_PATH, secrets, private=True)


def startup():
    """Run once before anything else: makes sure the active account is stored, and moves
    secrets out of an old config.json."""
    sync_active_account()
    if NEEDS_MIGRATION:
        save_config()
        print_info("Moved your secrets out of config.json into secrets.json")
