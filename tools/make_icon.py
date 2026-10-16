"""Génère, à partir de ``assets/logo.png`` (1254 px) :

- ``assets/nova.ico`` : icône de l'exe. Un .ico contient la même image à plusieurs
  tailles, et Windows choisit la bonne selon l'endroit (barre des tâches, bureau…) ;
- ``assets/logo_small.png`` : logo de 256 px utilisé par l'application (plus léger à
  charger et en mémoire que l'original, et bien assez grand pour l'interface).

À relancer seulement si le logo change :

    .venv\\Scripts\\python tools\\make_icon.py
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

logo = Image.open(ROOT / "assets" / "logo.png").convert("RGBA")
logo.save(ROOT / "assets" / "nova.ico", sizes=[(size, size) for size in SIZES])
logo.resize((256, 256), Image.Resampling.LANCZOS).save(
    ROOT / "assets" / "logo_small.png", optimize=True
)
print(f"assets/nova.ico ({len(SIZES)} tailles) et assets/logo_small.png créés")
