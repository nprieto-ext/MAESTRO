"""
Composants UI pour le controleur AKAI
DualColorButton, EffectButton, FaderButton, ApcFader
"""
import json
from pathlib import Path
from PySide6.QtWidgets import QPushButton, QWidget, QMenu, QWidgetAction, QLabel, QHBoxLayout
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon


class DualColorButton(QPushButton):
    """Bouton avec deux couleurs en diagonale"""

    def __init__(self, color1, color2):
        super().__init__()
        self.color1 = color1
        self.color2 = color2
        self.setFixedSize(28, 28)
        self.active = False
        self.brightness = 0.3  # 30% par defaut

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculer les couleurs avec brightness
        c1 = QColor(
            int(self.color1.red() * self.brightness),
            int(self.color1.green() * self.brightness),
            int(self.color1.blue() * self.brightness)
        )
        c2 = QColor(
            int(self.color2.red() * self.brightness),
            int(self.color2.green() * self.brightness),
            int(self.color2.blue() * self.brightness)
        )

        # Diagonale couleur 1 (haut gauche)
        painter.setPen(Qt.NoPen)
        painter.setBrush(c1)
        points1 = [QPoint(0, 0), QPoint(28, 0), QPoint(0, 28)]
        painter.drawPolygon(QPolygon(points1))

        # Diagonale couleur 2 (bas droite)
        painter.setBrush(c2)
        points2 = [QPoint(28, 0), QPoint(28, 28), QPoint(0, 28)]
        painter.drawPolygon(QPolygon(points2))

        # Bordure
        if self.active:
            pen = QPen(QColor("#ffffff"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(1, 1, 26, 26, 4, 4)


EFFECT_PRESETS = [
    ("⭕ Aucun",           None,           "#2a2a2a"),
    ("⚡ Strobe",          "Strobe",        "#ffffff"),
    ("💥 Flash",           "Flash",         "#ffff00"),
    ("💜 Pulse",           "Pulse",         "#ff00ff"),
    ("🌊 Vague",           "Wave",          "#00ffff"),
    ("☄️ Comète",          "Comete",        "#ff8800"),
    ("🌈 Rainbow",         "Rainbow",       "#00ff00"),
    ("🌠 Etoile Filante",  "Etoile Filante","#aaddff"),
    ("🔥 Feu",             "Fire",          "#ff4400"),
    ("⬜ Passage Blanc",   "Chase",         "#e0e0e0"),
    ("↔️ Bascule",         "Bascule",       "#44ccff"),
]

# Effet par defaut pour chaque bouton (index 0-8)
DEFAULT_EFFECTS = [
    "Strobe", "Flash", "Pulse", "Wave",
    "Comete", "Rainbow", "Etoile Filante", "Chase", "Pulse"
]

def get_effect_emoji(effect_name):
    """Retourne l'emoji correspondant a un effet"""
    for label, name, _ in EFFECT_PRESETS:
        if name == effect_name:
            return label.split(" ")[0]
    return ""


class EffectButton(QPushButton):
    """Bouton d'effet carre rouge avec menu d'effets"""

    effect_config_selected = Signal(int, dict)  # (btn_index, config_dict)

    def __init__(self, index):
        super().__init__()
        self.index = index
        self.setFixedSize(16, 16)
        self.active = False
        # Effet par defaut selon la position
        if index < len(DEFAULT_EFFECTS):
            self.current_effect = DEFAULT_EFFECTS[index]
        else:
            self.current_effect = None
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_effects_menu)
        self.setToolTip(self._tooltip())
        self.update_style()

    def _tooltip(self):
        """Genere le tooltip avec emoji + nom de l'effet"""
        if not self.current_effect:
            return "Aucun effet"
        for label, name, _ in EFFECT_PRESETS:
            if name == self.current_effect:
                return label
        return self.current_effect

    def show_effects_menu(self, pos):
        """Affiche le menu des effets (chargés depuis l'éditeur d'effets)"""
        # Charger tous les effets : builtin + custom
        all_effects = []
        try:
            from effect_editor import BUILTIN_EFFECTS
            all_effects = list(BUILTIN_EFFECTS)
            effects_file = Path.home() / ".mystrow_effects.json"
            if effects_file.exists():
                custom = json.loads(effects_file.read_text(encoding="utf-8"))
                if isinstance(custom, list):
                    existing_names = {e["name"] for e in all_effects}
                    for e in custom:
                        if e.get("name") not in existing_names:
                            all_effects.append(e)
        except Exception:
            pass

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                padding: 4px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 3px;
                color: #e0e0e0;
            }
            QMenu::item:selected { background: #2a3a3a; color: #fff; }
            QMenu::item:disabled { color: #555; font-size: 10px; letter-spacing: 1px; }
            QMenu::separator { background: #333; height: 1px; margin: 3px 8px; }
        """)

        # Si current_effect est un nom de type legacy ("Strobe", "Chase"...) sans match
        # exact dans la liste, on fait un fallback par type pour trouver le premier match
        cur = self.current_effect
        name_is_full_match = cur and any(e.get("name") == cur for e in all_effects)

        def _is_checked(eff):
            name = eff.get("name", "")
            if name == cur:
                return True
            # Fallback : current_effect est un type legacy ("Strobe", "Flash"...)
            if not name_is_full_match and cur and eff.get("type") == cur:
                # Ne cocher que le premier de ce type
                first_of_type = next(
                    (e for e in all_effects if e.get("type") == cur), None
                )
                return first_of_type is not None and first_of_type.get("name") == name
            return False

        # Option "Aucun"
        act_none = menu.addAction("⭕  Aucun")
        act_none.setCheckable(True)
        act_none.setChecked(not cur)
        act_none.triggered.connect(lambda: self._select_editor_effect(None))
        menu.addSeparator()

        # Grouper par catégorie
        CATS = ["Strobe / Flash", "Mouvement", "Ambiance", "Couleur", "Spécial", "Personnalisés"]
        for cat in CATS:
            cat_effs = [e for e in all_effects if e.get("category") == cat]
            if not cat_effs:
                continue
            hdr = menu.addAction(f"  {cat.upper()}")
            hdr.setEnabled(False)
            for eff in cat_effs:
                name = eff.get("name", "")
                act = menu.addAction(f"  {name}")
                act.setCheckable(True)
                act.setChecked(_is_checked(eff))
                act.triggered.connect(lambda checked=False, e=dict(eff): self._select_editor_effect(e))

        # Effets sans catégorie connue
        other = [e for e in all_effects if e.get("category", "") not in CATS]
        if other:
            menu.addSeparator()
            for eff in other:
                name = eff.get("name", "")
                act = menu.addAction(f"  {name}")
                act.setCheckable(True)
                act.setChecked(_is_checked(eff))
                act.triggered.connect(lambda checked=False, e=dict(eff): self._select_editor_effect(e))

        menu.exec(self.mapToGlobal(pos))

    def _select_editor_effect(self, cfg_or_none):
        """Applique un effet sélectionné dans le menu (avec ou sans config)."""
        if cfg_or_none is None:
            self.current_effect = None
            self.active = False
        else:
            self.current_effect = cfg_or_none.get("name", "")
            self.active = bool(self.current_effect)
        self.setToolTip(self.current_effect or "Aucun effet")
        self.update_style()
        cfg = dict(cfg_or_none) if cfg_or_none else {}
        self.effect_config_selected.emit(self.index, cfg)

    def set_effect(self, effect):
        """Definit l'effet actuel"""
        self.current_effect = effect
        if effect:
            self.active = True
        else:
            self.active = False
        self.setToolTip(self._tooltip())
        self.update_style()
        print(f"Effet {self.index}: {effect}")

    def update_style(self):
        if self.active:
            self.setStyleSheet("""
                QPushButton {
                    background: #33ff33;
                    border: 2px solid #ffffff;
                    border-radius: 3px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: #116611;
                    border: 1px solid #114411;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background: #118811;
                }
            """)


class FaderButton(QPushButton):
    """Bouton mute au-dessus du fader"""

    def __init__(self, index, callback):
        super().__init__()
        self.index = index
        self.callback = callback
        self.setFixedSize(16, 16)
        self.active = False
        self.update_style()

    def update_style(self):
        if self.active:
            self.setStyleSheet("""
                QPushButton {
                    background: #ff0000;
                    border: 2px solid #ff3333;
                    border-radius: 3px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: #440000;
                    border: 1px solid #660000;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background: #660000;
                }
            """)

    def mousePressEvent(self, e):
        self.active = not self.active
        self.update_style()
        self.callback(self.index, self.active)
        super().mousePressEvent(e)


class ApcFader(QWidget):
    """Fader style AKAI APC"""

    def __init__(self, index, callback, vertical=True, label=""):
        super().__init__()
        self.index = index
        self.callback = callback
        self.value = 0
        self.vertical = vertical
        self.label = label
        if vertical:
            self.setFixedWidth(50)
            self.setMinimumHeight(200)
        else:
            self.setFixedSize(26, 110)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setBrush(QColor("#333"))
        if not self.vertical:
            p.drawRoundedRect(w//2 - 2, 6, 4, h - 12, 2, 2)
            pos = h - 15 - int((self.value / 100) * (h - 25))
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(2, pos, 22, 10, 2, 2)
        else:
            p.drawRoundedRect(w//2 - 2, 15, 4, h - 30, 2, 2)
            pos = h - 30 - int((self.value / 100) * (h - 45))
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(w//2 - 15, pos + 10, 30, 12, 3, 3)

    def mousePressEvent(self, e):
        self.update_value(e.position())

    def mouseMoveEvent(self, e):
        self.update_value(e.position())

    def update_value(self, pos):
        limit = self.height() - (45 if self.vertical else 25)
        offset = 30 if self.vertical else 15
        y = max(10, min(self.height() - 10, int(pos.y())))
        self.value = int((self.height() - offset - y) / limit * 100)
        self.value = max(0, min(100, self.value))
        self.callback(self.index, self.value)
        self.update()

    def set_value(self, value):
        """Definit la valeur du fader (0-100)"""
        self.value = max(0, min(100, value))
        self.update()


class CartoucheButton(QPushButton):
    """Bouton cartouche audio/video avec 3 etats: IDLE, PLAYING, STOPPED"""

    IDLE = 0
    PLAYING = 1
    STOPPED = 2

    COLORS = [
        QColor("#ff8800"),  # Orange
        QColor("#ffdd00"),  # Jaune
        QColor("#00cc44"),  # Vert
        QColor("#0088ff"),  # Bleu
    ]

    VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}
    AUDIO_EXTS = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.wma'}

    def __init__(self, index, callback):
        super().__init__()
        self.index = index
        self.callback = callback
        self.state = self.IDLE
        self.base_color = self.COLORS[index % len(self.COLORS)]
        self.media_path = None
        self.media_title = None
        self.media_icon = ""
        self.volume = 100  # Volume 0-100, defaut 100%
        self.setFixedHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self._update_style()

    def _update_style(self):
        if self.state == self.PLAYING:
            bg = self.base_color.name()
            border = "2px solid #ffffff"
            text_color = "black"
        else:
            r = int(self.base_color.red() * 0.3)
            g = int(self.base_color.green() * 0.3)
            b = int(self.base_color.blue() * 0.3)
            bg = QColor(r, g, b).name()
            border = "1px solid #2a2a2a"
            text_color = "white"

        if self.media_title:
            label = f"{self.media_icon} {self.media_title}" if self.media_icon else self.media_title
        else:
            label = f"Cartouche {self.index + 1}"
        vol_str = f"  {self.volume}%" if self.volume < 100 else ""
        self.setText(label + vol_str)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: {border};
                border-radius: 4px;
                color: {text_color};
                font-weight: bold;
                font-size: 11px;
                padding: 4px 8px;
                text-align: left;
            }}
            QPushButton:hover {{
                border: 1px solid #888;
            }}
        """)

    def set_idle(self):
        self.state = self.IDLE
        self._update_style()

    def set_playing(self):
        self.state = self.PLAYING
        self._update_style()

    def set_stopped(self):
        self.state = self.STOPPED
        self._update_style()

    def paintEvent(self, event):
        super().paintEvent(event)
        # Barre de volume en bas du bouton
        painter = QPainter(self)
        w = self.width()
        h = self.height()
        bar_h = 3
        bar_w = int((w - 4) * self.volume / 100)
        color = self.base_color if self.volume > 0 else QColor("#555")
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 160))
        painter.drawRoundedRect(2, h - bar_h - 1, bar_w, bar_h, 1, 1)
        painter.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.callback(self.index)
            e.accept()
            return
        super().mousePressEvent(e)
