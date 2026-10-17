"""Petits appels à l'API Windows (via ctypes, module standard)."""

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

APP_USER_MODEL_ID = "Nova.GameTimeTracker"


def set_app_user_model_id() -> None:
    """Donne à Nova sa propre identité dans la barre des tâches.

    Sans cela, pendant le développement, Windows regroupe la fenêtre avec Python et
    affiche l'icône de Python au lieu de celle de Nova.
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except OSError:
        log.warning("Impossible de définir l'identité de Nova dans la barre des tâches")


def allow_any_process_to_take_focus() -> None:
    """Autorise la première instance de Nova à passer au premier plan.

    Windows interdit à un programme en arrière-plan de voler le focus : sans cet
    appel, la fenêtre réveillée se contenterait de clignoter dans la barre des
    tâches. La nouvelle instance, lancée par l'utilisateur, a le droit de céder
    ce privilège juste avant de demander le réveil.
    """
    if sys.platform != "win32":
        return
    asfw_any = 0xFFFFFFFF  # ASFW_ANY : n'importe quel processus
    ctypes.windll.user32.AllowSetForegroundWindow(asfw_any)


# --- Barre de titre intégrée à la fenêtre ---
#
# La fenêtre principale dessine elle-même sa barre de titre. Pour garder les
# comportements de Windows (déplacement, aimantation aux bords, redimensionnement,
# animations, ombre), la fenêtre garde son cadre natif, mais Nova annonce à Windows
# que toute la fenêtre est une zone « cliente » qu'elle dessine (WM_NCCALCSIZE),
# puis lui indique où se trouvent la barre de titre et les bords (WM_NCHITTEST).

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084

# Réponses à WM_NCHITTEST : ce qui se trouve sous la souris.
HTCLIENT = 1
HTCAPTION = 2  # barre de titre : déplacer, double-clic pour agrandir
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WS_MINIMIZEBOX = 0x00020000
_WS_MAXIMIZEBOX = 0x00010000
_SWP_FRAMECHANGED_ONLY = 0x0020 | 0x0002 | 0x0001 | 0x0004 | 0x0010  # sans bouger ni activer
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWCP_ROUND = 2
_MONITOR_DEFAULTTONEAREST = 2


class _Margins(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_int),
        ("right", ctypes.c_int),
        ("top", ctypes.c_int),
        ("bottom", ctypes.c_int),
    ]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _colorref(hex_color: str) -> wintypes.DWORD:
    """Convertit « #RRGGBB » au format COLORREF de Windows (0x00BBGGRR)."""
    red, green, blue = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return wintypes.DWORD(red | green << 8 | blue << 16)


def _set_dwm_attribute(hwnd: int, attribute: int, value: wintypes.DWORD) -> None:
    # Les attributs de couleur et d'angles n'existent que sous Windows 11 : ailleurs,
    # l'appel échoue sans conséquence.
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value)
    )


def prepare_custom_title_bar(hwnd: int, border_color: str) -> None:
    """Rend à une fenêtre sans cadre Qt les comportements d'une fenêtre Windows normale."""
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    hwnd_value = wintypes.HWND(hwnd)
    style = user32.GetWindowLongW(hwnd_value, _GWL_STYLE)
    style |= _WS_CAPTION | _WS_THICKFRAME | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX
    user32.SetWindowLongW(hwnd_value, _GWL_STYLE, style)
    # Une ligne de cadre « étendue » suffit pour que Windows dessine l'ombre.
    margins = _Margins(0, 0, 1, 0)
    ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd_value, ctypes.byref(margins))
    _set_dwm_attribute(hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, wintypes.DWORD(_DWMWCP_ROUND))
    _set_dwm_attribute(hwnd, _DWMWA_BORDER_COLOR, _colorref(border_color))
    # Windows recalcule le cadre avec le nouveau style.
    user32.SetWindowPos(hwnd_value, None, 0, 0, 0, 0, _SWP_FRAMECHANGED_ONLY)


def set_caption_color(hwnd: int, color: str) -> None:
    """Colore la barre de titre native d'une fenêtre (Windows 11), pour la fondre au fond."""
    if sys.platform == "win32":
        _set_dwm_attribute(hwnd, _DWMWA_CAPTION_COLOR, _colorref(color))


def read_message(address: int) -> wintypes.MSG:
    """Lit le message Windows reçu par ``nativeEvent``."""
    return wintypes.MSG.from_address(address)


def is_maximized(hwnd: int) -> bool:
    # Demandé à Windows : pendant un agrandissement, Qt ne le sait pas encore.
    return bool(ctypes.windll.user32.IsZoomed(wintypes.HWND(hwnd)))


def cursor_offset(message: wintypes.MSG) -> tuple[int, int]:
    """Position de la souris d'un WM_NCHITTEST dans la zone dessinée par Nova.

    Le résultat est en pixels physiques, depuis le coin haut gauche de cette zone. On ne
    part pas du coin de la fenêtre : agrandie, elle déborde de l'écran de quelques
    pixels, et tout serait décalé (le coin de l'écran tomberait hors du bouton Fermer).
    """
    # La position à l'écran est rangée dans lParam : deux entiers signés de 16 bits
    # (négatifs sur un écran placé à gauche ou au-dessus de l'écran principal).
    x = ctypes.c_short(message.lParam & 0xFFFF).value
    y = ctypes.c_short((message.lParam >> 16) & 0xFFFF).value
    point = wintypes.POINT(x, y)
    ctypes.windll.user32.ScreenToClient(wintypes.HWND(message.hWnd), ctypes.byref(point))
    return point.x, point.y


def fill_client_area(message: wintypes.MSG) -> None:
    """Répond à WM_NCCALCSIZE : la zone dessinée par Nova couvre toute la fenêtre.

    Agrandie, une fenêtre Windows déborde de l'écran de l'épaisseur de son cadre : sa
    zone est alors ramenée à l'espace de travail de l'écran (sans la barre des tâches).
    """
    if not message.wParam or not is_maximized(message.hWnd):
        return  # le rectangle proposé (toute la fenêtre) convient tel quel
    rect = wintypes.RECT.from_address(message.lParam)  # premier rectangle de NCCALCSIZE_PARAMS
    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.restype = wintypes.HMONITOR  # un handle, pas un simple entier
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    monitor = user32.MonitorFromWindow(message.hWnd, _MONITOR_DEFAULTTONEAREST)
    info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
    if user32.GetMonitorInfoW(wintypes.HMONITOR(monitor), ctypes.byref(info)):
        rect.left, rect.top = info.rcWork.left, info.rcWork.top
        rect.right, rect.bottom = info.rcWork.right, info.rcWork.bottom
