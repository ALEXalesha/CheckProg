import json
import os
import sys
from typing import NamedTuple

from checkprog import APP_NAME
from checkprog.model import write_json_atomic

PORTABLE_MARKER = "portable.flag"


class Paths(NamedTuple):
    settings_file: str
    lists_dir: str
    portable: bool


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _documents_dir():
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            # CSIDL_PERSONAL follows OneDrive/folder redirection, unlike ~/Documents.
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except (AttributeError, OSError):
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def resolve_paths(base_dir=None, appdata=None, documents=None):
    base = os.path.abspath(base_dir or app_dir())
    if os.path.isfile(os.path.join(base, PORTABLE_MARKER)):
        return Paths(os.path.join(base, "settings.json"), os.path.join(base, "lists"), True)
    appdata = appdata or os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming")
    documents = documents or _documents_dir()
    return Paths(os.path.join(appdata, APP_NAME, "settings.json"),
                 os.path.join(documents, APP_NAME), False)


def load_settings(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write_json_atomic(path, data)
    except OSError:
        return False
    return True
