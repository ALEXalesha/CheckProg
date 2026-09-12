import sys
from typing import NamedTuple

try:
    import winreg
except ImportError:
    winreg = None

MODES = ("system", "light", "dark")
MODE_LABELS = {"system": "Как в системе", "light": "Светлая", "dark": "Тёмная"}
_PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_WIN = sys.platform == "win32"


class Palette(NamedTuple):
    ttk_theme: str
    bg: str
    fg: str
    field: str
    muted: str
    done_fg: str
    border: str
    select_bg: str
    select_fg: str
    heading_bg: str
    menu_bar_bg: str
    menu_bg: str
    menu_fg: str
    menu_active_bg: str
    menu_active_fg: str
    check_off_fill: str
    check_off_border: str
    accent: str


# The light theme keeps the native "vista" look; ttk colors are left alone and
# only the widgets Tk draws itself (menus, labels, tags, images) use these values.
LIGHT = Palette(
    ttk_theme="vista",
    bg="SystemButtonFace" if _WIN else "#f0f0f0",
    fg="SystemButtonText" if _WIN else "#000000",
    field="SystemWindow" if _WIN else "#ffffff",
    muted="gray40",
    done_fg="gray50",
    border="SystemButtonShadow" if _WIN else "#a0a0a0",
    select_bg="SystemHighlight" if _WIN else "#0078d7",
    select_fg="SystemHighlightText" if _WIN else "#ffffff",
    heading_bg="SystemButtonFace" if _WIN else "#f0f0f0",
    menu_bar_bg="SystemButtonFace" if _WIN else "#f0f0f0",
    menu_bg="SystemMenu" if _WIN else "#ffffff",
    menu_fg="SystemMenuText" if _WIN else "#000000",
    menu_active_bg="SystemHighlight" if _WIN else "#0078d7",
    menu_active_fg="SystemHighlightText" if _WIN else "#ffffff",
    check_off_fill="#ffffff",
    check_off_border="#8a8a8a",
    accent="#2e7d32",
)

DARK = Palette(
    ttk_theme="clam",
    bg="#202020",
    fg="#e6e6e6",
    field="#2b2b2b",
    muted="#9a9a9a",
    done_fg="#8c8c8c",
    border="#3f3f3f",
    select_bg="#3a6ea5",
    select_fg="#ffffff",
    heading_bg="#262626",
    menu_bar_bg="#202020",
    menu_bg="#2b2b2b",
    menu_fg="#e6e6e6",
    menu_active_bg="#3a6ea5",
    menu_active_fg="#ffffff",
    check_off_fill="#2b2b2b",
    check_off_border="#a0a0a0",
    accent="#43a047",
)


def normalize_mode(value):
    return value if isinstance(value, str) and value in MODES else "system"


def resolve(mode, system_dark):
    mode = normalize_mode(mode)
    if mode == "system":
        return "dark" if system_dark else "light"
    return mode


def palette_for(name):
    return DARK if name == "dark" else LIGHT


def system_prefers_dark():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return False
    return type(value) is int and value == 0


def set_title_bar_dark(window, dark):
    if not _WIN:
        return False
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            return False  # not mapped yet; the caller retries on <Map>
        value = ctypes.c_int(1 if dark else 0)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE; 19 on Windows 10 builds before 20H1.
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
            if result == 0:
                # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED: repaint the frame now.
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
                return True
    except Exception:  # purely cosmetic: never let the title bar break the app
        return False
    return False
