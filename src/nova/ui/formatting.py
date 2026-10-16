"""Mise en forme des durées et des dates pour l'affichage (fonctions pures, testées)."""

import unicodedata
from datetime import datetime

_MONTHS = [
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
]
_THIN_SPACE = " "  # espace fine insécable, séparateur de milliers en français


def format_duration(seconds: float) -> str:
    """Durée de jeu : « 0 min », « moins d'une minute », « 45 min », « 3 h 05 min »…"""
    if seconds <= 0:
        return "0 min"  # jamais joué
    minutes = int(seconds // 60)
    if minutes < 1:
        return "moins d'une minute"
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    hours_text = f"{hours:,}".replace(",", _THIN_SPACE)
    return f"{hours_text} h {minutes:02d} min"


def format_last_played(timestamp: float | None, now: float) -> str:
    """Dernière utilisation : « Jamais », « Aujourd'hui à 14:05 », « Hier à 22:10 »…"""
    if timestamp is None:
        return "Jamais"
    moment = datetime.fromtimestamp(timestamp)
    days_ago = (datetime.fromtimestamp(now).date() - moment.date()).days
    if days_ago <= 0:
        return f"Aujourd'hui à {moment:%H:%M}"
    if days_ago == 1:
        return f"Hier à {moment:%H:%M}"
    if days_ago < 7:
        return f"Il y a {days_ago} jours"
    return f"{moment.day} {_MONTHS[moment.month - 1]} {moment.year}"


def format_elapsed(seconds: float) -> str:
    """Compteur de la session en cours : « 0:05:12 », « 1:23:45 »."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def format_clock(timestamp: float) -> str:
    """Heure locale « 14:05 »."""
    return f"{datetime.fromtimestamp(timestamp):%H:%M}"


def sort_key(text: str) -> str:
    """Clé de tri alphabétique : sans accents ni majuscules (« Élan » se range avec « elan »)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
