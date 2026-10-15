"""Métadonnées d'un exécutable Windows (nom du produit, description).

Elles servent à proposer un nom lisible (« Fortnite ») plutôt que le nom du
fichier (« FortniteClient-Win64-Shipping »). Lecture via l'API Windows
« version.dll », appelée avec ctypes (module standard, sans pywin32).
"""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

_FIELDS = ("ProductName", "FileDescription")
# Langues de repli si l'exe ne déclare pas les siennes : anglais US et français.
_FALLBACK_TRANSLATIONS = [(0x0409, 0x04B0), (0x0409, 0x04E4), (0x040C, 0x04B0)]
_TRADEMARKS = str.maketrans("", "", "™®©")
# Noms qui désignent un moteur ou un lanceur, pas le jeu (constatés sur de vrais jeux).
_GENERIC_NAMES = {"unreal engine", "bootstrappackagedgame", "unity", "unity player"}
# Suffixes techniques ajoutés par les moteurs au nom du fichier.
_TECHNICAL_SUFFIXES = ("-win64-shipping", "-win32-shipping", "-shipping", "_be", "_eac")


def suggest_display_name(exe_path: str | Path) -> str:
    """Nom lisible proposé pour un jeu, à partir de son exécutable."""
    return pick_display_name(read_version_strings(exe_path), Path(exe_path).stem)


def pick_display_name(version_strings: dict[str, str], file_stem: str) -> str:
    """Choisit le meilleur nom parmi les métadonnées, sinon nettoie le nom du fichier.

    FileDescription passe en premier : chez Unreal, ProductName vaut souvent
    « Unreal Engine », et chez Windows « Système d'exploitation Microsoft Windows ».
    """
    for field in ("FileDescription", "ProductName"):
        name = " ".join(version_strings.get(field, "").translate(_TRADEMARKS).split())
        if name and name.casefold() not in _GENERIC_NAMES:
            return name
    stem = file_stem
    for suffix in _TECHNICAL_SUFFIXES:
        if stem.casefold().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem or file_stem


def _load_version_api():
    if sys.platform != "win32":
        return None
    api = ctypes.WinDLL("version")
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    api.GetFileVersionInfoW.restype = wintypes.BOOL
    api.VerQueryValueW.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.UINT),
    ]
    api.VerQueryValueW.restype = wintypes.BOOL
    return api


_api = _load_version_api()


def read_version_strings(path: str | Path) -> dict[str, str]:
    """Renvoie ProductName et FileDescription de l'exe, quand ils existent."""
    if _api is None:
        return {}
    path = str(path)
    size = _api.GetFileVersionInfoSizeW(path, None)
    if not size:
        return {}
    buffer = ctypes.create_string_buffer(size)
    if not _api.GetFileVersionInfoW(path, 0, size, buffer):
        return {}

    pointer, length = ctypes.c_void_p(), wintypes.UINT()

    def query(sub_block: str) -> bool:
        found = _api.VerQueryValueW(buffer, sub_block, ctypes.byref(pointer), ctypes.byref(length))
        return bool(found) and length.value > 0

    translations = []
    if query(r"\VarFileInfo\Translation"):
        count = length.value // 4  # chaque entrée : langue (2 octets) + page de code (2 octets)
        words = (wintypes.WORD * (count * 2)).from_address(pointer.value)
        translations = [(words[2 * i], words[2 * i + 1]) for i in range(count)]

    result = {}
    for field in _FIELDS:
        for language, codepage in translations + _FALLBACK_TRANSLATIONS:
            if query(rf"\StringFileInfo\{language:04x}{codepage:04x}\{field}"):
                value = ctypes.wstring_at(pointer.value, length.value).rstrip("\x00").strip()
                if value:
                    result[field] = value
                    break
    return result
