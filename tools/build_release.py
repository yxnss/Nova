"""Construit Nova.exe puis l'archive à publier : ``dist/Nova-<version>-windows.zip``.

.venv\\Scripts\\python tools\\build_release.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nova import __version__  # noqa: E402

DIST = ROOT / "dist"
APP = DIST / "Nova"


def main() -> None:
    pyinstaller = Path(sys.executable).with_name("pyinstaller.exe")
    subprocess.run(
        [str(pyinstaller), "nova.spec", "--noconfirm", "--clean", "--log-level", "WARN"],
        cwd=ROOT,
        check=True,
    )
    # Licences à côté de Nova.exe, comme l'exigent la licence MIT et la LGPL de Qt.
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, APP / name)
    archive = shutil.make_archive(
        str(DIST / f"Nova-{__version__}-windows"), "zip", root_dir=DIST, base_dir="Nova"
    )
    size = Path(archive).stat().st_size / 2**20
    print(f"Archive prête : {Path(archive).relative_to(ROOT)} ({size:.1f} Mo)")


if __name__ == "__main__":
    main()
