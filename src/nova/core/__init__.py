"""Moteur de suivi : détection des processus, sessions, gestion de la veille.

Règle d'architecture : ce paquet n'importe ni PySide6, ni sqlite3, ni les autres
couches de Nova. Il reste ainsi testable sans interface ni base de données.
"""
