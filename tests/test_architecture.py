"""Garde-fous d'architecture : vérifie les règles de dépendance entre les couches.

Chaque fichier est analysé (sans être exécuté) pour lister ses imports. Si une
couche importe un module qui lui est interdit, le test échoue et indique le fichier.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

# Modules interdits pour chaque couche (voir la docstring de chaque paquet).
FORBIDDEN_IMPORTS = {
    "core": ("PySide6", "sqlite3", "nova.data", "nova.services", "nova.system", "nova.ui"),
    "data": ("PySide6", "nova.services", "nova.system", "nova.ui"),
}


def imported_modules(path: Path, src_root: Path = SRC) -> set[str]:
    """Renvoie le nom complet de chaque module importé par un fichier."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    # Paquet du fichier, ex. "nova.core" : sert à résoudre les imports relatifs.
    package_parts = path.relative_to(src_root).with_suffix("").parts[:-1]
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                modules.add(node.module or "")
            else:
                base = list(package_parts[: len(package_parts) - (node.level - 1)])
                modules.add(".".join(base + ([node.module] if node.module else [])))
    return modules


def is_forbidden(module: str, forbidden: tuple[str, ...]) -> bool:
    return any(module == name or module.startswith(name + ".") for name in forbidden)


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_IMPORTS))
def test_layer_respects_its_import_rules(layer: str) -> None:
    files = sorted((SRC / "nova" / layer).rglob("*.py"))
    assert files, f"le paquet nova.{layer} est introuvable"
    for path in files:
        bad = sorted(m for m in imported_modules(path) if is_forbidden(m, FORBIDDEN_IMPORTS[layer]))
        assert not bad, f"{path.relative_to(SRC)} importe {bad}"


def test_detects_forbidden_relative_import(tmp_path: Path) -> None:
    """Vérifie que le garde-fou repère aussi un import relatif vers une autre couche."""
    fake = tmp_path / "nova" / "core" / "tracker.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("from ..ui import main_window\n", encoding="utf-8")
    modules = imported_modules(fake, src_root=tmp_path)
    assert modules == {"nova.ui"}
    assert is_forbidden("nova.ui", FORBIDDEN_IMPORTS["core"])
