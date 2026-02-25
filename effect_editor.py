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
    QScrollArea, QWidget, QLineEdit, QComboBox, QSlider,
    QColorDialog, QFrame, QMessageBox, QSizePolicy, QGridLayout,
    QMenuBar, QMenu, QFileDialog,
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
     "speed": 80, "target": "lr",        "color_mode": "white",   "custom_color": "#ffffff", "builtin": True},
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
     "speed": 70, "target": "all",       "color_mode": "base",    "custom_color": "#ffffff", "builtin": True},
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
                "Comete", "Etoile Filante", "Rainbow", "Fire", "Bascule"]

PATTERNS = [
    ("Tous",               "all"),
    ("Pairs",              "even"),
    ("Impairs",            "odd"),
    ("Alternance",         "alternate"),
    ("Gauche → Droite",    "lr"),
    ("Droite → Gauche",    "rl"),
]

COLOR_MODES = [
    ("Couleur de base",    "base"),
    ("Blanc",              "white"),
    ("Noir",               "black"),
    ("Arc-en-ciel",        "rainbow"),
    ("Feu",                "fire"),
    ("Couleur custom",     "custom"),
]

TYPE_COLORS = {
    "Strobe": "#ffffff", "Flash": "#ffff44", "Pulse": "#dd44ff",
    "Wave": "#00ffff",   "Chase": "#e0e0e0", "Comete": "#ff8800",
    "Etoile Filante": "#aaddff", "Rainbow": "#00ff88",
    "Fire": "#ff4400",   "Bascule": "#44ccff",
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
"""


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────
def _eff_layers(eff: dict) -> list:
    """Retourne la liste des couches d'un effet (compat legacy sans 'layers')."""
    if "layers" in eff:
        return copy.deepcopy(eff["layers"])
    return [{
        "type":         eff.get("type", "Pulse"),
        "speed":        eff.get("speed", 50),
        "target":       eff.get("target", "all"),
        "color_mode":   eff.get("color_mode", "base"),
        "custom_color": eff.get("custom_color", "#ffffff"),
    }]


# ──────────────────────────────────────────────────────────────────────────────
# MINI PREVIEW
# ──────────────────────────────────────────────────────────────────────────────
class MiniPreviewWidget(QWidget):
    """8 cercles animés montrant l'effet en temps réel (multi-couches)."""

    N = 8
    BASE = QColor(200, 100, 30)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setMinimumWidth(300)
        self._layers = []
        self._layer_states = []
        self._colors = [QColor("#1a1a1a")] * self.N

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def set_config(self, cfg: dict):
        """Compat legacy — wraps single config in a layers list."""
        self.set_layers(_eff_layers(cfg) if cfg else [])

    def set_layers(self, layers: list):
        self._layers = layers
        while len(self._layer_states) < len(layers):
            self._layer_states.append({"state": 0, "brightness": 0.0, "brightness_dir": 1, "hue": 0})
        self._layer_states = self._layer_states[:len(layers)]
        for st in self._layer_states:
            st["state"] = 0
            st["brightness"] = 0.0
            st["brightness_dir"] = 1
            st["hue"] = 0

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
        t      = cfg.get("type", "Pulse")
        speed  = cfg.get("speed", 50)
        target = cfg.get("target", "all")
        n      = self.N
        colors = [QColor(0, 0, 0)] * n
        black  = QColor(0, 0, 0)
        act    = self._active(cfg)

        if t in ("Strobe", "Flash"):
            on = st["state"] % 2 == 0
            for i in act:
                colors[i] = self._resolve(i, cfg, st) if on else black
            st["state"] += 1

        elif t == "Pulse":
            step = 2 + int(speed / 20)
            st["brightness"] += st["brightness_dir"] * step
            if st["brightness"] >= 100: st["brightness"], st["brightness_dir"] = 100, -1
            if st["brightness"] <= 0:   st["brightness"], st["brightness_dir"] = 0, 1
            for i in act:
                b = (st["brightness"] if (target != "alternate" or i % 2 == 0)
                     else 100 - st["brightness"]) / 100.0
                c = self._resolve(i, cfg, st)
                colors[i] = QColor(int(c.red() * b), int(c.green() * b), int(c.blue() * b))

        elif t == "Wave":
            for i in range(n):
                phase = (st["state"] + i * 15) % 100
                b = abs(50 - phase) / 50.0
                c = self._resolve(i, cfg, st)
                colors[i] = QColor(int(c.red() * b), int(c.green() * b), int(c.blue() * b))
            st["state"] += 3 + int(speed / 25)

        elif t == "Chase":
            if act:
                pos = st["state"] % len(act)
                for idx2, i in enumerate(act):
                    c = self._resolve(i, cfg, st)
                    colors[i] = c if idx2 == pos else QColor(
                        int(c.red() * 0.12), int(c.green() * 0.12), int(c.blue() * 0.12))
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
            lc = self._compute_layer(cfg, self._layer_states[li])
            for i, c in enumerate(lc):
                final_r[i] = max(final_r[i], c.red())
                final_g[i] = max(final_g[i], c.green())
                final_b[i] = max(final_b[i], c.blue())

        self._colors = [QColor(r, g, b) for r, g, b in zip(final_r, final_g, final_b)]

        if self._layers:
            speed = self._layers[0].get("speed", 50)
            sf = max(0.05, 1.0 - speed / 100.0 * 0.9)
            self._timer.setInterval(max(25, int(80 * sf)))

        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        n = self.N
        cell = w / n
        r = min(cell * 0.33, h * 0.38)
        cy = h // 2

        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor("#0d0d0d"))
        grad.setColorAt(1, QColor("#111"))
        p.fillRect(self.rect(), grad)

        for i, color in enumerate(self._colors):
            cx = int(cell * (i + 0.5))
            if color.red() + color.green() + color.blue() > 40:
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

        self._sel            = 0
        self._dirty          = False
        self._custom_hex     = "#ffffff"
        self._ign            = False
        self._undo_stack     = []
        self._working_layers = []   # couches de l'effet en cours d'édition
        self._cur_layer      = 0   # index de la couche sélectionnée

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

    def _get_assigned_btn(self, eff_name: str) -> int:
        if not eff_name:
            return -1
        for i in range(len(self._mw.effect_buttons)):
            if self._mw._button_effect_configs.get(i, {}).get("name", "") == eff_name:
                return i
        return -1

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
        self._title_lbl.setStyleSheet("color: #00d4ff;")
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

        body = QWidget()
        body_v = QVBoxLayout(body)
        body_v.setContentsMargins(28, 20, 28, 20)
        body_v.setSpacing(14)

        # ── Preview ───────────────────────────────────────────────────────────
        prev_frame = QFrame()
        prev_frame.setStyleSheet(
            "QFrame { background: #0a0a0a; border: 1px solid #222; border-radius: 8px; }")
        prev_fl = QVBoxLayout(prev_frame)
        prev_fl.setContentsMargins(0, 0, 0, 0)
        self._preview = MiniPreviewWidget()
        prev_fl.addWidget(self._preview)
        body_v.addWidget(prev_frame)

        # ── Couches d'effets ──────────────────────────────────────────────────
        layers_frame = QFrame()
        layers_frame.setStyleSheet(
            "QFrame { background: #111; border: 1px solid #222; border-radius: 8px; }")
        layers_row = QHBoxLayout(layers_frame)
        layers_row.setContentsMargins(14, 8, 14, 8)
        layers_row.setSpacing(8)

        layers_lbl = QLabel("Couches :")
        layers_lbl.setStyleSheet("color: #777; font-size: 11px; min-width: 58px;")
        layers_row.addWidget(layers_lbl)

        chips_container = QWidget()
        chips_container.setStyleSheet("background: transparent;")
        self._layers_chips_row = QHBoxLayout(chips_container)
        self._layers_chips_row.setContentsMargins(0, 0, 0, 0)
        self._layers_chips_row.setSpacing(4)
        layers_row.addWidget(chips_container, 1)

        self._btn_add_layer = QPushButton("+ Couche")
        self._btn_add_layer.setFixedHeight(26)
        self._btn_add_layer.setStyleSheet(
            "QPushButton { background: transparent; color: #00d4ff; border: 1px solid #00d4ff44;"
            " border-radius: 3px; padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #00d4ff22; }")
        self._btn_add_layer.clicked.connect(self._add_layer)
        layers_row.addWidget(self._btn_add_layer)

        body_v.addWidget(layers_frame)

        # ── Formulaire (couche sélectionnée) ──────────────────────────────────
        form = QFrame()
        form.setStyleSheet(
            "QFrame { background: #111; border: 1px solid #222; border-radius: 8px; }")
        fg = QGridLayout(form)
        fg.setContentsMargins(20, 16, 20, 16)
        fg.setVerticalSpacing(14)
        fg.setHorizontalSpacing(20)
        fg.setColumnStretch(1, 1)
        fg.setColumnStretch(3, 1)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet("color: #777; font-size: 11px;")
            return l

        fg.addWidget(_lbl("Nom"), 0, 0)
        self._name_edit = QLineEdit()
        self._name_edit.setFixedHeight(34)
        self._name_edit.textChanged.connect(self._form_changed)
        fg.addWidget(self._name_edit, 0, 1)

        fg.addWidget(_lbl("Type"), 0, 2)
        self._type_cb = QComboBox()
        self._type_cb.setFixedHeight(34)
        for t in EFFECT_TYPES:
            self._type_cb.addItem(t)
        self._type_cb.currentIndexChanged.connect(self._form_changed)
        fg.addWidget(self._type_cb, 0, 3)

        fg.addWidget(_lbl("Vitesse"), 1, 0)
        spd_row = QHBoxLayout()
        self._speed_sl = QSlider(Qt.Horizontal)
        self._speed_sl.setRange(0, 100)
        self._speed_sl.valueChanged.connect(self._on_speed)
        self._speed_lbl = QLabel("50")
        self._speed_lbl.setFixedWidth(28)
        self._speed_lbl.setStyleSheet("color: #00d4ff; font-size: 12px; font-weight: bold;")
        spd_row.addWidget(self._speed_sl)
        spd_row.addWidget(self._speed_lbl)
        fg.addLayout(spd_row, 1, 1)

        fg.addWidget(_lbl("Pattern"), 1, 2)
        self._pat_cb = QComboBox()
        self._pat_cb.setFixedHeight(34)
        for label, _ in PATTERNS:
            self._pat_cb.addItem(label)
        self._pat_cb.currentIndexChanged.connect(self._form_changed)
        fg.addWidget(self._pat_cb, 1, 3)

        fg.addWidget(_lbl("Couleur"), 2, 0)
        self._col_cb = QComboBox()
        self._col_cb.setFixedHeight(34)
        for label, _ in COLOR_MODES:
            self._col_cb.addItem(label)
        self._col_cb.currentIndexChanged.connect(self._form_changed)
        fg.addWidget(self._col_cb, 2, 1)

        fg.addWidget(_lbl("Couleur perso"), 2, 2)
        self._colpick_btn = QPushButton("  Choisir...")
        self._colpick_btn.setFixedHeight(34)
        self._colpick_btn.setFixedWidth(140)
        self._colpick_btn.setVisible(False)
        self._colpick_btn.clicked.connect(self._pick_color)
        fg.addWidget(self._colpick_btn, 2, 3, alignment=Qt.AlignLeft)
        body_v.addWidget(form)

        # ── Assignation ───────────────────────────────────────────────────────
        assign = QFrame()
        assign.setStyleSheet(
            "QFrame { background: #111; border: 1px solid #222; border-radius: 8px; }")
        av = QVBoxLayout(assign)
        av.setContentsMargins(20, 14, 20, 14)
        av.setSpacing(10)
        albl = QLabel("Assigner à un bouton AKAI")
        albl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        albl.setStyleSheet("color: #ccc;")
        av.addWidget(albl)
        arow = QHBoxLayout()
        arow.setSpacing(6)
        self._assign_btns = []
        for i in range(9):
            ab = QPushButton(f"B{i+1}")
            ab.setFixedSize(52, 36)
            ab.setToolTip(f"Assigner à bouton {i+1}")
            ab.clicked.connect(lambda _, idx=i: self._assign_to_btn(idx))
            arow.addWidget(ab)
            self._assign_btns.append(ab)
        arow.addStretch()
        av.addLayout(arow)
        body_v.addWidget(assign)
        body_v.addStretch()
        rv.addWidget(body, 1)
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

        eff_menu = bar.addMenu("Effets")
        reset_act = QAction("Charger les effets par défaut...", self)
        reset_act.triggered.connect(self._reset_to_defaults)
        eff_menu.addAction(reset_act)
        eff_menu.addSeparator()
        import_act = QAction("Importer un effet...", self)
        import_act.triggered.connect(self._import_effect)
        eff_menu.addAction(import_act)
        export_act = QAction("Exporter l'effet sélectionné...", self)
        export_act.triggered.connect(self._export_effect)
        eff_menu.addAction(export_act)

        return bar

    # ── LISTE ─────────────────────────────────────────────────────────────────

    def _rebuild_list(self):
        while self._list_vl.count() > 1:
            item = self._list_vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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
        sel    = idx == self._sel
        tc     = TYPE_COLORS.get(eff.get("type", ""), "#888")
        name   = eff.get("name", "Sans nom")
        btn_no = self._get_assigned_btn(name)
        badge  = f"  · B{btn_no + 1}" if btn_no >= 0 else ""

        # Nombre de couches
        layers = eff.get("layers", [])
        layer_badge = f"  [{len(layers)}]" if len(layers) > 1 else ""

        btn = QPushButton(f"  {name}{badge}{layer_badge}")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("eff_idx", idx)

        if sel and btn_no >= 0:
            bg, bdl, color = "#1e2e32", tc, "#ffffff"
        elif sel:
            bg, bdl, color = "#1e2e32", tc, "#ffffff"
        elif btn_no >= 0:
            bg, bdl, color = "#0e1e22", "#00d4ff44", "#aaddff"
        else:
            bg, bdl, color = "transparent", "#2a2a2a", "#aaa"

        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {color};
                border: none;
                border-left: 3px solid {bdl};
                text-align: left;
                padding-left: 10px;
                font-size: 11px;
                border-radius: 0px;
            }}
            QPushButton:hover {{
                background: #1a2428;
                color: #fff;
                border-left: 3px solid {tc};
            }}
        """)
        btn.clicked.connect(lambda _, i=idx: self._select(i))
        return btn

    # ── COUCHES ───────────────────────────────────────────────────────────────

    def _rebuild_layers_chips(self):
        """Reconstruit les chips de couches dans la barre 'Couches'."""
        while self._layers_chips_row.count():
            item = self._layers_chips_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, layer in enumerate(self._working_layers):
            layer_type = layer.get("type", "?")
            tc = TYPE_COLORS.get(layer_type, "#888")
            selected = (i == self._cur_layer)

            chip = QWidget()
            chip.setStyleSheet("background: transparent;")
            chip_h = QHBoxLayout(chip)
            chip_h.setContentsMargins(0, 0, 0, 0)
            chip_h.setSpacing(0)

            lbl_btn = QPushButton(layer_type)
            lbl_btn.setFixedHeight(26)
            if selected:
                lbl_btn.setStyleSheet(
                    f"QPushButton {{ background: {tc}33; color: {tc}; border: 1px solid {tc}88;"
                    f" border-radius: 3px; padding: 2px 8px; font-size: 11px; font-weight: bold; }}"
                    f"QPushButton:hover {{ background: {tc}55; }}")
            else:
                lbl_btn.setStyleSheet(
                    "QPushButton { background: #1a1a1a; color: #888; border: 1px solid #2a2a2a;"
                    " border-radius: 3px; padding: 2px 8px; font-size: 11px; }"
                    "QPushButton:hover { background: #222; color: #ccc; }")
            lbl_btn.clicked.connect(lambda _, idx=i: self._select_layer(idx))
            chip_h.addWidget(lbl_btn)

            if len(self._working_layers) > 1:
                rm_btn = QPushButton("×")
                rm_btn.setFixedSize(16, 26)
                rm_btn.setStyleSheet(
                    "QPushButton { background: transparent; color: #555; border: none;"
                    " font-size: 13px; padding: 0; margin-left: 1px; }"
                    "QPushButton:hover { color: #ff4444; }")
                rm_btn.clicked.connect(lambda _, idx=i: self._remove_layer(idx))
                chip_h.addWidget(rm_btn)

            self._layers_chips_row.addWidget(chip)

        self._layers_chips_row.addStretch()

    def _select_layer(self, layer_idx: int):
        if layer_idx >= len(self._working_layers):
            return
        self._save_form_to_layer()
        self._cur_layer = layer_idx
        self._rebuild_layers_chips()
        self._load_layer_to_form(self._working_layers[layer_idx])

    def _save_form_to_layer(self):
        """Sauvegarde le formulaire dans la couche courante de _working_layers."""
        if not self._working_layers or self._cur_layer >= len(self._working_layers):
            return
        ti = self._type_cb.currentIndex()
        pi = self._pat_cb.currentIndex()
        ci = self._col_cb.currentIndex()
        self._working_layers[self._cur_layer] = {
            "type":         EFFECT_TYPES[ti] if ti >= 0 else "Pulse",
            "speed":        self._speed_sl.value(),
            "target":       PATTERNS[pi][1]    if pi >= 0 else "all",
            "color_mode":   COLOR_MODES[ci][1] if ci >= 0 else "base",
            "custom_color": self._custom_hex,
        }

    def _load_layer_to_form(self, layer: dict):
        """Charge une couche dans les widgets du formulaire."""
        self._ign = True
        ti = next((i for i, t in enumerate(EFFECT_TYPES) if t == layer.get("type")), 0)
        self._type_cb.setCurrentIndex(ti)
        self._speed_sl.setValue(layer.get("speed", 50))
        self._speed_lbl.setText(str(layer.get("speed", 50)))
        pi = next((i for i, (_, v) in enumerate(PATTERNS) if v == layer.get("target", "all")), 0)
        self._pat_cb.setCurrentIndex(pi)
        ci = next((i for i, (_, v) in enumerate(COLOR_MODES) if v == layer.get("color_mode", "base")), 0)
        self._col_cb.setCurrentIndex(ci)
        self._custom_hex = layer.get("custom_color", "#ffffff")
        self._update_colbtn(self._custom_hex)
        self._colpick_btn.setVisible(layer.get("color_mode") == "custom")
        self._ign = False

    def _add_layer(self):
        self._save_form_to_layer()
        new_layer = {"type": "Strobe", "speed": 50, "target": "all",
                     "color_mode": "white", "custom_color": "#ffffff"}
        self._working_layers.append(new_layer)
        self._cur_layer = len(self._working_layers) - 1
        self._rebuild_layers_chips()
        self._load_layer_to_form(new_layer)
        self._dirty = True
        self._btn_save.setEnabled(True)
        self._preview.set_layers(copy.deepcopy(self._working_layers))

    def _remove_layer(self, layer_idx: int):
        if len(self._working_layers) <= 1:
            return
        self._working_layers.pop(layer_idx)
        if self._cur_layer >= len(self._working_layers):
            self._cur_layer = len(self._working_layers) - 1
        self._rebuild_layers_chips()
        self._load_layer_to_form(self._working_layers[self._cur_layer])
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

        # Charger les couches
        self._working_layers = _eff_layers(eff)
        self._cur_layer = 0
        self._rebuild_layers_chips()
        if self._working_layers:
            self._load_layer_to_form(self._working_layers[0])

        self._btn_save.setEnabled(False)
        self._btn_del.setVisible(not is_builtin)
        self._dirty = False

        self._preview.set_layers(copy.deepcopy(self._working_layers))
        self._refresh_assign_btns()

        self._ign = False
        self._rebuild_list()

    def _form_changed(self):
        if self._ign:
            return
        self._dirty = True
        self._btn_save.setEnabled(True)
        cm = COLOR_MODES[self._col_cb.currentIndex()][1]
        self._colpick_btn.setVisible(cm == "custom")
        self._save_form_to_layer()
        self._rebuild_layers_chips()
        self._preview.set_layers(copy.deepcopy(self._working_layers))

    def _on_speed(self, val: int):
        self._speed_lbl.setText(str(val))
        self._form_changed()

    def _form_cfg(self) -> dict:
        self._save_form_to_layer()
        layers = copy.deepcopy(self._working_layers)
        first  = layers[0] if layers else {}
        return {
            "name":         self._name_edit.text().strip() or "Sans nom",
            "type":         first.get("type", "Pulse"),
            "speed":        first.get("speed", 50),
            "target":       first.get("target", "all"),
            "color_mode":   first.get("color_mode", "base"),
            "custom_color": first.get("custom_color", "#ffffff"),
            "layers":       layers,
            "builtin":      self._all[self._sel].get("builtin", False) if self._all else False,
            "category":     self._all[self._sel].get("category", "Personnalisés") if self._all else "Personnalisés",
        }

    def _update_colbtn(self, hex_c: str):
        c   = QColor(hex_c)
        lum = (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000
        tc  = "#000" if lum > 128 else "#fff"
        self._colpick_btn.setStyleSheet(
            f"QPushButton {{ background: {hex_c}; color: {tc}; border: 1px solid #555;"
            f" border-radius: 5px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ border-color: #00d4ff; }}")
        self._colpick_btn.setText(f"  {hex_c}")

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._custom_hex), self, "Couleur personnalisée")
        if c.isValid():
            self._custom_hex = c.name()
            self._update_colbtn(c.name())
            self._form_changed()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _new_effect(self):
        self._push_undo()
        default_layer = {"type": "Strobe", "speed": 50, "target": "all",
                         "color_mode": "white", "custom_color": "#ffffff"}
        new = {
            "name": "Nouvel effet", "type": "Strobe", "category": "Personnalisés",
            "speed": 50, "target": "all", "color_mode": "white",
            "custom_color": "#ffffff", "builtin": False,
            "layers": [dict(default_layer)],
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
        cfg = self._form_cfg()
        cfg["name"] = self._name_edit.text().strip() or cfg.get("name", "Effet")
        self.effect_assigned.emit(btn_idx, cfg)
        self._refresh_assign_btns()
        self._rebuild_list()

    def _refresh_assign_btns(self):
        eff_name = self._all[self._sel].get("name", "") if self._all else ""
        for i, ab in enumerate(self._assign_btns):
            cfg_name = self._mw._button_effect_configs.get(i, {}).get("name", "")
            assigned = bool(cfg_name) and cfg_name == eff_name
            if assigned:
                ab.setStyleSheet(
                    "QPushButton { background: #00d4ff; color: #000; border: none;"
                    " border-radius: 5px; font-size: 11px; font-weight: bold; }"
                    "QPushButton:hover { background: #33ddff; }")
            else:
                other = bool(self._mw._button_effect_configs.get(i, {}).get("name", ""))
                if other:
                    ab.setStyleSheet(
                        "QPushButton { background: #1e1e1e; color: #555; border: 1px solid #333;"
                        " border-radius: 5px; font-size: 10px; }"
                        "QPushButton:hover { border-color: #00d4ff; color: #fff; }")
                else:
                    ab.setStyleSheet(
                        "QPushButton { background: #1a1a1a; color: #666; border: 1px solid #2a2a2a;"
                        " border-radius: 5px; font-size: 10px; }"
                        "QPushButton:hover { border-color: #00d4ff; color: #fff; }")
