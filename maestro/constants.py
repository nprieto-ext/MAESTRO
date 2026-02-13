"""
Constantes et configuration pour Maestro.py
"""

APP_NAME = "Maestro.py"
VERSION = "2.5.0"

# Mapping des couleurs RGB vers les vélocités AKAI APC mini
AKAI_COLOR_MAP = {
    # Blanc/Jaune (pas de vrai blanc sur AKAI)
    "white": 5,      # Jaune vif (le plus proche du blanc)
    # Rouge
    "red": 3,        # Rouge vif
    # Orange
    "orange": 9,     # Orange vif
    # Jaune
    "yellow": 13,    # Jaune-vert vif
    # Vert
    "green": 25,     # Vert lime vif
    # Cyan/Bleu
    "cyan": 37,      # Cyan
    "blue": 45,      # Bleu
    # Violet/Magenta
    "violet": 53,    # Violet vif
    "magenta": 49,   # Rose/Magenta vif
}
