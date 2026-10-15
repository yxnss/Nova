"""Script console pour vérifier le suivi avec de vrais jeux (étape 2 du plan).

Exemples, depuis le dossier du projet :

    .venv\\Scripts\\python tools\\probe_tracking.py find valorant
    .venv\\Scripts\\python tools\\probe_tracking.py add VALORANT-Win64-Shipping.exe --name Valorant
    .venv\\Scripts\\python tools\\probe_tracking.py run
    .venv\\Scripts\\python tools\\probe_tracking.py stats

Les essais utilisent une base séparée (``probe.db`` dans %APPDATA%\\Nova) pour ne
pas se mélanger avec la vraie bibliothèque de Nova.
"""

import argparse
import logging
import signal
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCore import QCoreApplication, QTimer

from nova.core.events import GameStarted, GameStopped
from nova.core.scanner import PsutilScanner
from nova.data.database import connect
from nova.data.games_repo import DuplicateGameError, GameRepository, normalize_process_name
from nova.data.sessions_repo import RepairReport
from nova.data.stats import load_stats
from nova.services.tracking import TrackingService
from nova.system.logging_setup import setup_logging
from nova.system.paths import data_dir, logs_dir


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def format_time(timestamp: float | None) -> str:
    if timestamp is None:
        return "jamais"
    return datetime.fromtimestamp(timestamp).strftime("%d/%m %H:%M:%S")


def game_names(conn: sqlite3.Connection) -> dict[int, str]:
    return {game.id: game.display_name for game in GameRepository(conn).list_all()}


# --- Commandes ---


def cmd_find(args: argparse.Namespace) -> None:
    """Liste les processus dont le nom contient le texte, et ce que Nova sait en lire."""
    text = args.text.lower()
    psutil.process_iter.cache_clear()
    names: set[str] = set()
    unreadable = 0
    for process in psutil.process_iter(["name"]):
        name = process.info["name"]
        if name is None:
            unreadable += 1
        elif text in name.lower():
            names.add(name.lower())

    if not names:
        print(f"Aucun processus en cours ne contient « {args.text} ».")
    scanner = PsutilScanner()  # exactement ce que Nova utilise pendant le suivi
    for name in sorted(names):
        pids = scanner.find({name})[name]
        alive = scanner.still_running(pids)
        print(f"\n{name}")
        for pid in sorted(pids):
            path = scanner.exe_path(pid)
            print(f"  PID {pid:>6}  chemin : {path or 'ILLISIBLE (processus protégé ?)'}")
        print(f"  Vérification légère des PID : {len(alive)}/{len(pids)} vus en cours")
    print(f"\nProcessus dont le nom est illisible sur ce PC : {unreadable}")


def cmd_add(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    name = normalize_process_name(args.process)
    display = args.name or Path(name).stem
    try:
        game = GameRepository(conn).add(name, display, added_at=time.time())
    except DuplicateGameError:
        print(f"{name} est déjà dans la liste.")
    else:
        print(f"Ajouté : {game.display_name} ({game.process_name}), id {game.id}")
    conn.close()


def cmd_remove(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    games = GameRepository(conn)
    name = normalize_process_name(args.process)
    matches = [game for game in games.list_all() if game.process_name == name]
    if not matches:
        print(f"{name} n'est pas dans la liste.")
    for game in matches:
        games.delete(game.id)
        print(f"Retiré avec son historique : {game.display_name}")
    conn.close()


def cmd_list(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    games = GameRepository(conn).list_all()
    if not games:
        print("Aucun jeu. Ajoutez-en un avec : add <nom.exe>")
    for game in games:
        print(
            f"{game.id:>3}  {game.display_name:<20} {game.process_name:<40} {game.exe_path or '-'}"
        )
    conn.close()


def cmd_stats(args: argparse.Namespace) -> None:
    conn = connect(args.db)
    names = game_names(conn)
    stats = load_stats(conn, time.time())
    for game_id, s in stats.items():
        print(
            f"{names[game_id]:<20} total {format_duration(s.total_seconds):>14}"
            f" | 7 jours {format_duration(s.last_7_days_seconds):>14}"
            f" | dernière fois : {format_time(s.last_played_at)}"
        )
    sessions = conn.execute(
        "SELECT game_id, started_at, ended_at FROM sessions ORDER BY started_at DESC LIMIT 10"
    ).fetchall()
    if sessions:
        print("\nDernières sessions :")
    for row in sessions:
        end = row["ended_at"]
        length = format_duration(end - row["started_at"]) if end else "ouverte"
        print(
            f"  {names[row['game_id']]:<20} {format_time(row['started_at'])}"
            f" -> {format_time(end)}  ({length})"
        )
    conn.close()


def cmd_run(args: argparse.Namespace) -> None:
    """Lance le vrai thread de suivi et affiche les événements jusqu'au Ctrl+C."""
    app = QCoreApplication(sys.argv[:1])
    conn = connect(args.db)
    names = game_names(conn)
    conn.close()
    if not names:
        print("Aucun jeu à suivre. Ajoutez-en un avec : add <nom.exe>")
        return

    def on_ready(report: RepairReport) -> None:
        print(f"Suivi démarré pour : {', '.join(names.values())}")
        if report.closed or report.deleted:
            print(
                f"  Réparé au démarrage : {report.closed} clôturée(s),"
                f" {report.deleted} supprimée(s)"
            )
        print("  Lancez ou fermez un jeu. Ctrl+C pour arrêter proprement.\n")

    def on_started(event: GameStarted) -> None:
        path = event.exe_path or "ILLISIBLE (processus protégé ?)"
        print(f"{format_time(event.started_at)}  DÉMARRÉ  {names[event.game_id]}  [{path}]")

    def on_stopped(event: GameStopped) -> None:
        length = format_duration(event.ended_at - event.started_at)
        note = "" if event.counted else " - ignorée car trop courte"
        print(
            f"{format_time(event.ended_at)}  ARRÊTÉ   {names[event.game_id]}"
            f" ({event.reason}) après {length}{note}"
        )

    service = TrackingService(args.db)
    service.ready.connect(on_ready)
    service.game_started.connect(on_started)
    service.game_stopped.connect(on_stopped)
    service.game_path_found.connect(
        lambda game_id, path: print(f"  Chemin enregistré pour {names[game_id]} : {path}")
    )

    # Qt garde la main pendant qu'il attend des événements, et Python ne voit alors pas
    # le Ctrl+C : ce minuteur rend la main à Python quatre fois par seconde.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    wake_up = QTimer()
    wake_up.timeout.connect(lambda: None)
    wake_up.start(250)

    service.start()
    app.exec()
    print("\nArrêt : clôture des sessions en cours…")
    service.stop()
    app.processEvents()  # affiche les derniers événements du thread de suivi
    print()
    cmd_stats(args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vérifie le suivi de Nova avec de vrais jeux.")
    parser.add_argument(
        "--db", type=Path, default=None, help="base à utiliser (par défaut : probe.db)"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    find = commands.add_parser("find", help="cherche un processus en cours par morceau de nom")
    find.add_argument("text")
    find.set_defaults(func=cmd_find)

    add = commands.add_parser("add", help="ajoute un jeu par son nom de processus")
    add.add_argument("process")
    add.add_argument("--name", help="nom affiché (par défaut : nom de l'exe)")
    add.set_defaults(func=cmd_add)

    remove = commands.add_parser("remove", help="retire un jeu et son historique")
    remove.add_argument("process")
    remove.set_defaults(func=cmd_remove)

    commands.add_parser("list", help="liste les jeux suivis").set_defaults(func=cmd_list)
    commands.add_parser("stats", help="affiche les statistiques").set_defaults(func=cmd_stats)
    commands.add_parser("run", help="lance le suivi en direct").set_defaults(func=cmd_run)

    args = parser.parse_args()
    if args.db is None:
        args.db = data_dir() / "probe.db"
    # Une sortie redirigée vers un fichier utilise l'encodage de Windows (cp1252) :
    # un caractère impossible à écrire y est remplacé au lieu de faire planter le script.
    sys.stdout.reconfigure(errors="replace")
    setup_logging(logs_dir(), console_level=logging.WARNING)
    args.func(args)


if __name__ == "__main__":
    main()
