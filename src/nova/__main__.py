"""Point d'entrée : ``python -m nova`` lance l'application, ``--version`` affiche la version."""

import argparse

from nova import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nova", description="Suivi du temps de jeu.")
    parser.add_argument("--version", action="store_true", help="affiche la version et quitte")
    args = parser.parse_args(argv)
    if args.version:
        print(f"Nova {__version__}")
        return 0
    # Import tardif : Qt n'est chargé que pour lancer réellement l'application.
    from nova.app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
