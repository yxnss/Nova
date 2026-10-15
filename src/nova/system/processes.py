"""Liste des programmes en cours, pour ajouter un jeu en le choisissant parmi eux.

Utilisée seulement à l'ouverture de la fenêtre d'ajout, jamais pendant le suivi.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True)
class RunningProgram:
    process_name: str  # en minuscules, ex. « fortniteclient-win64-shipping.exe »
    exe_path: str
    memory: int  # octets utilisés par le plus gros de ses processus


def list_running_programs(exclude_pids: set[int] | None = None) -> list[RunningProgram]:
    """Programmes en cours, un par exécutable, du plus gourmand en mémoire au moins gourmand.

    Un jeu utilise bien plus de mémoire que ses lanceurs : il arrive donc en tête.
    Les programmes de Windows (dossier système) et les PID exclus ne sont pas listés.
    """
    excluded = exclude_pids or set()
    system_folders = _system_folders()
    psutil.process_iter.cache_clear()
    programs: dict[str, RunningProgram] = {}
    for process in psutil.process_iter(["exe", "memory_info"]):
        exe = process.info["exe"]
        if process.pid in excluded or not _is_listable(exe, system_folders):
            continue
        memory_info = process.info["memory_info"]
        memory = memory_info.rss if memory_info else 0
        key = exe.casefold()
        known = programs.get(key)
        if known is None or memory > known.memory:
            programs[key] = RunningProgram(Path(exe).name.lower(), exe, memory)
    return sorted(programs.values(), key=lambda program: program.memory, reverse=True)


def _system_folders() -> tuple[str, ...]:
    """Dossiers de Windows et de ses composants (antivirus…), jamais proposés comme jeux."""
    windows = os.environ.get("SystemRoot", r"C:\Windows")
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    folders = (windows, os.path.join(program_data, "Microsoft"))
    return tuple(folder.casefold().rstrip("\\") + "\\" for folder in folders)


def _is_listable(exe: str | None, system_folders: tuple[str, ...]) -> bool:
    # Certains processus du système (« Registry », « MemCompression ») n'ont pas de
    # vrai chemin : seul un vrai fichier .exe peut être un jeu.
    if not exe or not exe.casefold().endswith(".exe") or not os.path.isabs(exe):
        return False
    return not exe.casefold().startswith(system_folders)
