"""
Fonctions utilitaires pour Maestro.py
"""

from PySide6.QtGui import QColor


def rgb_to_akai_velocity(qcolor):
    """Convertit une QColor RGB en vélocité AKAI (approximation)"""
    r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()

    # Détection par couleur HTML (plus précis)
    hex_color = qcolor.name().lower()

    # Mapping exact des couleurs du simulateur
    color_map = {
        "#ffffff": 3,   # Blanc → Rouge vif (interverti avec ligne 2)
        "#ff0000": 5,   # Rouge → Jaune (interverti avec ligne 1)
        "#ff8800": 9,   # Orange → Orange vif (9)
        "#ffdd00": 13,  # Jaune → Jaune vif (13)
        "#00ff00": 21,  # Vert → Vert vif (21)
        "#00dddd": 37,  # Cyan → Cyan (37)
        "#0000ff": 45,  # Bleu → Bleu (45)
        "#ff00ff": 53,  # Magenta/Violet → Violet (53)
    }

    # Chercher la couleur exacte
    if hex_color in color_map:
        return color_map[hex_color]

    # Sinon, approximation par dominante
    # Blanc (toutes composantes élevées)
    if r > 200 and g > 200 and b > 200:
        return 5  # Jaune vif (proche du blanc)

    # Rouge dominant
    if r > 150 and g < 150 and b < 150:
        return 3  # Rouge pur

    # Orange (rouge + vert moyen)
    if r > 200 and g > 100 and g < 200 and b < 100:
        return 9  # Orange

    # Jaune (rouge + vert)
    if r > 200 and g > 200 and b < 100:
        return 13  # Jaune

    # Vert dominant
    if g > 150 and r < 150 and b < 150:
        return 21  # Vert

    # Cyan (vert + bleu)
    if g > 150 and b > 150 and r < 100:
        return 37  # Cyan

    # Bleu dominant
    if b > 150 and r < 150 and g < 150:
        return 45  # Bleu

    # Magenta (rouge + bleu)
    if r > 150 and b > 150 and g < 100:
        return 53  # Violet/Magenta

    # Par défaut
    return 5
