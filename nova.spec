# Recette PyInstaller de Nova : construit dist\Nova\Nova.exe (mode dossier).
#
#     .venv\Scripts\pyinstaller nova.spec --noconfirm --clean
#
# Mode dossier plutôt qu'un exe unique : démarrage plus rapide (rien à décompresser
# à chaque lancement de Windows), moins de faux positifs d'antivirus, et les DLL de
# Qt restent remplaçables, comme le demande leur licence LGPL.

import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH)
VERSION = re.search(
    r'__version__ = "([\d.]+)"', (ROOT / "src" / "nova" / "__init__.py").read_text("utf-8")
).group(1)
NUMBERS = tuple(int(part) for part in VERSION.split(".")) + (0,)

# Informations affichées par Windows (propriétés du fichier, Gestionnaire des tâches).
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040C04B0",  # français, Unicode
                    [
                        StringStruct("CompanyName", "yxnss"),
                        StringStruct("FileDescription", "Nova"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", "Nova"),
                        StringStruct("LegalCopyright", "© 2026 yxnss, licence MIT"),
                        StringStruct("OriginalFilename", "Nova.exe"),
                        StringStruct("ProductName", "Nova"),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
    ],
)

a = Analysis(
    [str(ROOT / "src" / "nova" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "assets" / "logo_small.png"), "assets"),
        (str(ROOT / "src" / "nova" / "ui" / "theme" / "nova.qss"), "nova/ui/theme"),
    ],
    # Chiffrement (SSL) : Nova ne fait aucune connexion réseau.
    excludes=["tkinter", "_ssl", "_hashlib"],
)

# Éléments de Qt inutiles à Nova, retirés pour alléger le dossier :
# - rendu OpenGL logiciel (environ 20 Mo) : Nova n'utilise pas OpenGL ;
# - chiffrement réseau (TLS) et informations réseau : aucune connexion réseau ;
# - traductions de Qt autres que le français.
UNUSED = ("opengl32sw", "libcrypto", "libssl", "plugins\\tls", "plugins\\networkinformation")


def is_needed(entry) -> bool:
    destination = entry[0].lower().replace("/", "\\")
    if any(part in destination for part in UNUSED):
        return False
    return "translations" not in destination or destination.endswith("qtbase_fr.qm")


a.binaries = [entry for entry in a.binaries if is_needed(entry)]
a.datas = [entry for entry in a.datas if is_needed(entry)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Nova",
    icon=str(ROOT / "assets" / "nova.ico"),
    version=version_info,
    console=False,  # application fenêtrée : pas de console noire
    upx=False,  # la compression UPX déclenche souvent les antivirus
)
coll = COLLECT(exe, a.binaries, a.datas, name="Nova", upx=False)
