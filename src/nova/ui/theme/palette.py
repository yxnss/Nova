"""Couleurs de Nova, tirées du logo. Toute couleur de l'interface vient d'ici.

La feuille de style ``nova.qss`` y fait référence par leur nom (``@accent``), et le
code Python les lit dans ``COLORS`` (icône générique, pastille « en cours »).
"""

COLORS = {
    # Surfaces, de la plus sombre à la plus claire.
    "background": "#0E0B16",  # fond général : anthracite teinté de violet
    "panel": "#15111F",  # barre latérale, fenêtres secondaires
    "card": "#1E1830",  # cartes, champs de saisie
    "hover": "#241D36",  # survol
    "border": "#2A2340",
    "border_strong": "#4A3A75",
    # Violets du logo.
    "night": "#0B0128",  # fond du disque du logo, départ de la bannière par défaut
    "deep_violet": "#3E05C2",
    "selection": "#2B1466",  # élément sélectionné
    "accent": "#7D27FA",  # action principale, sélection, focus
    "accent_hover": "#9338FA",
    "accent_pressed": "#5B16C9",
    "lilac": "#C77FFC",
    # Textes.
    "text": "#F3EEFB",
    "text_secondary": "#A99BC4",
    "text_muted": "#6E6487",
    # États.
    "running": "#3DDC97",  # jeu en cours : vert doux, distinct du violet de sélection
    "running_background": "#12261F",
    "running_border": "#1F5A43",
    "danger": "#F26D7D",
}
