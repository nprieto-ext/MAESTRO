"""
IA de génération de show lumineux pour Maestro.py
"""

from PySide6.QtGui import QColor


class AudioColorAI:
    """IA qui génère un show lumineux professionnel"""
    def __init__(self):
        self.current_hue = 0
        self.beat_counter = 0
        self.tempo = 120
        self.last_beat_time = 0
        self.current_scene = 0
        self.scenes = [
            {"contre": "red", "face": "white", "lat": "blue", "douche": "orange"},
            {"contre": "blue", "face": "white", "lat": "red", "douche": "cyan"},
            {"contre": "green", "face": "white", "lat": "magenta", "douche": "yellow"},
            {"contre": "magenta", "face": "white", "lat": "green", "douche": "red"},
        ]

    def get_color_from_name(self, name):
        colors = {
            "red": QColor(255, 0, 0),
            "blue": QColor(0, 100, 255),
            "green": QColor(0, 255, 100),
            "white": QColor(255, 255, 255),
            "orange": QColor(255, 140, 0),
            "cyan": QColor(0, 255, 255),
            "magenta": QColor(255, 0, 255),
            "yellow": QColor(255, 255, 0),
        }
        return colors.get(name, QColor(255, 255, 255))

    def update_show(self, volume, elapsed_ms):
        beat_interval = 60000 / self.tempo
        if elapsed_ms - self.last_beat_time >= beat_interval:
            self.last_beat_time = elapsed_ms
            self.beat_counter += 1
            if self.beat_counter % 32 == 0:
                self.current_scene = (self.current_scene + 1) % len(self.scenes)
        is_strong_beat = self.beat_counter % 4 in [0, 2]
        return self.scenes[self.current_scene], is_strong_beat
