"""
Classe Projector pour la gestion des projecteurs DMX
"""
from PySide6.QtGui import QColor


class Projector:
    """Represente un projecteur avec son etat (niveau, couleur, mute)"""

    def __init__(self, group):
        self.group = group
        self.level = 0
        self.base_color = QColor("white")
        self.color = QColor("black")
        self.dmx_mode = "Manuel"
        self.muted = False

    def set_color(self, color, brightness=None):
        """Definit la couleur de base et recalcule la couleur effective"""
        self.base_color = color
        if brightness is not None:
            self.level = brightness

        if self.level > 0:
            factor = self.level / 100.0
            self.color = QColor(
                int(self.base_color.red() * factor),
                int(self.base_color.green() * factor),
                int(self.base_color.blue() * factor)
            )
        else:
            self.color = QColor(0, 0, 0)

    def set_level(self, level):
        """Definit le niveau de luminosite"""
        self.level = max(0, min(100, level))
        self.set_color(self.base_color)

    def toggle_mute(self):
        """Bascule l'etat mute"""
        self.muted = not self.muted
        return self.muted

    def get_dmx_rgb(self):
        """Retourne les valeurs RGB pour DMX (0-255)"""
        if self.muted or self.level == 0:
            return (0, 0, 0)
        return (self.color.red(), self.color.green(), self.color.blue())

    def __repr__(self):
        return f"Projector({self.group}, level={self.level}, muted={self.muted})"
