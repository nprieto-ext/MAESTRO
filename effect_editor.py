"""
Editeur d'effets lumineux — MyStrow
Dialog de création, configuration et assignation d'effets AKAI.
"""
import copy
import json
import math
import random
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QLineEdit, QComboBox, QSlider, QSpinBox,
    QColorDialog, QFrame, QMessageBox, QSizePolicy, QGridLayout,
    QMenuBar, QMenu, QFileDialog, QStyle, QApplication,
    QCheckBox, QDoubleSpinBox,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QLinearGradient, QAction, QKeySequence

EFFECTS_FILE = Path.home() / ".mystrow_effects.json"

# ──────────────────────────────────────────────────────────────────────────────
# 22 EFFETS BUILT-IN
# ──────────────────────────────────────────────────────────────────────────────
BUILTIN_EFFECTS = [
    # ── Strobe / Flash ────────────────────────────────────────────────────────
    {"name": "Strobe Classique",   "type": "Strobe", "category": "Strobe / Flash",
     "speed": 55, "target": "all",       "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Strobe Lent",        "type": "Strobe", "category": "Strobe / Flash",
     "speed": 15, "target": "all",       "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Strobe Rapide",      "type": "Strobe", "category": "Strobe / Flash",
     "speed": 90, "target": "all",       "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Strobe Alternance",  "type": "Strobe", "category": "Strobe / Flash",
     "speed": 60, "target": "alternate", "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Strobe Pairs",       "type": "Strobe", "category": "Strobe / Flash",
     "speed": 60, "target": "even",      "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Flash Couleur",      "type": "Flash",  "category": "Strobe / Flash",
     "speed": 50, "target": "all",       "color_mode": "base",    "custom_color": "#ffffff", "builtin": True},
    {"name": "Flash Blanc",        "type": "Flash",  "category": "Strobe / Flash",
     "speed": 55, "target": "all",       "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    # ── Mouvement ─────────────────────────────────────────────────────────────
    {"name": "Chase Blanc",        "type": "Chase",  "category": "Mouvement",
     "speed": 50, "target": "all",       "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Chase Rapide",       "type": "Chase",  "category": "Mouvement",
     "speed": 96, "target": "lr",        "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Chase Retour",       "type": "Chase",  "category": "Mouvement",
     "speed": 50, "target": "rl",        "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Comète",             "type": "Comete", "category": "Mouvement",
     "speed": 50, "target": "all",       "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    {"name": "Étoile Filante",     "type": "Etoile Filante", "category": "Mouvement",
     "speed": 50, "target": "all",       "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
    # ── Ambiance ──────────────────────────────────────────────────────────────
    {"name": "Pulse Doux",         "type": "Pulse",  "category": "Ambiance",
     "speed": 30, "target": "all",       "color_mode": "base",    "custom_color": "#ffffff", "builtin": True},
    {"name": "Pulse Rapide",       "type": "Pulse",  "category": "Ambiance",
     "speed": 92, "target": "all",       "color_mode": "base",    "custom_color": "#ffffff", "builtin": True},
    {"name": "Pulse Décalé",       "type": "Pulse",  "category": "Ambiance",
     "speed": 40, "target": "alternate", "color_mode": "base",    "custom_color": "#ffffff", "builtin": True},
    {"name": "Vague",              "type": "Wave",   "category": "Ambiance",
     "speed": 45, "target": "all",       "color_mode": "base",    "custom_color": "#ffffff", "builtin": True},
    # ── Couleur ───────────────────────────────────────────────────────────────
    {"name": "Rainbow",            "type": "Rainbow","category": "Couleur",
     "speed": 45, "target": "all",       "color_mode": "rainbow", "custom_color": "#ffffff", "builtin": True},
    {"name": "Rainbow Rapide",     "type": "Rainbow","category": "Couleur",
     "speed": 85, "target": "all",       "color_mode": "rainbow", "custom_color": "#ffffff", "builtin": True},
    {"name": "Feu",                "type": "Fire",   "category": "Couleur",
     "speed": 50, "target": "all",       "color_mode": "fire",    "custom_color": "#ff4400", "builtin": True},
    # ── Spécial ───────────────────────────────────────────────────────────────
    {"name": "Bascule",            "type": "Bascule","category": "Spécial",
     "speed": 0,  "target": "all",       "color_mode": "base",    "custom_color": "#ffffff", "builtin": True},
    {"name": "Flash Custom",       "type": "Flash",  "category": "Spécial",
     "speed": 55, "target": "all",       "color_mode": "custom",  "custom_color": "#00aaff", "builtin": True},
    {"name": "Chase Custom",       "type": "Chase",  "category": "Spécial",
     "speed": 50, "target": "all",       "color_mode": "custom",  "custom_color": "#ff00aa", "builtin": True},
]

EFFECT_TYPES = ["Strobe", "Flash", "Pulse", "Wave", "Chase",
                "Comete", "Etoile Filante", "Rainbow", "Fire", "Bascule"]  # legacy

PROJECTOR_GROUPS = ["face", "douche1", "douche2", "douche3", "lat", "contre"]  # legacy

PATTERNS = [
    ("Tous",               "all"),
    ("Pairs",              "even"),
    ("Impairs",            "odd"),
    ("Alternance",         "alternate"),
    ("Gauche → Droite",    "lr"),
    ("Droite → Gauche",    "rl"),
]  # legacy

COLOR_MODES = [
    ("Couleur de base",    "base"),
    ("Blanc",              "white"),
    ("Noir",               "black"),
    ("Arc-en-ciel",        "rainbow"),
    ("Feu",                "fire"),
    ("Couleur custom",     "custom"),
]  # legacy

TYPE_COLORS = {
    "Strobe": "#ffffff", "Flash": "#ffff44", "Pulse": "#dd44ff",
    "Wave": "#00ffff",   "Chase": "#e0e0e0", "Comete": "#ff8800",
    "Etoile Filante": "#aaddff", "Rainbow": "#00ff88",
    "Fire": "#ff4400",   "Bascule": "#44ccff",
}  # legacy

# Attributs DMX utilisés par chaque type d'effet  # legacy
EFFECT_ATTRS = {
    "Strobe":         [{"attr": "DIMMER",  "mode": "Absolu", "shape": "Carré"},
                       {"attr": "SHUTTER", "mode": "Absolu", "shape": "Carré"}],
    "Flash":          [{"attr": "DIMMER",  "mode": "Absolu", "shape": "Impulsion"},
                       {"attr": "COULEUR", "mode": "Absolu", "shape": "Impulsion"}],
    "Pulse":          [{"attr": "DIMMER",  "mode": "Absolu", "shape": "Sinus"}],
    "Wave":           [{"attr": "DIMMER",  "mode": "Absolu", "shape": "Sinus décalé"}],
    "Chase":          [{"attr": "DIMMER",  "mode": "Absolu", "shape": "Chase"}],
    "Comete":         [{"attr": "DIMMER",  "mode": "Absolu", "shape": "Impulsion"}],
    "Etoile Filante": [{"attr": "DIMMER",  "mode": "Absolu", "shape": "Décroissant"}],
    "Rainbow":        [{"attr": "COULEUR", "mode": "Absolu", "shape": "Arc-en-ciel"}],
    "Fire":           [{"attr": "COULEUR", "mode": "Absolu", "shape": "Aléatoire"},
                       {"attr": "DIMMER",  "mode": "Absolu", "shape": "Aléatoire"}],
    "Bascule":        [{"attr": "DIMMER",  "mode": "Absolu", "shape": "Carré"},
                       {"attr": "COULEUR", "mode": "Absolu", "shape": "Carré"}],
}  # legacy

# ── Nouveau modèle Attribut/Forme ─────────────────────────────────────────────
CHANNEL_TYPES_ORDER = [
    "Dim", "R", "G", "B", "W", "Strobe", "UV", "Pan", "Tilt", "Zoom",
    "Iris", "Gobo1", "Gobo2", "Focus", "ColorWheel", "Shutter", "Speed",
    "Mode", "Smoke", "Fan", "Ambre", "Orange", "PanFine", "TiltFine", "Prism",
]

SHAPES = [
    ("Chase",           "chase"),
    ("Toujours au max", "max"),
    ("Toujours au min", "min"),
    ("Phase 1",         "phase1"),
    ("Phase 2",         "phase2"),
    ("Phase 3",         "phase3"),
    ("Sinusoïdale",     "sine"),
    ("Pause",           "pause"),
    ("Off",             "off"),
    ("Son",             "sound"),
]

GROUP_DISPLAY_FALLBACK = {
    "face":    "Groupe A",
    "lat":     "Groupe B",
    "contre":  "Groupe C",
    "douche1": "Groupe D",
    "douche2": "Groupe E",
    "douche3": "Groupe F",
    "public":  "Groupe G",
}

_TYPE_TO_ATTR  = {
    "Strobe": "Strobe", "Flash": "Dim",  "Pulse": "Dim",  "Wave": "Dim",
    "Chase":  "Dim",    "Comete":"Dim",  "Etoile Filante":"Dim",
    "Rainbow":"R",      "Fire":  "Dim",  "Bascule":"Dim",
}

_TYPE_TO_SHAPE = {
    "Strobe": "chase",  "Flash": "max",    "Pulse": "sine",   "Wave":  "phase2",
    "Chase":  "chase",  "Comete":"chase",  "Etoile Filante":  "chase",
    "Rainbow":"phase1", "Fire":  "sound",  "Bascule":"max",
}

_TARGET_TO_TYPE = {
    "all": "all", "even": "even", "odd": "odd",
    "alternate": "all", "lr": "all", "rl": "all",
}

def _speed_label(speed: int) -> str:
    if speed < 20: return "Très lent"
    if speed < 40: return "Lent"
    if speed < 60: return "Modéré"
    if speed < 80: return "Rapide"
    return "Très rapide"


# ── Helpers nouveau modèle ─────────────────────────────────────────────────────

def _get_available_attributes(projectors) -> list:
    """Union des profils DMX du patch courant, dans l'ordre canonique."""
    attrs = set()
    for p in projectors:
        profile = getattr(p, "_dmx_profile", [])
        attrs.update(profile)
    if not attrs:
        try:
            for p in projectors:
                ft = getattr(p, "fixture_template", None)
                if ft and "profile" in ft:
                    attrs.update(ft["profile"])
        except Exception:
            pass
    if not attrs:
        attrs = {"Dim", "R", "G", "B", "Strobe"}
    return [c for c in CHANNEL_TYPES_ORDER if c in attrs]


def _get_display_groups(projectors) -> dict:
    """Retourne {group_key: display_name} pour chaque groupe présent dans le patch."""
    seen = {}
    for p in projectors:
        g = p.group
        if g not in seen:
            seen[g] = GROUP_DISPLAY_FALLBACK.get(g, g.capitalize())
    return seen


def _migrate_layer(layer: dict) -> dict:
    """Convertit l'ancien format vers le nouveau modèle attribut/forme."""
    if "attribute" in layer and "shape" in layer:
        # Déjà nouveau format — compléter les champs manquants
        return {
            "attribute":     layer.get("attribute", "Dim"),
            "shape":         layer.get("shape", "sine"),
            "target_type":   layer.get("target_type", "all"),
            "target_groups": layer.get("target_groups", []),
            "speed":         layer.get("speed", 50),
            "amplitude":     layer.get("amplitude", 100),
            "val_max":       layer.get("val_max", 100),
            "val_min":       layer.get("val_min", 0),
            "muted":         layer.get("muted", False),
        }
    old_type   = layer.get("type", "Pulse")
    old_target = layer.get("target", "all")
    use_fixed  = layer.get("use_fixed_groups", False)
    return {
        "attribute":     _TYPE_TO_ATTR.get(old_type, "Dim"),
        "shape":         _TYPE_TO_SHAPE.get(old_type, "sine"),
        "target_type":   _TARGET_TO_TYPE.get(old_target, "all"),
        "target_groups": layer.get("fixed_groups", []) if use_fixed else [],
        "speed":         layer.get("speed", 50),
        "amplitude":     layer.get("amplitude", 100),
        "val_max":       100,
        "val_min":       0,
        "muted":         layer.get("muted", False),
    }

_MENU_STYLE = """
QMenuBar {
    background: #0a0a0a;
    color: #ccc;
    border-bottom: 1px solid #222;
    padding: 2px 4px;
    font-size: 12px;
}
QMenuBar::item { padding: 5px 12px; background: transparent; border-radius: 3px; }
QMenuBar::item:selected { background: #1e1e1e; color: #fff; }
QMenu {
    background: #1a1a1a;
    color: #e0e0e0;
    border: 1px solid #00d4ff55;
    padding: 4px;
    font-size: 12px;
}
QMenu::item { padding: 7px 28px; border-radius: 3px; }
QMenu::item:selected { background: #00d4ff; color: #000; }
QMenu::separator { background: #333; height: 1px; margin: 4px 8px; }
"""

_STYLE = """
QDialog, QWidget  { background: #141414; color: #e0e0e0; font-family: 'Segoe UI', Arial; }
QLabel            { border: none; background: transparent; }
QLineEdit         { background: #1e1e1e; border: 1px solid #333; border-radius: 4px;
                    padding: 5px 8px; color: #fff; }
QLineEdit:focus   { border-color: #00d4ff66; }
QComboBox         { background: #1e1e1e; border: 1px solid #333; border-radius: 4px;
                    padding: 5px 8px; color: #e0e0e0; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #1e1e1e; color: #e0e0e0;
    selection-background-color: #00d4ff; selection-color: #000; border: 1px solid #333; }
QScrollArea       { border: none; }
QScrollBar:vertical { background: #111; width: 8px; border-radius: 4px; }
QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 4px; min-height: 20px; }
QSlider::groove:horizontal { background: #2a2a2a; height: 5px; border-radius: 2px; }
QSlider::handle:horizontal { background: #00d4ff; width: 14px; height: 14px;
                              border-radius: 7px; margin: -5px 0; }
QSlider::sub-page:horizontal { background: #00d4ff44; border-radius: 2px; }
QPushButton       { background: #222; border: 1px solid #333; border-radius: 5px;
                    padding: 5px 14px; color: #ccc; }
QPushButton:hover { background: #282828; border-color: #00d4ff; color: #fff; }
QPushButton:disabled { background: #1a1a1a; color: #444; border-color: #222; }
QFrame[frameShape="4"] { background: #2a2a2a; }
QSpinBox         { background: #1e1e1e; border: 1px solid #333; border-radius: 4px;
                   padding: 2px 4px; color: #00d4ff; font-weight: bold; font-size: 11px; }
QSpinBox::up-button, QSpinBox::down-button { width: 14px; background: #2a2a2a; border: none; }
QSpinBox:focus   { border-color: #00d4ff66; }
"""


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def _eff_layers(eff: dict) -> list:
    """Retourne la liste des couches d'un effet (compat legacy sans 'layers'), migrées."""
    if "layers" in eff:
        return [_migrate_layer(l) for l in copy.deepcopy(eff["layers"])]
    raw = {
        "type":             eff.get("type", "Pulse"),
        "speed":            eff.get("speed", 50),
        "amplitude":        eff.get("amplitude", 100),
        "phase":            eff.get("phase", 0),
        "fade":             eff.get("fade", 0),
        "muted":            eff.get("muted", False),
        "use_fixed_groups": eff.get("use_fixed_groups", False),
        "fixed_groups":     eff.get("fixed_groups", []),
        "target":           eff.get("target", "all"),
        "color_mode":       eff.get("color_mode", "base"),
        "custom_color":     eff.get("custom_color", "#ffffff"),
    }
    return [_migrate_layer(raw)]


def _dmx_info_for_type(eff_type: str):
    """Retourne (canaux_dmx, formes) sous forme de texte pour affichage inline."""
    attrs = EFFECT_ATTRS.get(eff_type, [])
    if not attrs:
        return "—", "—"
    return (" · ".join(a["attr"] for a in attrs),
            " · ".join(a["shape"] for a in attrs))


# ──────────────────────────────────────────────────────────────────────────────
# KNOB WIDGET
# ──────────────────────────────────────────────────────────────────────────────
class KnobWidget(QWidget):
    """Potentiomètre circulaire 42×50px — arc cyan proportionnel à la valeur."""

    valueChanged = Signal(int)

    def __init__(self, label="", min_val=0, max_val=100, default=0, parent=None):
        super().__init__(parent)
        self.setFixedSize(42, 50)
        self._min   = min_val
        self._max   = max_val
        self._val   = max(min_val, min(max_val, default))
        self._label = label
        self._drag_y = None
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip(f"{label}: {self._val}")

    def value(self) -> int:
        return self._val

    def setValue(self, v: int):
        v = max(self._min, min(self._max, int(v)))
        if v != self._val:
            self._val = v
            self.setToolTip(f"{self._label}: {self._val}")
            self.update()
            self.valueChanged.emit(v)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_y = event.globalPosition().y()

    def mouseMoveEvent(self, event):
        if self._drag_y is not None:
            dy = self._drag_y - event.globalPosition().y()
            self._drag_y = event.globalPosition().y()
            rng = self._max - self._min
            delta = int(dy / 80.0 * rng)
            if delta != 0:
                self.setValue(self._val + delta)

    def mouseReleaseEvent(self, event):
        self._drag_y = None

    def wheelEvent(self, event):
        delta = 1 if event.angleDelta().y() > 0 else -1
        self.setValue(self._val + delta)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        knob_h = h - 14
        cx, cy = w // 2, knob_h // 2
        radius = min(cx, cy) - 3

        START_ANGLE = 225
        SPAN = 270

        # Background arc
        pen = QPen(QColor("#2a2a2a"), 4, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(
            int(cx - radius), int(cy - radius),
            int(radius * 2), int(radius * 2),
            int(START_ANGLE * 16), int(-SPAN * 16),
        )

        # Cyan arc proportional to value
        rng = self._max - self._min
        ratio = (self._val - self._min) / rng if rng else 0
        cyan_span = int(SPAN * ratio)
        if cyan_span > 0:
            pen2 = QPen(QColor("#00d4ff"), 4, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen2)
            p.drawArc(
                int(cx - radius), int(cy - radius),
                int(radius * 2), int(radius * 2),
                int(START_ANGLE * 16), int(-cyan_span * 16),
            )

        # Indicator dot
        dot_angle_deg = START_ANGLE - cyan_span
        dot_rad = math.radians(dot_angle_deg)
        dot_x = cx + radius * math.cos(dot_rad)
        dot_y = cy - radius * math.sin(dot_rad)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#00d4ff") if cyan_span > 0 else QColor("#555")))
        p.drawEllipse(int(dot_x - 3), int(dot_y - 3), 6, 6)

        # Value at centre
        p.setPen(QPen(QColor("#e0e0e0")))
        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
        p.drawText(0, int(cy - radius * 0.4), w, int(radius * 0.9),
                   Qt.AlignCenter, str(self._val))

        # Label below
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QPen(QColor("#555")))
        p.drawText(0, h - 14, w, 14, Qt.AlignCenter, self._label)
        p.end()


# ──────────────────────────────────────────────────────────────────────────────
# MINI PREVIEW
# ──────────────────────────────────────────────────────────────────────────────
class MiniPreviewWidget(QWidget):
    """8 cercles animés montrant l'effet en temps réel (multi-couches)."""

    N = 8
    BASE = QColor(200, 100, 30)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setMinimumWidth(300)
        self._layers = []
        self._layer_states = []
        self._colors = [QColor("#1a1a1a")] * self.N

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_config(self, cfg: dict):
        """Compat legacy — wraps single config in a layers list."""
        self.set_layers(_eff_layers(cfg) if cfg else [])

    def set_layers(self, layers: list):
        """Charge de nouvelles couches ET réinitialise tous les états (changement d'effet)."""
        self._layers = layers
        while len(self._layer_states) < len(layers):
            self._layer_states.append({"state": 0, "brightness": 0.0, "brightness_dir": 1, "hue": 0, "angle": 0.0})
        self._layer_states = self._layer_states[:len(layers)]
        for st in self._layer_states:
            st["state"] = 0
            st["brightness"] = 0.0
            st["brightness_dir"] = 1
            st["hue"] = 0
            st["angle"] = 0.0

    def update_layers_config(self, layers: list):
        """Met à jour les configs des couches SANS réinitialiser les états d'animation (édition live)."""
        self._layers = layers
        while len(self._layer_states) < len(layers):
            self._layer_states.append({"state": 0, "brightness": 0.0, "brightness_dir": 1, "hue": 0, "angle": 0.0})
        self._layer_states = self._layer_states[:len(layers)]

    def _resolve(self, idx: int, cfg: dict, st: dict) -> QColor:
        mode   = cfg.get("color_mode", "base")
        custom = cfg.get("custom_color", "#ffffff")
        if mode == "white":  return QColor(255, 255, 255)
        if mode == "black":  return QColor(0, 0, 0)
        if mode == "custom": return QColor(custom)
        if mode == "fire":
            return random.choice([QColor(255, 50, 0), QColor(255, 100, 0),
                                   QColor(255, 150, 0), QColor(255, 200, 0)])
        if mode == "rainbow":
            return QColor.fromHsv((st["hue"] + idx * 30) % 360, 255, 220)
        return QColor(self.BASE)

    def _active(self, cfg: dict) -> list:
        target = cfg.get("target", "all")
        n = self.N
        if target == "even": return [i for i in range(n) if i % 2 == 0]
        if target == "odd":  return [i for i in range(n) if i % 2 == 1]
        if target == "rl":   return list(reversed(range(n)))
        return list(range(n))

    def _compute_layer(self, cfg: dict, st: dict) -> list:
        t         = cfg.get("type", "Pulse")
        speed     = cfg.get("speed", 50)
        amplitude = cfg.get("amplitude", 100)
        phase     = cfg.get("phase", 0)
        fade_v    = cfg.get("fade", 0)
        target    = cfg.get("target", "all")
        amp       = amplitude / 100.0
        ph        = phase / 100.0
        fd        = fade_v / 100.0
        n         = self.N
        colors    = [QColor(0, 0, 0)] * n
        black     = QColor(0, 0, 0)
        act       = self._active(cfg)
        n_act     = len(act) or 1

        if t in ("Strobe", "Flash"):
            # Phase : décale le déclenchement de chaque projecteur
            for idx2, i in enumerate(act):
                offset = int(ph * (idx2 / n_act) * 4)
                on = (st["state"] + offset) % 2 == 0
                c  = self._resolve(i, cfg, st)
                bv = amp
                colors[i] = QColor(int(c.red()*bv), int(c.green()*bv), int(c.blue()*bv)) if on else black
            st["state"] += 1

        elif t == "Pulse":
            # Angle continu (évite le rebond, permet le phasage inter-projecteur)
            step = 1 + int(speed / 12)
            st["angle"] = st.get("angle", 0.0) + step * math.pi / 100.0
            for idx2, i in enumerate(act):
                ang_i = st["angle"] + ph * (idx2 / n_act) * 2 * math.pi
                norm  = (ang_i % (2 * math.pi)) / (2 * math.pi)
                tri   = 1.0 - abs(2 * norm - 1)          # triangulaire 0→1→0
                sine  = (1 - math.cos(ang_i)) / 2         # sinusoïde   0→1→0
                b_base = tri * (1 - fd) + sine * fd        # blend fade
                b_final = b_base * amp                     # amplitude totale
                c = self._resolve(i, cfg, st)
                colors[i] = QColor(int(c.red()*b_final), int(c.green()*b_final), int(c.blue()*b_final))

        elif t == "Wave":
            for idx2, i in enumerate(act):
                ph_off = ph * (idx2 / n_act) * 50         # déphasage par projecteur
                raw    = (st["state"] + idx2 * 15 + ph_off) % 100
                tri    = abs(50 - raw) / 50.0
                smooth = (1 - math.cos(raw / 100.0 * 2 * math.pi)) / 2
                b_base  = tri * (1 - fd) + smooth * fd
                b_final = b_base * amp
                c = self._resolve(i, cfg, st)
                colors[i] = QColor(int(c.red()*b_final), int(c.green()*b_final), int(c.blue()*b_final))
            st["state"] += 1 + int(speed / 14)

        elif t == "Chase":
            if act:
                trail = int(ph * n_act * 0.6)              # longueur de traîne (phase)
                pos   = st["state"] % n_act
                for idx2, i in enumerate(act):
                    c    = self._resolve(i, cfg, st)
                    dist = (pos - idx2) % n_act
                    if dist == 0:
                        brightness = amp
                    elif trail > 0 and dist <= trail:
                        t_frac = dist / (trail + 1)
                        lin    = 1.0 - t_frac
                        cos_f  = math.cos(t_frac * math.pi / 2)
                        trail_b = lin * (1 - fd) + cos_f * fd
                        brightness = trail_b * amp
                    else:
                        brightness = 0
                    colors[i] = QColor(int(c.red()*brightness), int(c.green()*brightness), int(c.blue()*brightness))
            st["state"] += 1

        elif t == "Comete":
            TAIL = 3
            pos = st["state"] % (n + TAIL)
            for i in range(n):
                dist = pos - i
                c = self._resolve(i, cfg, st)
                if dist == 0:
                    colors[i] = QColor(255, 255, 255)
                elif 1 <= dist <= TAIL:
                    blend = (1.0 - dist / (TAIL + 1)) * 0.88
                    colors[i] = QColor(
                        min(255, int(c.red()   + (255 - c.red())   * blend)),
                        min(255, int(c.green() + (255 - c.green()) * blend)),
                        min(255, int(c.blue()  + (255 - c.blue())  * blend)),
                    )
                else:
                    colors[i] = QColor(int(c.red() * 0.1), int(c.green() * 0.1), int(c.blue() * 0.1))
            st["state"] += 1

        elif t == "Etoile Filante":
            TAIL, total = 5, n + 9
            pos = st["state"] % total
            for i in range(n):
                dist = pos - i
                c = self._resolve(i, cfg, st)
                if dist == 0:
                    colors[i] = QColor(255, 255, 255)
                elif 1 <= dist <= TAIL:
                    tt = dist / TAIL
                    blend = (math.sin((1.0 - tt) * math.pi / 2)) ** 1.5
                    colors[i] = QColor(
                        min(255, int(c.red()   + (255 - c.red())   * blend)),
                        min(255, int(c.green() + (255 - c.green()) * blend)),
                        min(255, int(c.blue()  + (255 - c.blue())  * blend)),
                    )
                else:
                    colors[i] = QColor(int(c.red() * 0.08), int(c.green() * 0.08), int(c.blue() * 0.08))
            st["state"] += 1

        elif t == "Rainbow":
            st["hue"] = (st["hue"] + 3 + int(speed / 30)) % 360
            for i in range(n):
                colors[i] = QColor.fromHsv((st["hue"] + i * 40) % 360, 255, 220)

        elif t == "Fire":
            for i in range(n):
                colors[i] = self._resolve(i, cfg, st)

        elif t == "Bascule":
            ph = (st["state"] // 10) % 2
            for i in range(n):
                colors[i] = QColor(255, 255, 255) if i % 2 == ph else QColor(200, 100, 30)
            st["state"] += 1

        return colors

    def _tick(self):
        if not self._layers:
            self._colors = [QColor("#111")] * self.N
            self.update()
            return

        # MAX blend across all layers
        final_r = [0] * self.N
        final_g = [0] * self.N
        final_b = [0] * self.N

        for li, cfg in enumerate(self._layers):
            if li >= len(self._layer_states):
                self._layer_states.append({"state": 0, "brightness": 0.0, "brightness_dir": 1, "hue": 0})
            if not cfg or not cfg.get("type"):
                continue
            if cfg.get("muted"):
                continue
            lc = self._compute_layer(cfg, self._layer_states[li])
            for i, c in enumerate(lc):
                final_r[i] = max(final_r[i], c.red())
                final_g[i] = max(final_g[i], c.green())
                final_b[i] = max(final_b[i], c.blue())

        self._colors = [QColor(r, g, b) for r, g, b in zip(final_r, final_g, final_b)]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        n = self.N
        cell = w / n
        r = min(cell * 0.38, h * 0.44)
        cy = h // 2

        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor("#0d0d0d"))
        grad.setColorAt(1, QColor("#111"))
        p.fillRect(self.rect(), grad)

        for i, color in enumerate(self._colors):
            cx = int(cell * (i + 0.5))
            if color.red() + color.green() + color.blue() > 60:
                glow = QColor(color.red(), color.green(), color.blue(), 50)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(glow))
                p.drawEllipse(int(cx - r * 1.8), int(cy - r * 1.8), int(r * 3.6), int(r * 3.6))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
            if color.red() + color.green() + color.blue() > 80:
                hr = max(2, r * 0.28)
                p.setBrush(QBrush(QColor(255, 255, 255, 100)))
                p.drawEllipse(int(cx - hr * 0.6), int(cy - r * 0.55), int(hr), int(hr))
        p.end()


# ──────────────────────────────────────────────────────────────────────────────
# MINI PLAN CANVAS
# ──────────────────────────────────────────────────────────────────────────────
_COLOR_ATTRS = {"R", "G", "B", "W", "Ambre", "Orange", "UV"}

class MiniPlanCanvas(QWidget):
    """Plan de feu miniature (~400×180px) animant l'effet courant en temps réel."""

    def __init__(self, projectors_ref: list, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setMinimumWidth(300)
        self._projectors = projectors_ref
        self._layers     = []
        self._states     = []   # un état par couche
        self._colors     = {}   # {id(proj): QColor}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_layers(self, layers: list):
        """Charge de nouvelles couches ET réinitialise les états."""
        self._layers = layers
        self._states = [{"angle": 0.0, "chase_pos": 0, "tick": 0}
                        for _ in layers]
        self._colors = {}
        self.update()

    def update_layers_config(self, layers: list):
        """Met à jour les couches sans réinitialiser les états (édition live)."""
        self._layers = layers
        while len(self._states) < len(layers):
            self._states.append({"angle": 0.0, "chase_pos": 0, "tick": 0})
        self._states = self._states[:len(layers)]

    def _compute_shape(self, shape: str, st: dict, proj_idx: int,
                       n_active: int, speed: int, amplitude: int,
                       val_min: int, val_max: int) -> float:
        n = max(n_active, 1)
        vmin = val_min / 100.0
        vmax = val_max / 100.0
        amp  = amplitude / 100.0
        step = max(0.005, speed / 2000.0)

        if shape == "max":
            return vmax * amp
        if shape == "min":
            return vmin * amp
        if shape == "off":
            return 0.0
        if shape == "sine" or shape == "phase1":
            v = (1.0 - math.cos(st["angle"])) / 2.0
            return (vmin + (vmax - vmin) * v) * amp
        if shape == "phase2":
            offset = proj_idx * 2 * math.pi / 3
            v = (1.0 - math.cos(st["angle"] + offset)) / 2.0
            return (vmin + (vmax - vmin) * v) * amp
        if shape == "phase3":
            offset = proj_idx * 2 * math.pi / 6
            v = (1.0 - math.cos(st["angle"] + offset)) / 2.0
            return (vmin + (vmax - vmin) * v) * amp
        if shape == "chase":
            pos = st["chase_pos"] % n
            return vmax * amp if proj_idx == pos else 0.0
        if shape == "pause":
            return vmin * amp
        if shape == "sound":
            return random.uniform(vmin, vmax) * amp
        return 0.0

    def _tick(self):
        if not self._projectors or not self._layers:
            self._colors = {}
            self.update()
            return

        # Init accumulators par proj
        final = {id(p): [0.0] for p in self._projectors}

        for li, layer in enumerate(self._layers):
            if layer.get("muted"):
                continue
            if li >= len(self._states):
                self._states.append({"angle": 0.0, "chase_pos": 0, "tick": 0})
            st = self._states[li]

            target_type   = layer.get("target_type", "all")
            target_groups = set(layer.get("target_groups", []))
            speed     = layer.get("speed", 50)
            amplitude = layer.get("amplitude", 100)
            val_max   = layer.get("val_max", 100)
            val_min   = layer.get("val_min", 0)
            shape     = layer.get("shape", "sine")

            # Déterminer les projecteurs actifs
            active = []
            for idx, p in enumerate(self._projectors):
                if target_type == "even" and idx % 2 != 0:
                    continue
                if target_type == "odd" and idx % 2 != 1:
                    continue
                if target_type == "groups" and p.group not in target_groups:
                    continue
                active.append((idx, p))

            n_active = len(active)
            for order_idx, (glob_idx, p) in enumerate(active):
                v = self._compute_shape(shape, st, order_idx, n_active,
                                        speed, amplitude, val_min, val_max)
                final[id(p)][0] = max(final[id(p)][0], v)

            # Avancer l'état
            step = max(0.005, speed / 2000.0)
            st["angle"] += step
            if st["angle"] > 2 * math.pi:
                st["angle"] -= 2 * math.pi
            st["tick"] += 1
            if n_active > 0:
                chase_speed = max(1, 8 - speed // 14)
                if st["tick"] % chase_speed == 0:
                    st["chase_pos"] = (st["chase_pos"] + 1) % n_active

        # Construire les couleurs
        self._colors = {}
        for p in self._projectors:
            v = final[id(p)][0]
            iv = int(v * 255)
            self._colors[id(p)] = QColor(iv, iv, iv)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Fond
        p.fillRect(self.rect(), QColor("#0a0a0a"))

        projs = self._projectors
        if not projs:
            p.setPen(QPen(QColor("#444")))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(self.rect(), Qt.AlignCenter, "Aucun projecteur dans le patch")
            p.end()
            return

        # Calculer positions
        MARGIN = 24
        usable_w = w - 2 * MARGIN
        usable_h = h - 2 * MARGIN - 16
        radius = min(usable_w / max(len(projs), 1) * 0.38, 16, usable_h * 0.38)

        pos_list = []
        for i, proj in enumerate(projs):
            cx = getattr(proj, "canvas_x", None)
            cy = getattr(proj, "canvas_y", None)
            if cx is not None and cy is not None:
                px = int(MARGIN + cx * usable_w)
                py = int(MARGIN + cy * usable_h)
            else:
                # Fallback : disposition linéaire
                px = int(MARGIN + (i + 0.5) / len(projs) * usable_w)
                py = h // 2 - 8
            pos_list.append((px, py))

        for i, proj in enumerate(projs):
            px, py = pos_list[i]
            color = self._colors.get(id(proj), QColor("#1a1a1a"))
            brightness = (color.red() + color.green() + color.blue()) / 3

            if brightness > 20:
                glow = QColor(color.red(), color.green(), color.blue(), 40)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(glow))
                p.drawEllipse(int(px - radius * 1.8), int(py - radius * 1.8),
                              int(radius * 3.6), int(radius * 3.6))

            p.setPen(QPen(QColor("#333"), 1))
            p.setBrush(QBrush(color))
            p.drawEllipse(int(px - radius), int(py - radius),
                          int(radius * 2), int(radius * 2))

            # Label groupe : lettre du groupe (A/B/C/D/E/F)
            grp = proj.group
            display = GROUP_DISPLAY_FALLBACK.get(grp, grp.capitalize())
            short = display[-1] if display else "?"
            p.setPen(QPen(QColor("#666")))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(int(px - radius), int(py + radius + 2), int(radius * 2), 14,
                       Qt.AlignCenter, short)

        p.end()


# ──────────────────────────────────────────────────────────────────────────────
# TARGET WIDGET
# ──────────────────────────────────────────────────────────────────────────────
class TargetWidget(QWidget):
    """Boutons toggle inline : [Tous][Pair][Impair] + boutons groupes."""

    changed = Signal()

    _BTN_STYLE = (
        "QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {bd};"
        " border-radius: 3px; font-size: 10px; padding: 2px 6px; }}"
        "QPushButton:hover {{ border-color: #00d4ff55; }}"
    )

    def __init__(self, display_groups: dict, parent=None):
        """display_groups = {group_key: display_name}"""
        super().__init__(parent)
        self._display_groups = display_groups
        self._target_type    = "all"   # "all"|"even"|"odd"|"groups"
        self._target_groups: set = set()

        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(3)

        # "Tous / Pair / Impair" — exclusifs
        self._btn_all  = QPushButton("Tous")
        self._btn_even = QPushButton("Pair")
        self._btn_odd  = QPushButton("Impair")
        for btn, key in [(self._btn_all, "all"), (self._btn_even, "even"),
                         (self._btn_odd, "odd")]:
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, k=key: self._click_global(k))
            hl.addWidget(btn)

        # Séparateur léger
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet("background: #2a2a2a; border: none;")
        hl.addWidget(sep)

        # Boutons groupes (multi-sélection)
        self._grp_btns: dict = {}
        for key, display in display_groups.items():
            letter = display[-1] if display else key[0].upper()
            btn = QPushButton(letter)
            btn.setCheckable(True)
            btn.setFixedSize(24, 24)
            btn.setToolTip(display)
            btn.clicked.connect(lambda _, k=key: self._click_group(k))
            hl.addWidget(btn)
            self._grp_btns[key] = btn

        self._refresh_styles()

    def _click_global(self, key: str):
        self._target_type   = key
        self._target_groups = set()
        self._refresh_styles()
        self.changed.emit()

    def _click_group(self, key: str):
        self._target_type = "groups"
        if key in self._target_groups:
            self._target_groups.discard(key)
        else:
            self._target_groups.add(key)
        if not self._target_groups:
            self._target_type = "all"
        self._refresh_styles()
        self.changed.emit()

    def _refresh_styles(self):
        def _style(active):
            if active:
                return self._BTN_STYLE.format(bg="#00d4ff22", fg="#00d4ff",
                                               bd="#00d4ff66")
            return self._BTN_STYLE.format(bg="#1a1a1a", fg="#666", bd="#333")

        self._btn_all.setChecked(self._target_type == "all")
        self._btn_even.setChecked(self._target_type == "even")
        self._btn_odd.setChecked(self._target_type == "odd")
        self._btn_all.setStyleSheet(_style(self._target_type == "all"))
        self._btn_even.setStyleSheet(_style(self._target_type == "even"))
        self._btn_odd.setStyleSheet(_style(self._target_type == "odd"))

        for key, btn in self._grp_btns.items():
            active = (self._target_type == "groups"
                      and key in self._target_groups)
            btn.setChecked(active)
            btn.setStyleSheet(_style(active))

    def target_type(self) -> str:
        return self._target_type

    def target_groups(self) -> list:
        return list(self._target_groups)

    def set_value(self, target_type: str, target_groups: list):
        self._target_type   = target_type
        self._target_groups = set(target_groups)
        self._refresh_styles()


# ──────────────────────────────────────────────────────────────────────────────
# PERSISTENCE
# ──────────────────────────────────────────────────────────────────────────────
def _load_user_effects() -> list:
    try:
        if EFFECTS_FILE.exists():
            data = json.loads(EFFECTS_FILE.read_text(encoding="utf-8"))
            for e in data:
                e["builtin"] = False
            return data
    except Exception:
        pass
    return []

def _save_user_effects(effects: list):
    custom = [e for e in effects if not e.get("builtin", False)]
    try:
        EFFECTS_FILE.write_text(json.dumps(custom, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# DIALOG
# ──────────────────────────────────────────────────────────────────────────────
class EffectEditorDialog(QDialog):
    """Editeur d'effets — liste + formulaire + preview live"""

    effect_assigned = Signal(int, dict)

    CATEGORIES = ["Strobe / Flash", "Mouvement", "Ambiance", "Couleur",
                  "Spécial", "Personnalisés"]

    def __init__(self, main_window):
        super().__init__(main_window)
        self._mw         = main_window
        self._all        = list(BUILTIN_EFFECTS) + _load_user_effects()

        existing_names = {e["name"] for e in self._all}
        for cfg in getattr(main_window, "_button_effect_configs", {}).values():
            name = cfg.get("name", "")
            if name and name not in existing_names:
                entry = dict(cfg)
                entry.setdefault("category", "Personnalisés")
                entry["builtin"] = False
                self._all.append(entry)
                existing_names.add(name)

        # Snapshot des assignations au moment de l'ouverture (pour "Charger les défauts")
        self._initial_assignments = {
            k: dict(v) for k, v in
            getattr(main_window, "_button_effect_configs", {}).items()
        }

        self._sel            = 0
        self._dirty          = False
        self._custom_hex     = "#ffffff"
        self._ign            = False
        self._undo_stack     = []
        self._working_layers = []   # couches de l'effet en cours d'édition
        self._cur_layer      = 0   # index de la couche sélectionnée

        # Nouveau modèle : attributs disponibles et groupes depuis le patch
        projs = getattr(main_window, "projectors", [])
        self._available_attrs = _get_available_attributes(projs) or ["Dim"]
        self._display_groups  = _get_display_groups(projs)

        self.setWindowTitle("Editeur d'effets")
        self.setWindowFlags(Qt.Window | Qt.WindowMaximizeButtonHint
                            | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet(_STYLE)
        self._build_ui()
        self.showMaximized()
        if self._all:
            self._select(0)

    # ── UNDO ──────────────────────────────────────────────────────────────────

    def _push_undo(self):
        self._undo_stack.append(copy.deepcopy(self._all))
        if len(self._undo_stack) > 20:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            return
        self._all = self._undo_stack.pop()
        _save_user_effects(self._all)
        self._rebuild_list()
        new_sel = min(self._sel, len(self._all) - 1)
        if self._all:
            self._select(new_sel)

    # ── ASSIGNATION HELPERS ───────────────────────────────────────────────────

    def _get_assigned_btns(self, eff_name: str) -> list:
        """Retourne la liste de TOUS les indices de boutons assignés à cet effet."""
        if not eff_name:
            return []
        result = []
        for i in range(len(self._mw.effect_buttons)):
            if self._mw._button_effect_configs.get(i, {}).get("name", "") == eff_name:
                result.append(i)
        return result

    def _get_assigned_btn(self, eff_name: str) -> int:
        btns = self._get_assigned_btns(eff_name)
        return btns[0] if btns else -1

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._create_menu_bar())

        _content = QWidget()
        root = QHBoxLayout(_content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── PANNEAU GAUCHE ────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(250)
        left.setStyleSheet("QWidget { background: #0e0e0e; border-right: 1px solid #222; }")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        lhdr = QWidget()
        lhdr.setFixedHeight(52)
        lhdr.setStyleSheet("background: #0a0a0a; border-bottom: 1px solid #222;")
        lhh = QHBoxLayout(lhdr)
        lhh.setContentsMargins(14, 0, 10, 0)
        ttl = QLabel("Effets")
        ttl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lhh.addWidget(ttl)
        lhh.addStretch()
        btn_new = QPushButton("+ Nouveau")
        btn_new.setFixedHeight(28)
        btn_new.setStyleSheet(
            "QPushButton { background: #00d4ff1a; color: #00d4ff; border: 1px solid #00d4ff44;"
            " border-radius: 4px; padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #00d4ff33; }")
        btn_new.clicked.connect(self._new_effect)
        lhh.addWidget(btn_new)
        lv.addWidget(lhdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: #0e0e0e; }")
        self._list_w = QWidget()
        self._list_w.setStyleSheet("background: #0e0e0e;")
        self._list_vl = QVBoxLayout(self._list_w)
        self._list_vl.setContentsMargins(4, 6, 4, 6)
        self._list_vl.setSpacing(0)
        self._list_vl.addStretch()
        scroll.setWidget(self._list_w)
        lv.addWidget(scroll)
        root.addWidget(left)

        # ── PANNEAU DROIT ─────────────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        rhdr = QWidget()
        rhdr.setFixedHeight(52)
        rhdr.setStyleSheet("background: #0a0a0a; border-bottom: 1px solid #222;")
        rhh = QHBoxLayout(rhdr)
        rhh.setContentsMargins(24, 0, 16, 0)
        self._title_lbl = QLabel("Sélectionnez un effet")
        self._title_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self._title_lbl.setStyleSheet("color: #00d4ff; border-radius: 4px;")
        self._title_lbl.setCursor(Qt.IBeamCursor)
        self._title_lbl.setToolTip("Cliquer pour renommer")
        self._title_lbl.mousePressEvent = lambda e: self._focus_rename()
        rhh.addWidget(self._title_lbl)
        rhh.addStretch()

        self._btn_save = QPushButton("Sauvegarder")
        self._btn_save.setFixedHeight(32)
        self._btn_save.setEnabled(False)
        self._btn_save.setStyleSheet(
            "QPushButton { background: #00d4ff; color: #000; border: none; border-radius: 5px;"
            " font-weight: bold; padding: 4px 20px; }"
            "QPushButton:hover { background: #33ddff; }"
            "QPushButton:disabled { background: #1a1a1a; color: #444; border: 1px solid #333; }")
        self._btn_save.clicked.connect(self._save_current)
        rhh.addWidget(self._btn_save)

        self._btn_del = QPushButton("Supprimer")
        self._btn_del.setFixedHeight(32)
        self._btn_del.setVisible(False)
        self._btn_del.setStyleSheet(
            "QPushButton { background: #c0392b1a; color: #e74c3c; border: 1px solid #c0392b55;"
            " border-radius: 5px; padding: 4px 14px; }"
            "QPushButton:hover { background: #c0392b33; }")
        self._btn_del.clicked.connect(self._delete_current)
        rhh.addWidget(self._btn_del)

        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(32)
        btn_close.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #888; border: 1px solid #3a3a3a;"
            " border-radius: 5px; padding: 4px 14px; }"
            "QPushButton:hover { background: #333; color: #fff; border-color: #666; }")
        btn_close.clicked.connect(self.close)
        rhh.addWidget(btn_close)
        rv.addWidget(rhdr)

        # ── Scroll area pour le panneau droit ─────────────────────────────────
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body_scroll.setStyleSheet("QScrollArea { border: none; background: #141414; }")
        body_w = QWidget()
        body_v = QVBoxLayout(body_w)
        body_v.setContentsMargins(24, 20, 24, 20)
        body_v.setSpacing(14)

        # ── Ligne haute : Nom + Preview | Assignation ─────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        # Colonne gauche : nom + preview
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        _name_lbl = QLabel("Nom de l'effet")
        _name_lbl.setStyleSheet("color: #555; font-size: 11px; min-width: 90px;")
        name_row.addWidget(_name_lbl)
        self._name_edit = QLineEdit()
        self._name_edit.setFixedHeight(32)
        self._name_edit.textChanged.connect(self._form_changed)
        name_row.addWidget(self._name_edit, 1)
        left_col.addLayout(name_row)

        prev_frame = QFrame()
        prev_frame.setStyleSheet(
            "QFrame { background: #0a0a0a; border: 1px solid #222; border-radius: 8px; }")
        prev_fl = QVBoxLayout(prev_frame)
        prev_fl.setContentsMargins(8, 8, 8, 8)
        projs = getattr(self._mw, "projectors", [])
        self._preview = MiniPlanCanvas(projs)
        prev_fl.addWidget(self._preview)
        left_col.addWidget(prev_frame)

        top_row.addLayout(left_col, 1)

        # Colonne droite : assignation
        assign = QFrame()
        assign.setStyleSheet(
            "QFrame { background: #111; border: 1px solid #222; border-radius: 8px; }")
        av = QVBoxLayout(assign)
        av.setContentsMargins(16, 12, 16, 12)
        av.setSpacing(8)
        albl = QLabel("Assigner à un bouton AKAI")
        albl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        albl.setStyleSheet("color: #ccc;")
        av.addWidget(albl)
        arow = QHBoxLayout()
        arow.setSpacing(5)
        self._assign_btns = []
        for i in range(9):
            ab = QPushButton(f"B{i+1}")
            ab.setFixedSize(46, 32)
            ab.setToolTip(f"Assigner à bouton {i+1}")
            ab.clicked.connect(lambda _, idx=i: self._assign_to_btn(idx))
            arow.addWidget(ab)
            self._assign_btns.append(ab)
        arow.addStretch()
        av.addLayout(arow)

        # Mode de déclenchement
        trig_lbl = QLabel("Mode de déclenchement")
        trig_lbl.setStyleSheet("color: #888; font-size: 10px;")
        av.addWidget(trig_lbl)
        trig_row = QHBoxLayout()
        trig_row.setSpacing(6)
        _trig_defs = [
            ("toggle", "↕ Toggle",  "Appuyer = active / re-appuyer = désactive"),
            ("flash",  "⚡ Flash",   "Maintenir enfoncé = actif, relâcher = stop"),
            ("timer",  "⏳ Timer",   "Active l'effet pendant une durée puis s'arrête"),
        ]
        self._trig_cbs = {}
        _cb_style = (
            "QCheckBox { color: #aaa; font-size: 10px; spacing: 4px; }"
            "QCheckBox:checked { color: #00d4ff; }"
            "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 2px; }"
            "QCheckBox::indicator:unchecked { border: 1px solid #444; background: #1a1a1a; }"
            "QCheckBox::indicator:checked { border: 1px solid #00d4ff; background: #00d4ff33; }")
        for mode, label, tip in _trig_defs:
            cb = QCheckBox(label)
            cb.setChecked(mode == "toggle")
            cb.setToolTip(tip)
            cb.setStyleSheet(_cb_style)
            self._trig_cbs[mode] = cb
            trig_row.addWidget(cb)

        def _trig_exclusive(checked, chosen_mode):
            if not checked:
                return
            for m, c in self._trig_cbs.items():
                if m != chosen_mode:
                    c.blockSignals(True)
                    c.setChecked(False)
                    c.blockSignals(False)
        for _mode in list(self._trig_cbs.keys()):
            self._trig_cbs[_mode].toggled.connect(
                lambda checked, m=_mode: _trig_exclusive(checked, m))

        self._trig_dur_spin = QDoubleSpinBox()
        self._trig_dur_spin.setRange(0.1, 60.0)
        self._trig_dur_spin.setSingleStep(0.5)
        self._trig_dur_spin.setValue(2.0)
        self._trig_dur_spin.setSuffix(" s")
        self._trig_dur_spin.setFixedWidth(72)
        self._trig_dur_spin.setToolTip("Durée du timer (en secondes)")
        self._trig_dur_spin.setStyleSheet(
            "QDoubleSpinBox { background: #1a1a1a; color: #00d4ff; border: 1px solid #333;"
            " border-radius: 3px; padding: 2px 4px; font-size: 10px; }"
            "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button"
            " { width: 14px; background: #222; border: none; }")
        self._trig_dur_spin.setVisible(False)
        trig_row.addWidget(self._trig_dur_spin)
        trig_row.addStretch()
        av.addLayout(trig_row)
        self._trig_cbs["timer"].toggled.connect(self._trig_dur_spin.setVisible)
        av.addStretch()

        top_row.addWidget(assign, 1)
        body_v.addLayout(top_row)

        # ── Couches ───────────────────────────────────────────────────────────
        layers_frame = QFrame()
        layers_frame.setStyleSheet(
            "QFrame { background: #111; border: 1px solid #222; border-radius: 8px; }")
        layers_v = QVBoxLayout(layers_frame)
        layers_v.setContentsMargins(0, 0, 0, 0)
        layers_v.setSpacing(0)

        # En-tête couches avec bouton + Ajouter
        layers_hdr = QWidget()
        layers_hdr.setFixedHeight(36)
        layers_hdr.setStyleSheet(
            "QWidget { background: #0e0e0e; border-radius: 8px 8px 0 0;"
            " border-bottom: 1px solid #222; }")
        layers_hh = QHBoxLayout(layers_hdr)
        layers_hh.setContentsMargins(14, 0, 10, 0)
        _lhdr_lbl = QLabel("COUCHES")
        _lhdr_lbl.setStyleSheet(
            "color: #444; font-size: 9px; font-weight: bold; letter-spacing: 1px; border: none;")
        layers_hh.addWidget(_lhdr_lbl)
        layers_hh.addStretch()
        self._btn_add_layer = QPushButton("+ Ajouter une couche")
        self._btn_add_layer.setFixedHeight(24)
        self._btn_add_layer.setStyleSheet(
            "QPushButton { background: #00d4ff1a; color: #00d4ff; border: 1px solid #00d4ff44;"
            " border-radius: 4px; padding: 0 10px; font-size: 11px; }"
            "QPushButton:hover { background: #00d4ff33; }")
        self._btn_add_layer.clicked.connect(self._add_layer)
        layers_hh.addWidget(self._btn_add_layer)
        layers_v.addWidget(layers_hdr)

        self._layers_list_w = QWidget()
        self._layers_list_w.setStyleSheet("background: transparent;")
        self._layers_chips_row = QVBoxLayout(self._layers_list_w)
        self._layers_chips_row.setContentsMargins(0, 0, 0, 0)
        self._layers_chips_row.setSpacing(0)
        layers_v.addWidget(self._layers_list_w)
        body_v.addWidget(layers_frame)

        body_v.addStretch()
        body_scroll.setWidget(body_w)
        rv.addWidget(body_scroll, 1)
        root.addWidget(right, 1)

        outer.addWidget(_content, 1)
        self._rebuild_list()

    # ── MENU ──────────────────────────────────────────────────────────────────

    def _create_menu_bar(self) -> QMenuBar:
        bar = QMenuBar()
        bar.setStyleSheet(_MENU_STYLE)

        edit_menu = bar.addMenu("Edition")
        undo_act = QAction("Annuler\tCtrl+Z", self)
        undo_act.setShortcut(QKeySequence("Ctrl+Z"))
        undo_act.triggered.connect(self._undo)
        edit_menu.addAction(undo_act)
        edit_menu.addSeparator()
        reset_act = QAction("Charger les effets par défaut...", self)
        reset_act.triggered.connect(self._reset_to_defaults)
        edit_menu.addAction(reset_act)
        edit_menu.addSeparator()
        import_act = QAction("Importer un effet...", self)
        import_act.triggered.connect(self._import_effect)
        edit_menu.addAction(import_act)
        export_act = QAction("Exporter l'effet sélectionné...", self)
        export_act.triggered.connect(self._export_effect)
        edit_menu.addAction(export_act)

        return bar

    # ── LISTE ─────────────────────────────────────────────────────────────────

    def _rebuild_list(self):
        while self._list_vl.count() > 1:
            item = self._list_vl.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)
                w.deleteLater()

        for cat in self.CATEGORIES:
            if cat == "Personnalisés":
                cat_items = [(i, e) for i, e in enumerate(self._all) if not e.get("builtin", False)]
            else:
                cat_items = [(i, e) for i, e in enumerate(self._all) if e.get("category") == cat]
            if not cat_items:
                continue

            ch = QLabel(f"  {cat.upper()}")
            ch.setFixedHeight(24)
            ch.setStyleSheet(
                "color: #444; font-size: 9px; font-weight: bold; letter-spacing: 1px;"
                " background: transparent; padding-left: 4px;")
            self._list_vl.insertWidget(self._list_vl.count() - 1, ch)

            for i, e in cat_items:
                self._list_vl.insertWidget(self._list_vl.count() - 1, self._make_card(e, i))

    def _make_card(self, eff: dict, idx: int) -> QWidget:
        sel     = idx == self._sel
        tc      = TYPE_COLORS.get(eff.get("type", ""), "#888")
        name    = eff.get("name", "Sans nom")
        btn_nos = self._get_assigned_btns(name)
        assigned = bool(btn_nos)
        layers  = eff.get("layers", [])

        if sel:
            bg, bdl, txt_color = "#1e2e32", tc, "#ffffff"
        else:
            bg, bdl, txt_color = "transparent", "#2a2a2a", "#999"

        card = QWidget()
        card.setFixedHeight(36)
        card.setCursor(Qt.PointingHandCursor)
        card.setProperty("eff_idx", idx)
        card.setStyleSheet(
            f"QWidget {{ background: {bg}; border: none; border-left: 3px solid {bdl}; }}"
            f"QWidget:hover {{ background: #1a2428; border-left: 3px solid {tc}; }}")

        hl = QHBoxLayout(card)
        hl.setContentsMargins(10, 0, 8, 0)
        hl.setSpacing(4)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {txt_color}; font-size: 11px; background: transparent; border: none;")
        hl.addWidget(name_lbl)

        if len(layers) > 1:
            lyr_lbl = QLabel(f"[{len(layers)}]")
            lyr_lbl.setStyleSheet("color: #444; font-size: 9px; background: transparent; border: none;")
            hl.addWidget(lyr_lbl)

        hl.addStretch()

        # Badges cyan : max 3 affichés, puis "+" si surplus
        for bn in btn_nos[:3]:
            badge_lbl = QLabel(f"B{bn + 1}")
            badge_lbl.setFixedSize(22, 16)
            badge_lbl.setAlignment(Qt.AlignCenter)
            badge_lbl.setStyleSheet(
                "background: #00d4ff; color: #000; border-radius: 3px;"
                " font-size: 9px; font-weight: bold; border: none;")
            hl.addWidget(badge_lbl)
        if len(btn_nos) > 3:
            more_lbl = QLabel(f"+{len(btn_nos) - 3}")
            more_lbl.setFixedSize(20, 16)
            more_lbl.setAlignment(Qt.AlignCenter)
            more_lbl.setToolTip(", ".join(f"B{bn + 1}" for bn in btn_nos[3:]))
            more_lbl.setStyleSheet(
                "background: #005566; color: #00d4ff; border-radius: 3px;"
                " font-size: 9px; font-weight: bold; border: none;")
            hl.addWidget(more_lbl)

        # Clic → sélectionne ; re-clic sur sélectionné → désélectionne
        card.mousePressEvent = lambda e, i=idx: self._deselect() if i == self._sel else self._select(i)
        return card

    # ── COUCHES ───────────────────────────────────────────────────────────────

    def _rebuild_layers_chips(self):
        """Reconstruit les blocs inline de chaque couche."""
        while self._layers_chips_row.count():
            item = self._layers_chips_row.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for i, layer in enumerate(self._working_layers):
            self._layers_chips_row.addWidget(self._make_layer_block(i, layer))

    def _make_layer_block(self, idx: int, layer: dict) -> QWidget:
        """Crée un bloc DAW ligne unique (64px) pour une couche — nouveau modèle attribut/forme."""
        muted = layer.get("muted", False)
        blk = QFrame()
        blk.setFixedHeight(64)
        blk.setStyleSheet(
            "QFrame { background: " + ("#090909" if muted else "#0e0e0e") + ";"
            " border: none; border-bottom: 1px solid #1a1a1a; border-radius: 0; }")

        hl = QHBoxLayout(blk)
        hl.setContentsMargins(6, 4, 6, 4)
        hl.setSpacing(6)

        # ── Mute button ──
        mute_btn = QPushButton("◉" if not muted else "◌")
        mute_btn.setCheckable(True)
        mute_btn.setChecked(not muted)
        mute_btn.setFixedSize(26, 26)
        mute_btn.setToolTip("Activer/Désactiver cette couche")
        mute_btn.setStyleSheet(
            "QPushButton { background: #00d4ff22; color: #00d4ff; border: 1px solid #00d4ff44;"
            " border-radius: 4px; font-size: 12px; padding: 0; }"
            "QPushButton:checked { background: #00d4ff44; color: #00d4ff; }"
            "QPushButton:!checked { background: #1a1a1a; color: #333; border-color: #222; }")
        hl.addWidget(mute_btn)

        # ── Séparateur ──
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet("background: #252525; border: none;")
        hl.addWidget(sep)

        # ── Attribut ──
        attr_cb = QComboBox()
        attr_cb.setFixedHeight(28)
        attr_cb.setFixedWidth(110)
        for a in self._available_attrs:
            attr_cb.addItem(a, a)
        cur_attr = layer.get("attribute", "Dim")
        ai = next((j for j, a in enumerate(self._available_attrs) if a == cur_attr), 0)
        attr_cb.setCurrentIndex(ai)
        hl.addWidget(attr_cb)

        # ── Forme ──
        shape_cb = QComboBox()
        shape_cb.setFixedHeight(28)
        shape_cb.setFixedWidth(130)
        for label, _ in SHAPES:
            shape_cb.addItem(label)
        cur_shape = layer.get("shape", "sine")
        si = next((j for j, (_, v) in enumerate(SHAPES) if v == cur_shape), 0)
        shape_cb.setCurrentIndex(si)
        hl.addWidget(shape_cb)

        # ── Cible (TargetWidget) ──
        target_w = TargetWidget(self._display_groups)
        target_w.set_value(
            layer.get("target_type", "all"),
            layer.get("target_groups", []),
        )
        hl.addWidget(target_w)

        # ── 4 Knobs ──
        spd_knob = KnobWidget("Vit", 0, 100, layer.get("speed",     50))
        amp_knob = KnobWidget("Amp", 0, 100, layer.get("amplitude", 100))
        max_knob = KnobWidget("Max", 0, 100, layer.get("val_max",   100))
        min_knob = KnobWidget("Min", 0, 100, layer.get("val_min",     0))
        hl.addWidget(spd_knob)
        hl.addWidget(amp_knob)
        hl.addWidget(max_knob)
        hl.addWidget(min_knob)

        hl.addStretch()

        # ── Delete button ──
        if len(self._working_layers) > 1:
            rm = QPushButton()
            rm.setIcon(QApplication.style().standardIcon(QStyle.SP_TrashIcon))
            rm.setFixedSize(26, 26)
            rm.setToolTip("Supprimer cette couche")
            rm.setStyleSheet(
                "QPushButton { background: #2a0808; border: 1px solid #6a1515;"
                " border-radius: 4px; }"
                "QPushButton:hover { background: #aa2222; border-color: #ff4444; }")
            rm.clicked.connect(lambda _, i=idx: self._remove_layer(i))
            hl.addWidget(rm)

        # Store refs
        blk._attr_cb   = attr_cb
        blk._shape_cb  = shape_cb
        blk._target_w  = target_w
        blk._spd_knob  = spd_knob
        blk._amp_knob  = amp_knob
        blk._max_knob  = max_knob
        blk._min_knob  = min_knob
        blk._mute_btn  = mute_btn

        # Mute → update block background
        def _on_mute_toggled(checked, b=blk, i=idx):
            b.setStyleSheet(
                "QFrame { background: " + ("#0e0e0e" if checked else "#090909") + ";"
                " border: none; border-bottom: 1px solid #1a1a1a; border-radius: 0; }")
            b._mute_btn.setText("◉" if checked else "◌")
            self._on_layer_changed(i, b)
        mute_btn.toggled.connect(_on_mute_toggled)

        # Connect changes → save
        attr_cb.currentIndexChanged.connect(lambda _, i=idx, b=blk: self._on_layer_changed(i, b))
        shape_cb.currentIndexChanged.connect(lambda _, i=idx, b=blk: self._on_layer_changed(i, b))
        target_w.changed.connect(lambda i=idx, b=blk: self._on_layer_changed(i, b))
        spd_knob.valueChanged.connect(lambda _, i=idx, b=blk: self._on_layer_changed(i, b))
        amp_knob.valueChanged.connect(lambda _, i=idx, b=blk: self._on_layer_changed(i, b))
        max_knob.valueChanged.connect(lambda _, i=idx, b=blk: self._on_layer_changed(i, b))
        min_knob.valueChanged.connect(lambda _, i=idx, b=blk: self._on_layer_changed(i, b))

        return blk

    def _on_layer_changed(self, idx: int, blk):
        """Sauvegarde le bloc inline dans _working_layers et met à jour le preview."""
        if idx >= len(self._working_layers):
            return
        ai = blk._attr_cb.currentIndex()
        si = blk._shape_cb.currentIndex()
        self._working_layers[idx] = {
            "attribute":     blk._attr_cb.currentData() or (
                self._available_attrs[ai] if ai >= 0 else "Dim"),
            "shape":         SHAPES[si][1] if si >= 0 else "sine",
            "target_type":   blk._target_w.target_type(),
            "target_groups": blk._target_w.target_groups(),
            "speed":         blk._spd_knob.value(),
            "amplitude":     blk._amp_knob.value(),
            "val_max":       blk._max_knob.value(),
            "val_min":       blk._min_knob.value(),
            "muted":         not blk._mute_btn.isChecked(),
        }
        self._preview.update_layers_config(copy.deepcopy(self._working_layers))
        self._dirty = True
        self._btn_save.setEnabled(True)

    def _add_layer(self):
        new_layer = {
            "attribute":     "Dim",
            "shape":         "sine",
            "target_type":   "all",
            "target_groups": [],
            "speed":         50,
            "amplitude":     100,
            "val_max":       100,
            "val_min":       0,
            "muted":         False,
        }
        self._working_layers.append(new_layer)
        self._rebuild_layers_chips()
        self._dirty = True
        self._btn_save.setEnabled(True)
        self._preview.set_layers(copy.deepcopy(self._working_layers))

    def _remove_layer(self, layer_idx: int):
        if len(self._working_layers) <= 1:
            return
        self._working_layers.pop(layer_idx)
        self._rebuild_layers_chips()
        self._dirty = True
        self._btn_save.setEnabled(True)
        self._preview.set_layers(copy.deepcopy(self._working_layers))

    # ── SELECTION / FORM ──────────────────────────────────────────────────────

    def _select(self, idx: int):
        if idx < 0 or idx >= len(self._all):
            return
        self._sel = idx
        eff = self._all[idx]
        self._ign = True

        self._title_lbl.setText(eff.get("name", ""))
        self._name_edit.setText(eff.get("name", ""))
        is_builtin = eff.get("builtin", False)
        self._name_edit.setEnabled(not is_builtin)
        self._title_lbl.setToolTip(
            "Effet intégré — nom non modifiable" if is_builtin else "Cliquer pour renommer"
        )
        self._title_lbl.setCursor(Qt.ArrowCursor if is_builtin else Qt.IBeamCursor)

        # Charger les couches
        self._working_layers = _eff_layers(eff)
        self._rebuild_layers_chips()

        self._btn_save.setEnabled(False)
        self._btn_del.setVisible(not is_builtin)
        self._dirty = False

        self._preview.set_layers(copy.deepcopy(self._working_layers))
        self._refresh_assign_btns()

        # Charger le trigger_mode depuis le premier bouton assigné à cet effet
        eff_name = eff.get("name", "")
        trig_mode = "toggle"
        trig_dur  = 2000
        for i in range(9):
            cfg_i = self._mw._button_effect_configs.get(i, {})
            if cfg_i.get("name") == eff_name:
                trig_mode = cfg_i.get("trigger_mode", "toggle")
                trig_dur  = cfg_i.get("trigger_duration", 2000)
                break
        for mode, cb in self._trig_cbs.items():
            cb.blockSignals(True)
            cb.setChecked(mode == trig_mode)
            cb.blockSignals(False)
        self._trig_dur_spin.blockSignals(True)
        self._trig_dur_spin.setValue(trig_dur / 1000.0)
        self._trig_dur_spin.blockSignals(False)
        self._trig_dur_spin.setVisible(trig_mode == "timer")

        self._ign = False
        self._rebuild_list()

    def _form_changed(self):
        if self._ign:
            return
        self._dirty = True
        self._btn_save.setEnabled(True)

    def _form_cfg(self) -> dict:
        layers = copy.deepcopy(self._working_layers)
        first  = layers[0] if layers else {}
        # Trigger mode
        trig_mode = "toggle"
        for mode, cb in self._trig_cbs.items():
            if cb.isChecked():
                trig_mode = mode
                break
        trig_dur = int(self._trig_dur_spin.value() * 1000)
        return {
            "name":             self._name_edit.text().strip() or "Sans nom",
            "attribute":        first.get("attribute", "Dim"),
            "shape":            first.get("shape", "sine"),
            "target_type":      first.get("target_type", "all"),
            "target_groups":    first.get("target_groups", []),
            "speed":            first.get("speed", 50),
            "amplitude":        first.get("amplitude", 100),
            "val_max":          first.get("val_max", 100),
            "val_min":          first.get("val_min", 0),
            "layers":           layers,
            "builtin":          self._all[self._sel].get("builtin", False) if self._all else False,
            "category":         self._all[self._sel].get("category", "Personnalisés") if self._all else "Personnalisés",
            "trigger_mode":     trig_mode,
            "trigger_duration": trig_dur,
        }

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _new_effect(self):
        self._push_undo()
        default_layer = {
            "attribute": "Dim", "shape": "sine",
            "target_type": "all", "target_groups": [],
            "speed": 50, "amplitude": 100, "val_max": 100, "val_min": 0,
            "muted": False,
        }
        new = {
            "name": "Nouvel effet", "attribute": "Dim", "shape": "sine",
            "category": "Personnalisés", "speed": 50,
            "builtin": False, "layers": [dict(default_layer)],
        }
        self._all.append(new)
        _save_user_effects(self._all)
        self._rebuild_list()
        self._select(len(self._all) - 1)
        self._btn_save.setEnabled(True)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _save_current(self):
        if self._sel < 0 or self._sel >= len(self._all):
            return
        cfg = self._form_cfg()
        name = cfg["name"]
        if not name or name == "Sans nom":
            QMessageBox.warning(self, "Nom requis", "Donnez un nom à l'effet.")
            return
        self._push_undo()
        if cfg.get("builtin"):
            cfg = dict(cfg)
            cfg["builtin"] = False
            cfg["category"] = "Personnalisés"
            self._all.append(cfg)
            new_idx = len(self._all) - 1
        else:
            cfg["builtin"] = False
            self._all[self._sel] = cfg
            new_idx = self._sel
        _save_user_effects(self._all)
        self._dirty = False
        self._rebuild_list()
        self._select(new_idx)

    def _delete_current(self):
        if self._sel < 0 or self._sel >= len(self._all):
            return
        eff = self._all[self._sel]
        if eff.get("builtin", False):
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer l'effet « {eff.get('name', '')} » ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self._push_undo()
        self._all.pop(self._sel)
        _save_user_effects(self._all)
        new_sel = min(self._sel, len(self._all) - 1)
        self._rebuild_list()
        if self._all:
            self._select(new_sel)

    # ── MENU ACTIONS ──────────────────────────────────────────────────────────

    def _reset_to_defaults(self):
        result = QMessageBox.warning(
            self, "Charger les effets par défaut",
            "Cette action va remplacer tous vos effets personnalisés\n"
            "par les effets par défaut.\n\nVos effets personnalisés seront supprimés. Continuer ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if result != QMessageBox.Yes:
            return
        self._push_undo()
        self._all = [dict(e) for e in BUILTIN_EFFECTS]
        _save_user_effects(self._all)
        self._rebuild_list()
        self._select(0)

        # Restaurer les assignations bouton→effet telles qu'elles étaient à l'ouverture,
        # uniquement pour les effets qui existent dans les défauts
        default_names = {e["name"] for e in self._all}
        for btn_idx, cfg in self._initial_assignments.items():
            if cfg.get("name", "") in default_names:
                self.effect_assigned.emit(btn_idx, cfg)
            else:
                # L'effet n'existe plus dans les défauts → on vide le bouton
                self.effect_assigned.emit(btn_idx, {})
        self._refresh_assign_btns()
        self._rebuild_list()

    def _import_effect(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer un effet", "",
            "Effet MyStrow (*.mse);;JSON (*.json);;Tous les fichiers (*)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            effects = data if isinstance(data, list) else [data]
            existing_names = [e.get("name") for e in self._all]
            imported = 0
            for eff in effects:
                if "name" not in eff or ("type" not in eff and "layers" not in eff):
                    continue
                eff = dict(eff)
                eff["builtin"] = False
                eff.setdefault("category", "Personnalisés")
                base = eff["name"]
                n = 2
                while eff["name"] in existing_names:
                    eff["name"] = f"{base} ({n})"
                    n += 1
                existing_names.append(eff["name"])
                self._all.append(eff)
                imported += 1
            if imported:
                self._push_undo()
                _save_user_effects(self._all)
                self._rebuild_list()
                self._select(len(self._all) - 1)
                QMessageBox.information(self, "Import", f"{imported} effet(s) importé(s).")
            else:
                QMessageBox.warning(self, "Import", "Aucun effet valide trouvé dans le fichier.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'import", f"Impossible de lire le fichier :\n{e}")

    def _export_effect(self):
        if self._sel < 0 or self._sel >= len(self._all):
            return
        eff  = dict(self._all[self._sel])
        name = eff.get("name", "effet")
        safe = "".join(c for c in name if c.isalnum() or c in " _-").strip()
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter l'effet", f"{safe}.mse",
            "Effet MyStrow (*.mse);;JSON (*.json)"
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(eff, indent=2, ensure_ascii=False), encoding="utf-8")
            QMessageBox.information(self, "Export", f"Effet exporté :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export", f"Impossible d'écrire le fichier :\n{e}")

    # ── ASSIGNATION ───────────────────────────────────────────────────────────

    def _assign_to_btn(self, btn_idx: int):
        eff_name = (self._all[self._sel].get("name", "")
                    if self._all and self._sel >= 0 else "")
        current = self._mw._button_effect_configs.get(btn_idx, {}).get("name", "")
        if current and current == eff_name:
            # Déjà assigné à ce bouton → désassigner
            self.effect_assigned.emit(btn_idx, {})
        else:
            cfg = self._form_cfg()
            cfg["name"] = self._name_edit.text().strip() or cfg.get("name", "Effet")
            self.effect_assigned.emit(btn_idx, cfg)
        self._refresh_assign_btns()
        self._rebuild_list()

    def _focus_rename(self):
        """Focalise le champ nom pour renommer au clic sur le titre."""
        if not self._name_edit.isEnabled():
            self._title_lbl.setToolTip("Effet intégré — nom non modifiable")
            return
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def _deselect(self):
        """Désélectionne l'effet courant (re-clic sur la carte active)."""
        self._sel = -1
        self._dirty = False
        self._refresh_assign_btns()
        self._rebuild_list()

    def _refresh_assign_btns(self):
        eff_name = (self._all[self._sel].get("name", "")
                    if self._all and self._sel >= 0 else "")
        for i, ab in enumerate(self._assign_btns):
            cfg_name = self._mw._button_effect_configs.get(i, {}).get("name", "")
            is_this = bool(cfg_name) and cfg_name == eff_name
            has_any = bool(cfg_name)

            # Texte : "B{n}" + indication si autre effet assigné
            ab.setText(f"B{i+1}")
            if is_this:
                # Cet effet est assigné à ce bouton → bleu vif
                ab.setToolTip(f"✓ '{cfg_name}' assigné ici\nCliquer pour retirer")
                ab.setStyleSheet(
                    "QPushButton { background: #00d4ff; color: #000; border: none;"
                    " border-radius: 5px; font-size: 11px; font-weight: bold; }"
                    "QPushButton:hover { background: #33ddff; }")
            elif has_any:
                # Un autre effet est assigné → orange + tooltip
                ab.setToolTip(f"Assigné : {cfg_name}\nCliquer pour remplacer par '{eff_name}'")
                ab.setStyleSheet(
                    "QPushButton { background: #1e1a0e; color: #cc8833; border: 1px solid #443311;"
                    " border-radius: 5px; font-size: 10px; font-weight: bold; }"
                    "QPushButton:hover { border-color: #00d4ff; color: #ffcc55; }")
            else:
                ab.setToolTip(f"Assigner '{eff_name}' à B{i+1}")
                ab.setStyleSheet(
                    "QPushButton { background: #1a1a1a; color: #555; border: 1px solid #2a2a2a;"
                    " border-radius: 5px; font-size: 10px; }"
                    "QPushButton:hover { border-color: #00d4ff; color: #fff; }")
