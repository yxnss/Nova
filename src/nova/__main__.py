"""Point d'entrée : ``python -m nova``.

Pour l'instant, il affiche seulement la version. L'application sera branchée ici
aux étapes suivantes.
"""

from nova import __version__


def main() -> int:
    print(f"Nova {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
