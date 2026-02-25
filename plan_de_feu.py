"""
Plan de Feu - Visualisation des projecteurs (canvas 2D libre)
"""
import math
from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QGridLayout, QHBoxLayout,
    QLabel, QMenu, QWidgetAction, QPushButton, QSlider,
    QDialog, QTabWidget, QListWidget, QListWidgetItem, QSplitter,
    QFormLayout, QLineEdit, QComboBox, QSpinBox, QDialogButtonBox,
    QMessageBox, QSizePolicy, QApplication, QStackedWidget
)
from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QSize, Signal, QRectF
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPen, QBrush, QPainterPath, QPolygon,
    QLinearGradient, QRadialGradient,
)


class ColorPickerWidget(QWidget):
    """Gradient HSV cliquable/draggable - integre dans un menu contextuel"""

    colorSelected = Signal(QColor)

    def __init__(self, width=230, height=140, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CrossCursor)
        self._image = None
        self._marker_pos = None
        self._generate_gradient()

    def _generate_gradient(self):
        """Genere le gradient HSV: hue horizontal, blanc en haut, noir en bas"""
        w, h = self.width(), self.height()
        self._image = QImage(w, h, QImage.Format_RGB32)
        mid = h / 2.0
        for x in range(w):
            hue = x / w
            for y in range(h):
                if y <= mid:
                    sat = y / mid if mid > 0 else 1.0
                    val = 1.0
                else:
                    sat = 1.0
                    val = (h - y) / mid if mid > 0 else 0.0
                color = QColor.fromHsvF(
                    min(hue, 1.0), min(sat, 1.0), min(val, 1.0)
                )
                self._image.setPixelColor(x, y, color)

    def paintEvent(self, event):
        if not self._image:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawImage(0, 0, self._image)
        # Marqueur de position
        if self._marker_pos:
            x, y = self._marker_pos
            pen = QPen(QColor("white"), 2)
            painter.setPen(pen)
            painter.drawEllipse(QPoint(x, y), 6, 6)
            pen.setColor(QColor("black"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawEllipse(QPoint(x, y), 7, 7)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pick_color(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._pick_color(event.pos())

    def _pick_color(self, pos):
        x = max(0, min(pos.x(), self.width() - 1))
        y = max(0, min(pos.y(), self.height() - 1))
        self._marker_pos = (x, y)
        color = QColor(self._image.pixelColor(x, y))
        self.colorSelected.emit(color)
        self.update()


# Couleurs predefinies = meme ordre que les pads AKAI (sans noir)
PRESET_COLORS = [
    ("Blanc", QColor(255, 255, 255)),
    ("Rouge", QColor(255, 0, 0)),
    ("Orange", QColor(255, 136, 0)),
    ("Jaune", QColor(255, 221, 0)),
    ("Vert", QColor(0, 255, 0)),
    ("Cyan", QColor(0, 221, 221)),
    ("Bleu", QColor(0, 0, 255)),
    ("Magenta", QColor(255, 0, 255)),
]


class ColorPickerBlock(QFrame):
    """Bloc color picker compact entre Plan de Feu et Video"""

    def __init__(self, plan_de_feu, parent=None):
        super().__init__(parent)
        self.plan_de_feu = plan_de_feu

        self.setStyleSheet("ColorPickerBlock { border: none; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        title = QLabel("Color Picker")
        title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        title.setStyleSheet("color: #ccc;")
        layout.addWidget(title)

        self.picker = ColorPickerWidget(0, 100)
        self.picker.setFixedHeight(100)
        self.picker.setMinimumWidth(100)
        self.picker.colorSelected.connect(self._on_color_picked)
        layout.addWidget(self.picker)

        self.msg_label = QLabel()
        self.msg_label.setFont(QFont("Segoe UI", 9))
        self.msg_label.setStyleSheet("color: #f44336;")
        self.msg_label.setAlignment(Qt.AlignCenter)
        self.msg_label.hide()
        layout.addWidget(self.msg_label)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width() - 20
        if w > 0 and w != self.picker.width():
            self.picker.setFixedSize(w, 100)
            self.picker._generate_gradient()
            self.picker.update()

    def _on_color_picked(self, color):
        pdf = self.plan_de_feu
        if not pdf.selected_lamps:
            self.msg_label.setText("Merci de selectionner vos projecteurs")
            self.msg_label.show()
            QTimer.singleShot(2000, self.msg_label.hide)
            return

        targets = []
        for g, i in pdf.selected_lamps:
            projs = [p for p in pdf.projectors if p.group == g]
            if i < len(projs):
                targets.append((projs[i], g, i))

        for proj, g, i in targets:
            proj.base_color = color
            proj.level = 100
            proj.color = QColor(color.red(), color.green(), color.blue())

        if pdf.main_window and hasattr(pdf.main_window, 'dmx') and pdf.main_window.dmx:
            pdf.main_window.dmx.update_from_projectors(pdf.projectors)

        pdf.refresh()


# ── Bibliotheque de fixtures ─────────────────────────────────────────────────

FIXTURE_LIBRARY = {
    "PAR LED": [
        {"name": "PAR LED 5CH (RGB+Dim+Strobe)", "fixture_type": "PAR LED", "group": "face", "profile": "RGBDS"},
        {"name": "PAR LED 4CH (RGB+Dim)", "fixture_type": "PAR LED", "group": "face", "profile": "RGBD"},
        {"name": "PAR LED 3CH (RGB)", "fixture_type": "PAR LED", "group": "face", "profile": "RGB"},
        {"name": "PAR LED RGBW 4CH", "fixture_type": "PAR LED", "group": "face", "profile": "RGBW"},
        {"name": "PAR LED RGBW+Dim 5CH", "fixture_type": "PAR LED", "group": "face", "profile": "RGBWD"},
        {"name": "PAR contre 5CH (Contre)", "fixture_type": "PAR LED", "group": "contre", "profile": "RGBDS"},
    ],
    "Moving Head": [
        {"name": "Moving Head 8CH", "fixture_type": "Moving Head", "group": "lyre", "profile": "MOVING_8CH"},
        {"name": "Moving Head RGB 9CH", "fixture_type": "Moving Head", "group": "lyre", "profile": "MOVING_RGB"},
        {"name": "Moving Head RGBW 9CH", "fixture_type": "Moving Head", "group": "lyre", "profile": "MOVING_RGBW"},
    ],
    "Barre LED": [
        {"name": "Barre LED RGB 5CH", "fixture_type": "Barre LED", "group": "barre", "profile": "LED_BAR_RGB"},
    ],
    "Stroboscope": [
        {"name": "Stroboscope 2CH", "fixture_type": "Stroboscope", "group": "strobe", "profile": "STROBE_2CH"},
    ],
    "Machine a fumee": [
        {"name": "Machine a fumee 2CH", "fixture_type": "Machine a fumee", "group": "fumee", "profile": "2CH_FUMEE"},
    ],
}

# Positions par defaut sur le canvas (coordonnees normalisees 0-1)
_DEFAULT_POSITIONS = {
    "face":    lambda li, n: (0.20 + li * 0.60 / max(n - 1, 1), 0.78),
    "contre":  lambda li, n: (0.15 + li * 0.70 / max(n - 1, 1), 0.10),
    "douche1": lambda li, n: (0.24 + li * 0.08, 0.50),
    "douche2": lambda li, n: (0.46 + li * 0.08, 0.50),
    "douche3": lambda li, n: (0.68 + li * 0.08, 0.50),
    "lat":     lambda li, n: (0.07 if li == 0 else 0.93, 0.40),
    "public":  lambda li, n: (0.50, 0.90),
    "fumee":   lambda li, n: (0.10, 0.90),
    "lyre":    lambda li, n: (0.15 + li * 0.70 / max(n - 1, 1), 0.25),
    "barre":   lambda li, n: (0.15 + li * 0.70 / max(n - 1, 1), 0.35),
    "strobe":  lambda li, n: (0.15 + li * 0.70 / max(n - 1, 1), 0.45),
}

_MENU_STYLE = """
QMenu {
    background: #1e1e1e;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 6px;
    color: white;
    font-size: 11px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 3px;
}
QMenu::item:selected {
    background: #333;
}
QMenu::separator {
    height: 1px;
    background: #3a3a3a;
    margin: 4px 8px;
}
"""


# Couleurs de groupe pour les anneaux indicateurs
_GROUP_COLORS = {
    "face":    "#ff8844",
    "contre":  "#4488ff",
    "douche1": "#44cc88",
    "douche2": "#44cc88",
    "douche3": "#44cc88",
    "lat":     "#aa55ff",
    "lyre":    "#ff44cc",
    "barre":   "#44aaff",
    "strobe":  "#ffee44",
    "fumee":   "#88aaaa",
    "public":  "#ff6655",
}

# ── FixtureCanvas ─────────────────────────────────────────────────────────────

class FixtureCanvas(QWidget):
    """Canvas 2D libre - toutes les fixtures sont dessinees via paintEvent"""

    def __init__(self, pdf, parent=None):
        super().__init__(parent)
        self.pdf = pdf
        self.setFocusPolicy(Qt.ClickFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        # Mode edition : True dans le dialog Patch DMX, False sur la vue principale
        self._editable = getattr(pdf, '_canvas_editable', True)

        # Mode compact : icones plus petites, sans labels (utilisé dans la vue principale)
        self.compact = False

        self._guides      = []   # Smart Guides temporaires pendant le drag

        self._drag_index  = None
        self._drag_offset = QPoint()
        self._drag_starts = {}      # {proj_idx: (norm_x, norm_y)} pour multi-drag
        self._hover_index = None
        self._rubber_origin = None
        self._rubber_rect   = None

    # ── Helpers de position ─────────────────────────────────────────

    def _get_canvas_pos(self, i):
        """Retourne (px, py) en pixels pour la fixture i"""
        proj = self.pdf.projectors[i]
        w, h = max(self.width(), 1), max(self.height(), 1)
        cx = getattr(proj, 'canvas_x', None)
        cy = getattr(proj, 'canvas_y', None)
        if cx is not None and cy is not None:
            return int(cx * w), int(cy * h)
        group = proj.group
        group_indices = [j for j, p in enumerate(self.pdf.projectors) if p.group == group]
        li = group_indices.index(i) if i in group_indices else 0
        n = len(group_indices)
        pos_fn = _DEFAULT_POSITIONS.get(group, lambda li, n: (0.5, 0.5))
        fx, fy = pos_fn(li, n)
        return int(fx * w), int(fy * h)

    def _get_norm_pos(self, i):
        """Retourne la position normalisee (0-1) de la fixture i"""
        w, h = max(self.width(), 1), max(self.height(), 1)
        px, py = self._get_canvas_pos(i)
        return px / w, py / h

    def _local_idx(self, i):
        """Retourne (group, local_idx) pour la fixture i"""
        proj = self.pdf.projectors[i]
        group = proj.group
        group_indices = [j for j, p in enumerate(self.pdf.projectors) if p.group == group]
        li = group_indices.index(i) if i in group_indices else 0
        return group, li

    def _fixture_at(self, pos):
        """Retourne l'index de la fixture sous pos, ou None"""
        px, py = pos.x(), pos.y()
        for i in range(len(self.pdf.projectors) - 1, -1, -1):
            cx, cy = self._get_canvas_pos(i)
            ftype = getattr(self.pdf.projectors[i], 'fixture_type', 'PAR LED')
            if ftype == "Barre LED":
                if abs(px - cx) <= 16 and abs(py - cy) <= 6:
                    return i
            elif ftype == "Machine a fumee":
                if abs(px - cx) <= 13 and abs(py - cy) <= 7:
                    return i
            else:
                if (px - cx) ** 2 + (py - cy) ** 2 <= 13 * 13:
                    return i
        return None

    # ── Dessin ─────────────────────────────────────────────────────

    def _get_fill_color(self, proj):
        htp = self.pdf._htp_overrides
        if htp and id(proj) in htp:
            level, color = htp[id(proj)][:2]
            if level > 0 and not proj.muted:
                return QColor(color)
            return QColor("#1a1a1a")
        if proj.muted or proj.level == 0:
            return QColor("#1a1a1a")
        return QColor(proj.color)

    def _draw_fixture(self, painter, cx, cy, proj, is_selected, is_hover):
        """Dessine une fixture avec glow, forme adaptee et indicateurs visuels"""
        ftype      = getattr(proj, 'fixture_type', 'PAR LED')
        fill_color = self._get_fill_color(proj)
        r          = 9 if self.compact else 13
        is_lit     = not proj.muted and proj.level > 0
        gc         = QColor(_GROUP_COLORS.get(proj.group, "#555555"))

        # Dimensions dérivées de r pour barre et fumee
        barre_hw = int(r * 1.23); barre_hh = max(3, int(r * 0.38))
        fumee_hw = int(r * 0.92); fumee_hh = max(3, int(r * 0.46))

        # ── Halo de lumiere (quand allumee) ─────────────────────
        if is_lit:
            fc      = fill_color
            glow_r  = r + 9 if self.compact else r + 14
            grad    = QRadialGradient(float(cx), float(cy), float(glow_r))
            grad.setColorAt(0.0, QColor(fc.red(), fc.green(), fc.blue(), 110))
            grad.setColorAt(0.5, QColor(fc.red(), fc.green(), fc.blue(), 35))
            grad.setColorAt(1.0, QColor(fc.red(), fc.green(), fc.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QPoint(cx, cy), glow_r, glow_r)

        # ── Contour (selection / survol / groupe) ────────────────
        if is_selected:
            pen = QPen(QColor("#00d4ff"), 3)
        elif is_hover:
            pen = QPen(QColor("#cccccc"), 2)
        else:
            pen = QPen(gc, 1)

        painter.setPen(pen)
        painter.setBrush(QBrush(fill_color))

        if ftype == "Moving Head":
            # Cone de faisceau (dessine avant le losange)
            if is_lit:
                beam_col = QColor(fill_color)
                beam_col.setAlpha(20)
                painter.setBrush(QBrush(beam_col))
                painter.setPen(Qt.NoPen)
                cone = QPolygon([
                    QPoint(cx - r // 2, cy + r),
                    QPoint(cx + r // 2, cy + r),
                    QPoint(cx + r * 3,  cy + r * 5),
                    QPoint(cx - r * 3,  cy + r * 5),
                ])
                painter.drawPolygon(cone)
            painter.setPen(pen)
            painter.setBrush(QBrush(fill_color))
            painter.drawPolygon(QPolygon([
                QPoint(cx,     cy - r),
                QPoint(cx + r, cy),
                QPoint(cx,     cy + r),
                QPoint(cx - r, cy),
            ]))

        elif ftype == "Barre LED":
            painter.drawRoundedRect(QRect(cx - barre_hw, cy - barre_hh, barre_hw * 2, barre_hh * 2), 3, 3)
            # Segments internes
            if is_lit:
                seg_col = QColor(fill_color)
                seg_col.setAlpha(160)
                painter.setPen(QPen(seg_col, 1))
                seg_step = max(4, barre_hw * 2 // 4)
                for seg in range(1, 4):
                    sx = cx - barre_hw + seg * seg_step
                    painter.drawLine(sx, cy - barre_hh + 1, sx, cy + barre_hh - 1)

        elif ftype == "Stroboscope":
            inner_r = r // 2
            pts = [
                QPoint(
                    int(cx + (r if k % 2 == 0 else inner_r) * math.cos(math.pi / 2 + k * math.pi / 6)),
                    int(cy - (r if k % 2 == 0 else inner_r) * math.sin(math.pi / 2 + k * math.pi / 6))
                )
                for k in range(12)
            ]
            painter.drawPolygon(QPolygon(pts))

        elif ftype == "Machine a fumee":
            painter.drawEllipse(QRect(cx - fumee_hw, cy - fumee_hh, fumee_hw * 2, fumee_hh * 2))
            # Nuages de fumee (petits cercles)
            if is_lit:
                smoke_col = QColor(200, 200, 200, 40)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(smoke_col))
                for ox, oy, sr in [(-7, -10, 5), (0, -12, 6), (7, -10, 5), (-4, -16, 4), (4, -16, 4)]:
                    painter.drawEllipse(QPoint(cx + ox, cy + oy), sr, sr)

        else:  # PAR LED (defaut)
            painter.drawEllipse(QPoint(cx, cy), r, r)

        # ── Croix mute ──────────────────────────────────────────
        if proj.muted:
            painter.setPen(QPen(QColor("#ff4444"), 2))
            painter.drawLine(cx - 5, cy - 5, cx + 5, cy + 5)
            painter.drawLine(cx + 5, cy - 5, cx - 5, cy + 5)

    def _draw_hover_card(self, painter, cx, cy, proj):
        """Tooltip flottant avec infos de la fixture survolee"""
        gd = {}
        if hasattr(self.pdf, 'main_window') and hasattr(self.pdf.main_window, 'GROUP_DISPLAY'):
            gd = self.pdf.main_window.GROUP_DISPLAY
        ftype = getattr(proj, 'fixture_type', 'PAR LED')
        lines = [
            proj.name or proj.group,
            f"{ftype}  ·  {gd.get(proj.group, proj.group)}",
            f"CH {proj.start_address}  ·  Niveau {proj.level}%" + ("  (mute)" if proj.muted else ""),
        ]
        card_w, line_h = 178, 15
        card_h = len(lines) * line_h + 14
        # Positionner à droite de la fixture; basculer à gauche si ça déborde
        if cx + 26 + card_w < self.width() - 4:
            cx_card = cx + 26
        else:
            cx_card = max(4, cx - card_w - 10)
        cy_card = max(6, cy - card_h - 10)

        path = QPainterPath()
        path.addRoundedRect(QRectF(cx_card, cy_card, card_w, card_h), 7, 7)
        painter.fillPath(path, QColor("#1b1b26"))
        painter.setPen(QPen(QColor("#2e2e44"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.setPen(QColor("#e8e8e8"))
        painter.drawText(
            QRect(cx_card + 10, cy_card + 6, card_w - 20, line_h),
            Qt.AlignLeft, lines[0]
        )
        painter.setFont(QFont("Segoe UI", 8))
        for j, line in enumerate(lines[1:], 1):
            painter.setPen(QColor("#777777"))
            painter.drawText(
                QRect(cx_card + 10, cy_card + 6 + j * line_h, card_w - 20, line_h),
                Qt.AlignLeft, line
            )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        W, H = self.width(), self.height()
        SB_H = 22   # hauteur barre de statut

        # ── Fond general ─────────────────────────────────────────
        painter.fillRect(self.rect(), QColor("#0a0a0a"))

        # ── Zone scene ───────────────────────────────────────────
        mx  = int(W * 0.04)
        my  = int(H * 0.05)
        sw  = W - 2 * mx
        sh  = H - 2 * my - SB_H
        sx, sy = mx, my

        stage_path = QPainterPath()
        stage_path.addRoundedRect(QRectF(sx, sy, sw, sh), 14, 14)
        painter.fillPath(stage_path, QColor("#0d0d0d"))

        # Degrade zone CONTRE (haut, bleu subtil)
        g_top = QLinearGradient(float(sx), float(sy), float(sx), float(sy + sh * 0.30))
        g_top.setColorAt(0.0, QColor(30, 60, 150, 20))
        g_top.setColorAt(1.0, QColor(0,   0,   0,  0))
        painter.fillPath(stage_path, QBrush(g_top))

        # Degrade zone FACE (bas, orange subtil)
        g_bot = QLinearGradient(float(sx), float(sy + sh * 0.70), float(sx), float(sy + sh))
        g_bot.setColorAt(0.0, QColor(0,   0,  0,  0))
        g_bot.setColorAt(1.0, QColor(160, 80, 20, 20))
        painter.fillPath(stage_path, QBrush(g_bot))

        # Grille tres discrete
        painter.setPen(QPen(QColor(255, 255, 255, 7), 1))
        for col in range(1, 4):
            x = sx + col * sw // 4
            painter.drawLine(x, sy + 10, x, sy + sh - 10)
        for row in range(1, 4):
            y = sy + row * sh // 4
            painter.drawLine(sx + 10, y, sx + sw - 10, y)

        # Labels de zone
        painter.setFont(QFont("Segoe UI", 7))
        painter.setPen(QColor("#242424"))
        painter.drawText(QRect(sx, sy + 5,       sw, 14), Qt.AlignHCenter, "CONTRE / HAUT")
        painter.drawText(QRect(sx, sy + sh - 18, sw, 14), Qt.AlignHCenter, "FACE / BAS")

        # Bordure scene
        painter.setPen(QPen(QColor("#1c1c1c"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(stage_path)

        # ── Fixtures ─────────────────────────────────────────────
        font_name = QFont("Segoe UI", 8)
        font_ch   = QFont("Segoe UI", 7)

        for i, proj in enumerate(self.pdf.projectors):
            cx, cy = self._get_canvas_pos(i)
            group, local_idx = self._local_idx(i)
            key = (group, local_idx)
            is_selected = key in self.pdf.selected_lamps
            is_hover    = (i == self._hover_index)

            self._draw_fixture(painter, cx, cy, proj, is_selected, is_hover)

            if not self.compact:
                # Nom (en cyan si selectionne)
                painter.setFont(font_name)
                painter.setPen(QColor("#00d4ff" if is_selected else "#888888"))
                painter.drawText(QRect(cx - 38, cy + 16, 76, 14), Qt.AlignCenter,
                                 (proj.name[:11] if proj.name else group[:11]))

                # Adresse DMX discrete
                painter.setFont(font_ch)
                painter.setPen(QColor("#333333"))
                painter.drawText(QRect(cx - 22, cy + 28, 44, 12), Qt.AlignCenter,
                                 f"CH {proj.start_address}")

        # ── Rubber band ───────────────────────────────────────────
        if self._rubber_rect and not self._rubber_rect.isNull():
            painter.setPen(QPen(QColor("#00d4ff"), 1, Qt.DashLine))
            painter.setBrush(QColor(0, 212, 255, 18))
            painter.drawRect(self._rubber_rect)

        # ── Smart Guides ──────────────────────────────────────────
        if self._guides:
            self._draw_guides(painter, W, H)

        # ── Tooltip survol (masque pendant drag) ─────────────────
        if self._hover_index is not None and self._drag_index is None:
            hx, hy = self._get_canvas_pos(self._hover_index)
            self._draw_hover_card(painter, hx, hy, self.pdf.projectors[self._hover_index])

        # ── Barre de statut (bas du canvas) ──────────────────────
        n_fix = len(self.pdf.projectors)
        n_sel = len(self.pdf.selected_lamps)
        painter.fillRect(QRect(0, H - SB_H, W, SB_H), QColor("#080808"))
        painter.setPen(QPen(QColor("#1a1a1a"), 1))
        painter.drawLine(0, H - SB_H, W, H - SB_H)

        info_left = f"  {n_fix} fixture{'s' if n_fix != 1 else ''}"
        if n_sel:
            info_left += f"  /  {n_sel} selectionnee{'s' if n_sel != 1 else ''}"
        if self._editable:
            info_right = "Glisser = deplacer   Shift+glisser = snap   Double-clic = editer   Ctrl+A = tout sel.   "
        else:
            info_right = "Vue uniquement — edition dans Patch DMX > Plan de feu   "

        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#3a3a3a"))
        painter.drawText(QRect(0, H - SB_H, W,   SB_H), Qt.AlignVCenter | Qt.AlignLeft,  info_left)
        painter.setPen(QColor("#1e1e1e"))
        painter.drawText(QRect(0, H - SB_H, W-4, SB_H), Qt.AlignVCenter | Qt.AlignRight, info_right)

        painter.end()

    # ── Interactions souris ─────────────────────────────────────────

    def mousePressEvent(self, event):
        pos = event.pos()
        idx = self._fixture_at(pos)

        if event.button() == Qt.LeftButton:
            if idx is not None:
                group, local_idx = self._local_idx(idx)
                key = (group, local_idx)
                if event.modifiers() & Qt.ControlModifier:
                    if key in self.pdf.selected_lamps:
                        self.pdf.selected_lamps.discard(key)
                    else:
                        self.pdf.selected_lamps.add(key)
                elif key not in self.pdf.selected_lamps:
                    self.pdf.selected_lamps = {key}
                # Drag uniquement en mode edition
                if self._editable:
                    cx, cy = self._get_canvas_pos(idx)
                    self._drag_index  = idx
                    self._drag_offset = pos - QPoint(cx, cy)
                    g_cnt = {}
                    self._drag_starts = {}
                    for j, p in enumerate(self.pdf.projectors):
                        li = g_cnt.get(p.group, 0)
                        if (p.group, li) in self.pdf.selected_lamps:
                            self._drag_starts[j] = self._get_norm_pos(j)
                        g_cnt[p.group] = li + 1
                self.update()
            else:
                if not (event.modifiers() & Qt.ControlModifier):
                    self.pdf.selected_lamps.clear()
                self._rubber_origin = pos
                self._rubber_rect   = QRect(pos, QSize())
                self.update()

        elif event.button() == Qt.RightButton:
            if idx is not None:
                group, local_idx = self._local_idx(idx)
                key = (group, local_idx)
                if key not in self.pdf.selected_lamps:
                    self.pdf.selected_lamps = {key}
                    self.update()
                self.pdf._show_fixture_context_menu(event.globalPos(), idx)
            else:
                self.pdf._show_canvas_context_menu(event.globalPos())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self._editable:
            idx = self._fixture_at(event.pos())
            if idx is not None:
                self.pdf._edit_fixture(idx)

    def _resolve_overlaps(self, canvas_w, canvas_h, dragged_set):
        """Pousse les fixtures non-draguées qui chevauchent une fixture draguée."""
        r = 9 if self.compact else 13
        min_sep = r * 2 + 6   # distance min centre à centre (pixels)
        SB_H = 22
        x_min, x_max = 0.05, 0.95
        y_min = 0.06
        y_max = 1.0 - 0.05 - SB_H / max(canvas_h, 1)

        for i, pi in enumerate(self.pdf.projectors):
            if i in dragged_set:
                continue
            if pi.canvas_x is None or pi.canvas_y is None:
                continue  # Fixture auto-positionnée, ne pas forcer sa position
            xi = pi.canvas_x * canvas_w
            yi = pi.canvas_y * canvas_h

            for j in dragged_set:
                pj = self.pdf.projectors[j]
                xj = (pj.canvas_x or 0.5) * canvas_w
                yj = (pj.canvas_y or 0.5) * canvas_h

                dx, dy = xi - xj, yi - yj
                dist = math.sqrt(dx * dx + dy * dy)

                if dist < min_sep:
                    if dist > 0.5:
                        scale = min_sep / dist
                        xi = xj + dx * scale
                        yi = yj + dy * scale
                    else:
                        xi = xj + min_sep   # chevauchement exact : décaler à droite
                    pi.canvas_x = max(x_min, min(x_max, xi / canvas_w))
                    pi.canvas_y = max(y_min, min(y_max, yi / canvas_h))
                    xi = pi.canvas_x * canvas_w
                    yi = pi.canvas_y * canvas_h

    def _fixture_bbox_px(self, i):
        """Retourne (cx, cy, hw, hh) en pixels pour la fixture i (demi-largeur / demi-hauteur)."""
        cx, cy = self._get_canvas_pos(i)
        r = 9 if self.compact else 13
        ftype = getattr(self.pdf.projectors[i], 'fixture_type', 'PAR LED')
        if ftype == "Barre LED":
            hw = int(r * 1.23)
            hh = max(3, int(r * 0.38))
        elif ftype == "Machine a fumee":
            hw = int(r * 0.92)
            hh = max(3, int(r * 0.46))
        else:
            hw = hh = r
        return cx, cy, hw, hh

    def _compute_snap_guides(self, raw_x, raw_y, canvas_w, canvas_h, dragged_set):
        """
        Calcule le snap et les guides visuels en O(n).
        Retourne (snapped_norm_x, snapped_norm_y, guides_list).
        """
        SNAP_PX   = 8   # Seuil de snap en pixels
        ALIGN_THR = 8   # Tolérance d'alignement pour afficher la distance

        px = raw_x * canvas_w
        py = raw_y * canvas_h

        # Bbox de la fixture principale draguée
        drag_idx        = next(iter(dragged_set))
        _, _, dhw, dhh  = self._fixture_bbox_px(drag_idx)

        best_x, best_dx = px, SNAP_PX + 1
        best_y, best_dy = py, SNAP_PX + 1
        guides          = []

        # Snap au centre du canvas
        cx_mid = canvas_w * 0.5
        cy_mid = canvas_h * 0.5
        dx = abs(px - cx_mid)
        if dx < SNAP_PX and dx < best_dx:
            best_x, best_dx = cx_mid, dx
        dy = abs(py - cy_mid)
        if dy < SNAP_PX and dy < best_dy:
            best_y, best_dy = cy_mid, dy

        # Listes de fixtures alignées (candidats mesure de distance)
        aligned_h = []   # alignées horizontalement (même Y ± ALIGN_THR)
        aligned_v = []   # alignées verticalement   (même X ± ALIGN_THR)

        # ── Boucle unique O(n) ────────────────────────────────────────
        for i in range(len(self.pdf.projectors)):
            if i in dragged_set:
                continue
            ocx, ocy, ohw, ohh = self._fixture_bbox_px(i)

            # Snap X (axe vertical — aligner les centres X)
            dx = abs(px - ocx)
            if dx < SNAP_PX and dx < best_dx:
                best_x, best_dx = ocx, dx

            # Snap Y (axe horizontal — aligner les centres Y)
            dy = abs(py - ocy)
            if dy < SNAP_PX and dy < best_dy:
                best_y, best_dy = ocy, dy

            # Candidats mesure bord-à-bord
            if abs(py - ocy) <= ALIGN_THR:
                aligned_h.append((ocx, ocy, ohw, ohh))
            if abs(px - ocx) <= ALIGN_THR:
                aligned_v.append((ocx, ocy, ohw, ohh))

        snapped_x = best_x / canvas_w
        snapped_y = best_y / canvas_h

        # Guides d'alignement (lignes cyan pointillées)
        if best_dx <= SNAP_PX:
            guides.append({'type': 'v', 'x': snapped_x})
        if best_dy <= SNAP_PX:
            guides.append({'type': 'h', 'y': snapped_y})

        spx = best_x   # position snappée en pixels
        spy = best_y

        # ── Mesures de distance horizontales (bord droit drag ↔ bord gauche other) ──
        for (ocx, ocy, ohw, ohh) in aligned_h:
            if spx <= ocx:
                e_drag  = spx + dhw   # bord droit de la fixture draguée
                e_other = ocx - ohw   # bord gauche de l'autre fixture
            else:
                e_drag  = spx - dhw   # bord gauche drag
                e_other = ocx + ohw   # bord droit other
            gap = int(e_other - e_drag) if spx <= ocx else int(e_drag - e_other)
            if gap < 0:
                continue              # chevauchement : pas d'affichage
            guides.append({
                'type': 'dist_h',
                'x1':   min(e_drag, e_other) / canvas_w,
                'x2':   max(e_drag, e_other) / canvas_w,
                'y':    spy / canvas_h,
                'gap':  gap,
            })

        # ── Mesures de distance verticales (bord bas drag ↔ bord haut other) ──
        for (ocx, ocy, ohw, ohh) in aligned_v:
            if spy <= ocy:
                e_drag  = spy + dhh   # bord bas drag
                e_other = ocy - ohh   # bord haut other
            else:
                e_drag  = spy - dhh   # bord haut drag
                e_other = ocy + ohh   # bord bas other
            gap = int(e_other - e_drag) if spy <= ocy else int(e_drag - e_other)
            if gap < 0:
                continue
            guides.append({
                'type': 'dist_v',
                'y1':   min(e_drag, e_other) / canvas_h,
                'y2':   max(e_drag, e_other) / canvas_h,
                'x':    spx / canvas_w,
                'gap':  gap,
            })

        return snapped_x, snapped_y, guides

    def _draw_guides(self, painter, canvas_w, canvas_h):
        """Dessine les Smart Guides : lignes d'alignement cyan + mesures de distance."""
        pen_align = QPen(QColor(0, 212, 255, 160), 1, Qt.DashLine)
        pen_align.setDashPattern([6, 4])
        pen_dist  = QPen(QColor(0, 212, 255, 210), 1)
        font_dist = QFont("Segoe UI", 8)
        font_dist.setBold(True)

        for g in self._guides:
            gtype = g.get('type')

            if gtype == 'v':
                gx = int(g['x'] * canvas_w)
                painter.setPen(pen_align)
                painter.drawLine(gx, 0, gx, canvas_h)

            elif gtype == 'h':
                gy = int(g['y'] * canvas_h)
                painter.setPen(pen_align)
                painter.drawLine(0, gy, canvas_w, gy)

            elif gtype == 'dist_h':
                x1_px = int(g['x1'] * canvas_w)
                x2_px = int(g['x2'] * canvas_w)
                y_px  = int(g['y']  * canvas_h)
                gap   = g['gap']
                mid_x = (x1_px + x2_px) // 2

                painter.setPen(pen_dist)
                painter.drawLine(x1_px, y_px, x2_px, y_px)
                painter.drawLine(x1_px, y_px - 5, x1_px, y_px + 5)
                painter.drawLine(x2_px, y_px - 5, x2_px, y_px + 5)

                label = f"{gap} px"
                painter.setFont(font_dist)
                fm = painter.fontMetrics()
                lw = fm.horizontalAdvance(label) + 10
                lh = 16
                lx = mid_x - lw // 2
                ly = y_px - lh - 5
                if ly < 2:
                    ly = y_px + 7
                painter.fillRect(QRect(lx, ly, lw, lh), QColor(0, 0, 0, 200))
                painter.setPen(QPen(QColor(0, 212, 255, 70), 1))
                painter.drawRect(QRect(lx, ly, lw, lh))
                painter.setPen(QColor(0, 212, 255, 255))
                painter.drawText(QRect(lx, ly, lw, lh), Qt.AlignCenter, label)

            elif gtype == 'dist_v':
                y1_px = int(g['y1'] * canvas_h)
                y2_px = int(g['y2'] * canvas_h)
                x_px  = int(g['x']  * canvas_w)
                gap   = g['gap']
                mid_y = (y1_px + y2_px) // 2

                painter.setPen(pen_dist)
                painter.drawLine(x_px, y1_px, x_px, y2_px)
                painter.drawLine(x_px - 5, y1_px, x_px + 5, y1_px)
                painter.drawLine(x_px - 5, y2_px, x_px + 5, y2_px)

                label = f"{gap} px"
                painter.setFont(font_dist)
                fm = painter.fontMetrics()
                lw = fm.horizontalAdvance(label) + 10
                lh = 16
                lx = x_px + 8
                ly = mid_y - lh // 2
                if lx + lw > canvas_w - 4:
                    lx = x_px - lw - 8
                painter.fillRect(QRect(lx, ly, lw, lh), QColor(0, 0, 0, 200))
                painter.setPen(QPen(QColor(0, 212, 255, 70), 1))
                painter.drawRect(QRect(lx, ly, lw, lh))
                painter.setPen(QColor(0, 212, 255, 255))
                painter.drawText(QRect(lx, ly, lw, lh), Qt.AlignCenter, label)

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if self._editable and self._drag_index is not None and (event.buttons() & Qt.LeftButton):
            w, h = max(self.width(), 1), max(self.height(), 1)
            SB_H = 22
            # Bounds = stage rectangle (4% / 5% margins, status bar at bottom)
            mx_f = 0.04; my_f = 0.05
            x_min = mx_f + 0.01; x_max = 1.0 - mx_f - 0.01
            y_min = my_f + 0.01; y_max = 1.0 - my_f - (SB_H / h) - 0.01

            new_raw = pos - self._drag_offset
            new_x   = max(x_min, min(x_max, new_raw.x() / w))
            new_y   = max(y_min, min(y_max, new_raw.y() / h))

            if event.modifiers() & Qt.ShiftModifier:
                snap  = 1.0 / 16.0
                new_x = round(new_x / snap) * snap
                new_y = round(new_y / snap) * snap
                self._guides = []
            else:
                # Smart Guides : snap aux axes des autres fixtures
                dragged = set(self._drag_starts.keys()) or {self._drag_index}
                snapped_x, snapped_y, self._guides = self._compute_snap_guides(
                    new_x, new_y, w, h, dragged)
                new_x = max(x_min, min(x_max, snapped_x))
                new_y = max(y_min, min(y_max, snapped_y))

            orig = self._drag_starts.get(self._drag_index, (None, None))
            if orig[0] is not None:
                dx, dy = new_x - orig[0], new_y - orig[1]
                for j, (ox, oy) in self._drag_starts.items():
                    p = self.pdf.projectors[j]
                    p.canvas_x = max(x_min, min(x_max, ox + dx))
                    p.canvas_y = max(y_min, min(y_max, oy + dy))
            else:
                proj = self.pdf.projectors[self._drag_index]
                proj.canvas_x = new_x
                proj.canvas_y = new_y

            # Anti-overlap : pousser les fixtures non-draguées qui chevauchent.
            # Désactivé quand des Smart Guides snappent : l'anti-overlap fighterait
            # la fixture cible de l'alignement en la poussant au loin à chaque frame.
            if not self._guides:
                self._resolve_overlaps(w, h, set(self._drag_starts.keys()) or {self._drag_index})
            self.update()

        elif self._rubber_origin is not None and (event.buttons() & Qt.LeftButton):
            self._rubber_rect = QRect(self._rubber_origin, pos).normalized()
            self.update()

        else:
            new_hover = self._fixture_at(pos)
            if new_hover != self._hover_index:
                self._hover_index = new_hover
                # Curseur contextuel
                if new_hover is not None and self._editable:
                    self.setCursor(Qt.SizeAllCursor)
                elif new_hover is not None:
                    self.setCursor(Qt.PointingHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._drag_index is not None:
                self._drag_index  = None
                self._drag_starts = {}
                self._guides      = []   # Effacer les smart guides au release
                if self.pdf.main_window and hasattr(self.pdf.main_window, 'save_dmx_patch_config'):
                    self.pdf.main_window.save_dmx_patch_config()
            elif self._rubber_rect and self._rubber_origin is not None:
                for i in range(len(self.pdf.projectors)):
                    cx, cy = self._get_canvas_pos(i)
                    if self._rubber_rect.contains(QPoint(cx, cy)):
                        group, local_idx = self._local_idx(i)
                        self.pdf.selected_lamps.add((group, local_idx))
                self._rubber_rect   = None
                self._rubber_origin = None
                self.update()

    def leaveEvent(self, event):
        if self._hover_index is not None:
            self._hover_index = None
            self.update()

    # ── Clavier ─────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_A and (event.modifiers() & Qt.ControlModifier):
            for i in range(len(self.pdf.projectors)):
                group, local_idx = self._local_idx(i)
                self.pdf.selected_lamps.add((group, local_idx))
            self.update()
        elif event.key() == Qt.Key_Escape:
            self.pdf.selected_lamps.clear()
            self.update()
        elif event.key() == Qt.Key_Delete:
            if hasattr(self.pdf, '_delete_selected_fixtures'):
                self.pdf._delete_selected_fixtures()
        else:
            super().keyPressEvent(event)


# ── PlanDeFeu ─────────────────────────────────────────────────────────────────

class PlanDeFeu(QFrame):
    """Visualisation du plan de feu - canvas 2D libre"""

    def __init__(self, projectors, main_window=None):
        super().__init__()
        self.setFocusPolicy(Qt.ClickFocus)
        self.projectors = projectors
        self.main_window = main_window
        self.selected_lamps = set()   # set of (group, local_idx)
        self._htp_overrides = None    # dict {id(proj): (level, QColor)} ou None
        self._canvas_editable = False  # Vue principale : lecture seule (edition dans Patch DMX)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Barre d'outils ──────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Lumieres")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        toolbar.addWidget(title)
        toolbar.addStretch()

        self.dmx_toggle_btn = QPushButton("ON")
        self.dmx_toggle_btn.setCheckable(True)
        self.dmx_toggle_btn.setChecked(True)
        self.dmx_toggle_btn.setFixedSize(50, 24)
        self.dmx_toggle_btn.setStyleSheet("""
            QPushButton {
                background: #228b22; color: white; border: none;
                border-radius: 12px; font-weight: bold; font-size: 10px;
            }
            QPushButton:!checked {
                background: #8b0000;
            }
        """)
        self.dmx_toggle_btn.clicked.connect(self._toggle_dmx_output)
        toolbar.addWidget(self.dmx_toggle_btn)

        root.addLayout(toolbar)

        # ── Canvas ─────────────────────────────────────────────────
        self.canvas = FixtureCanvas(self)
        self.canvas.compact = True
        root.addWidget(self.canvas)

        # Timer de refresh (60 ms ~ 16 fps)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60)

    # ── API externe (identique a l'ancienne version) ────────────────

    @property
    def lamps(self):
        """Liste de (group, local_idx, None) pour compatibilite"""
        result = []
        group_counters = {}
        for proj in self.projectors:
            g = proj.group
            li = group_counters.get(g, 0)
            group_counters[g] = li + 1
            result.append((g, li, None))
        return result

    def refresh(self):
        self.canvas.update()

    def set_htp_overrides(self, overrides):
        self._htp_overrides = overrides

    def set_dmx_blocked(self):
        self.dmx_toggle_btn.setChecked(False)
        self.dmx_toggle_btn.setText("OFF")

    def is_dmx_enabled(self):
        return self.dmx_toggle_btn.isChecked()

    # ── DMX toggle ──────────────────────────────────────────────────

    def _toggle_dmx_output(self):
        if self.main_window and hasattr(self.main_window, '_license'):
            if not self.main_window._license.dmx_allowed:
                self.dmx_toggle_btn.setChecked(False)
                self.dmx_toggle_btn.setText("OFF")
                from PySide6.QtWidgets import QMessageBox as _QMB
                state = self.main_window._license.state
                from license_manager import LicenseState
                if state == LicenseState.TRIAL_EXPIRED:
                    msg = "Votre periode d'essai est terminee.\nActivez une licence pour utiliser la sortie Art-Net."
                elif state == LicenseState.LICENSE_EXPIRED:
                    msg = "Votre licence a expire.\nRenouvelez votre licence pour utiliser la sortie Art-Net."
                else:
                    msg = "Logiciel non active.\nActivez une licence pour utiliser la sortie Art-Net."
                _QMB.warning(self.main_window, "Sortie Art-Net", msg)
                return
        self.dmx_toggle_btn.setText("ON" if self.dmx_toggle_btn.isChecked() else "OFF")

    # ── Selection helpers ────────────────────────────────────────────

    def _deselect_all(self):
        self.selected_lamps.clear()
        self.refresh()

    def _select_all(self):
        self.selected_lamps.clear()
        for group, local_idx, _ in self.lamps:
            self.selected_lamps.add((group, local_idx))
        self.refresh()

    def _clear_all_projectors(self):
        for proj in self.projectors:
            proj.level = 0
            proj.base_color = QColor(0, 0, 0)
            proj.color = QColor(0, 0, 0)
        self.selected_lamps.clear()
        self.refresh()

    def _select_group(self, selection):
        self.selected_lamps.clear()
        if selection == "pairs_lat_contre":
            for group, idx, _ in self.lamps:
                if group == "contre" and idx in (1, 4):
                    self.selected_lamps.add((group, idx))
                elif group == "lat":
                    self.selected_lamps.add((group, idx))
        elif selection == "impairs_lat_contre":
            for group, idx, _ in self.lamps:
                if group == "contre" and idx in (0, 2, 3, 5):
                    self.selected_lamps.add((group, idx))
        elif selection == "all_lat_contre":
            for group, idx, _ in self.lamps:
                if group in ("contre", "lat"):
                    self.selected_lamps.add((group, idx))
        elif selection in ("face", "douche1", "douche2", "douche3", "lyre", "barre", "strobe", "fumee", "public"):
            for group, idx, _ in self.lamps:
                if group == selection:
                    self.selected_lamps.add((group, idx))
        self.refresh()

    # ── Couleur / dimmer ─────────────────────────────────────────────

    def _get_target_projectors(self, group, idx):
        targets = []
        for g, i in self.selected_lamps:
            projs = [p for p in self.projectors if p.group == g]
            if i < len(projs):
                targets.append((projs[i], g, i))
        if not targets:
            projs = [p for p in self.projectors if p.group == group]
            if idx < len(projs):
                targets.append((projs[idx], group, idx))
        return targets

    def _apply_color_to_targets(self, targets, color, close_menu=None):
        for proj, g, i in targets:
            proj.base_color = color
            if proj.level == 0:
                proj.level = 100
            brightness = proj.level / 100.0
            proj.color = QColor(
                int(color.red() * brightness),
                int(color.green() * brightness),
                int(color.blue() * brightness)
            )
        if self.main_window and hasattr(self.main_window, 'dmx') and self.main_window.dmx:
            self.main_window.dmx.update_from_projectors(self.projectors)
        self.refresh()
        if close_menu:
            close_menu.close()

    def _set_dimmer_for_targets(self, targets, level):
        for proj, g, i in targets:
            self.set_projector_dimmer(proj, level)

    def set_projector_dimmer(self, proj, level):
        proj.level = level
        if level > 0:
            brightness = level / 100.0
            proj.color = QColor(
                int(proj.base_color.red() * brightness),
                int(proj.base_color.green() * brightness),
                int(proj.base_color.blue() * brightness)
            )
        else:
            proj.color = QColor(0, 0, 0)
        if self.main_window and hasattr(self.main_window, 'dmx') and self.main_window.dmx:
            self.main_window.dmx.update_from_projectors(self.projectors)
        self.refresh()

    def change_projector_color_only(self, group, idx, color):
        projs = [p for p in self.projectors if p.group == group]
        if idx < len(projs):
            p = projs[idx]
            p.base_color = color
            if p.level > 0:
                brightness = p.level / 100.0
                p.color = QColor(
                    int(color.red() * brightness),
                    int(color.green() * brightness),
                    int(color.blue() * brightness)
                )
            else:
                p.color = QColor(0, 0, 0)

    def change_projector_color(self, group, idx, color, pad_row):
        self.change_projector_color_only(group, idx, color)

    # ── Menus contextuels ────────────────────────────────────────────

    def _show_fixture_context_menu(self, global_pos, fixture_idx):
        proj = self.projectors[fixture_idx]
        group, local_idx = self.canvas._local_idx(fixture_idx)
        targets = self._get_target_projectors(group, local_idx)
        if not targets:
            return

        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)

        # Titre
        if len(targets) == 1:
            p, g, i = targets[0]
            info_text = f"{p.name or (g.capitalize() + ' ' + str(i+1))}  (CH {p.start_address})"
        else:
            info_text = f"{len(targets)} fixtures selectionnees"

        info_lbl = QLabel(info_text)
        info_lbl.setStyleSheet("color: #00d4ff; font-weight: bold; font-size: 12px; padding: 4px 8px;")
        info_lbl.setAlignment(Qt.AlignCenter)
        info_wa = QWidgetAction(menu)
        info_wa.setDefaultWidget(info_lbl)
        menu.addAction(info_wa)
        menu.addSeparator()

        # Grille de couleurs 2 lignes x 4 cols
        colors_w = QWidget()
        colors_g = QGridLayout(colors_w)
        colors_g.setContentsMargins(8, 4, 8, 4)
        colors_g.setSpacing(5)
        for ci, (label, color) in enumerate(PRESET_COLORS):
            row, col = divmod(ci, 4)
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            border_c = "#555" if color.lightness() < 50 else color.darker(130).name()
            btn.setStyleSheet(f"""
                QPushButton {{ background: {color.name()}; border: 2px solid {border_c};
                               border-radius: 14px; }}
                QPushButton:hover {{ border: 2px solid #00d4ff; }}
            """)
            btn.setToolTip(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda checked, c=color, t=targets, m=menu: self._apply_color_to_targets(t, c, m)
            )
            colors_g.addWidget(btn, row, col)
        colors_wa = QWidgetAction(menu)
        colors_wa.setDefaultWidget(colors_w)
        menu.addAction(colors_wa)

        # Color picker inline
        picker_w = ColorPickerWidget(230, 100)
        picker_w.colorSelected.connect(
            lambda c, t=targets: self._apply_color_to_targets(t, c)
        )
        picker_wa = QWidgetAction(menu)
        picker_wa.setDefaultWidget(picker_w)
        menu.addAction(picker_wa)
        menu.addSeparator()

        # Dimmer
        dim_w = QWidget()
        dim_h = QHBoxLayout(dim_w)
        dim_h.setContentsMargins(8, 4, 8, 4)
        dim_h.setSpacing(8)
        dim_lbl = QLabel("Dim")
        dim_lbl.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        dim_h.addWidget(dim_lbl)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(targets[0][0].level)
        slider.setFixedWidth(150)
        slider.setStyleSheet("""
            QSlider::groove:horizontal { background: #333; height: 8px; border-radius: 4px; }
            QSlider::handle:horizontal { background: #00d4ff; width: 16px; height: 16px;
                                          margin: -4px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #005577,stop:1 #00d4ff);
                border-radius: 4px;
            }
        """)
        dim_val = QLabel(f"{targets[0][0].level}%")
        dim_val.setStyleSheet("color: #ddd; font-size: 12px; font-weight: bold; min-width: 35px;")
        dim_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider.valueChanged.connect(lambda v, t=targets: self._set_dimmer_for_targets(t, v))
        slider.valueChanged.connect(lambda v: dim_val.setText(f"{v}%"))
        dim_h.addWidget(slider)
        dim_h.addWidget(dim_val)
        dim_wa = QWidgetAction(menu)
        dim_wa.setDefaultWidget(dim_w)
        menu.addAction(dim_wa)
        menu.exec(global_pos)

    def _show_canvas_context_menu(self, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)

        act_add = menu.addAction("+ Ajouter fixture")
        act_add.triggered.connect(self._open_add_fixture_dialog)
        menu.addSeparator()

        act_sel_all = menu.addAction("Tout selectionner")
        act_sel_all.triggered.connect(self._select_all)

        act_desel = menu.addAction("Tout deselectionner")
        act_desel.triggered.connect(self._deselect_all)
        menu.addSeparator()

        act_clear = menu.addAction("Clear (tout a 0)")
        act_clear.triggered.connect(self._clear_all_projectors)
        menu.addSeparator()

        # Selectionner par groupe (noms depuis GROUP_DISPLAY si disponible)
        gd = {}
        if self.main_window and hasattr(self.main_window, 'GROUP_DISPLAY'):
            gd = self.main_window.GROUP_DISPLAY
        groups_present = []
        for p in self.projectors:
            if p.group not in groups_present:
                groups_present.append(p.group)
        if groups_present:
            sel_menu = menu.addMenu("Sélectionner...")
            for g in groups_present:
                label = gd.get(g, g)
                act = sel_menu.addAction(label)
                act.triggered.connect(lambda checked, grp=g: self._select_group(grp))

        menu.exec(global_pos)

    # ── Ajout / edition / suppression ────────────────────────────────

    def _open_new_plan_wizard(self):
        """Ouvre le wizard de creation d'un nouveau plan de feu"""
        dlg = NewPlanWizard(self)
        if dlg.exec() != QDialog.Accepted:
            return
        fixtures = dlg.get_result()
        if not fixtures:
            QMessageBox.warning(self, "Plan vide", "Aucune fixture configurée. Plan non appliqué.")
            return

        # Reconstruction des projectors in-place (preserve la reference main_window.projectors)
        from projector import Projector
        self.projectors.clear()
        self.selected_lamps.clear()
        for fd in fixtures:
            p = Projector(fd['group'], name=fd['name'], fixture_type=fd['fixture_type'])
            p.start_address = fd['start_address']
            p.canvas_x = None  # Position par defaut (calculee par le canvas)
            p.canvas_y = None
            if fd['fixture_type'] == "Machine a fumee":
                p.fan_speed = 0
            self.projectors.append(p)

        if self.main_window and hasattr(self.main_window, '_rebuild_dmx_patch'):
            self.main_window._rebuild_dmx_patch()
        self.refresh()

    def _open_add_fixture_dialog(self):
        from projector import Projector
        dlg = AddFixtureDialog(self.projectors, self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_fixture_data()
            if data:
                p = Projector(data['group'], name=data['name'], fixture_type=data['fixture_type'])
                p.start_address = data['start_address']
                p.canvas_x = 0.5
                p.canvas_y = 0.5
                self.projectors.append(p)
                if self.main_window and hasattr(self.main_window, '_rebuild_dmx_patch'):
                    self.main_window._rebuild_dmx_patch()
                self.refresh()

    def _edit_fixture(self, fixture_idx):
        if fixture_idx >= len(self.projectors):
            return
        proj = self.projectors[fixture_idx]
        dlg = EditFixtureDialog(proj, self.projectors, self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_fixture_data()
            if data:
                proj.name = data['name']
                proj.fixture_type = data['fixture_type']
                proj.group = data['group']
                proj.start_address = data['start_address']
                if self.main_window and hasattr(self.main_window, '_rebuild_dmx_patch'):
                    self.main_window._rebuild_dmx_patch()
                self.refresh()

    def _delete_fixture(self, fixture_idx):
        if fixture_idx >= len(self.projectors):
            return
        proj = self.projectors[fixture_idx]
        name = proj.name or f"{proj.group}"
        reply = QMessageBox.question(
            self, "Supprimer fixture",
            f"Supprimer '{name}' ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.projectors.pop(fixture_idx)
            self.selected_lamps.clear()
            if self.main_window and hasattr(self.main_window, '_rebuild_dmx_patch'):
                self.main_window._rebuild_dmx_patch()
            self.refresh()

    def _delete_selected_fixtures(self):
        selected = list(self.selected_lamps)
        if not selected:
            return
        if len(selected) > 1:
            reply = QMessageBox.question(
                self, "Supprimer fixtures",
                f"Supprimer {len(selected)} fixture(s) selectionnee(s) ?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Construire les indices a supprimer
        to_remove = set()
        group_counters = {}
        for i, proj in enumerate(self.projectors):
            g = proj.group
            li = group_counters.get(g, 0)
            group_counters[g] = li + 1
            if (g, li) in self.selected_lamps:
                to_remove.add(i)

        for i in sorted(to_remove, reverse=True):
            self.projectors.pop(i)

        self.selected_lamps.clear()
        if self.main_window and hasattr(self.main_window, '_rebuild_dmx_patch'):
            self.main_window._rebuild_dmx_patch()
        self.refresh()

    # ── Raccourcis clavier (re-expose depuis le QFrame) ──────────────

    def keyPressEvent(self, event):
        import time as _time
        now = _time.time()
        if event.key() == Qt.Key_Escape:
            if not hasattr(self, '_esc_times'):
                self._esc_times = []
            self._esc_times.append(now)
            self._esc_times = [t for t in self._esc_times if now - t < 1.5]
            if len(self._esc_times) >= 3:
                self._esc_times.clear()
                self._clear_all_projectors()
            else:
                self._deselect_all()
        elif event.key() == Qt.Key_A and (event.modifiers() & Qt.ControlModifier):
            self._select_all()
        elif event.key() == Qt.Key_Delete:
            self._delete_selected_fixtures()
        elif event.key() == Qt.Key_1:
            self._select_group("pairs_lat_contre")
        elif event.key() == Qt.Key_2:
            self._select_group("impairs_lat_contre")
        elif event.key() == Qt.Key_3:
            self._select_group("all_lat_contre")
        elif event.key() == Qt.Key_F:
            self._select_group("face")
        elif event.key() == Qt.Key_4:
            self._select_group("douche1")
        elif event.key() == Qt.Key_5:
            self._select_group("douche2")
        elif event.key() == Qt.Key_6:
            self._select_group("douche3")
        else:
            super().keyPressEvent(event)


# ── Dialogs Ajouter / Modifier ────────────────────────────────────────────────

class _FixtureFormWidget(QWidget):
    """Formulaire commun pour ajouter/modifier une fixture"""

    def __init__(self, projectors, preset=None, parent=None):
        super().__init__(parent)
        self._projectors = projectors

        layout = QFormLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.name_edit = QLineEdit(preset.get('name', '') if preset else '')
        self.name_edit.setPlaceholderText("Ex: Face gauche, Lyre SL...")
        layout.addRow("Nom :", self.name_edit)

        self.type_combo = QComboBox()
        for t in ["PAR LED", "Moving Head", "Barre LED", "Stroboscope", "Machine a fumee"]:
            self.type_combo.addItem(t)
        if preset:
            idx = self.type_combo.findText(preset.get('fixture_type', 'PAR LED'))
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
        layout.addRow("Type :", self.type_combo)

        self.addr_spin = QSpinBox()
        self.addr_spin.setRange(1, 512)
        self.addr_spin.setValue(preset.get('start_address', self._next_address()) if preset else self._next_address())
        layout.addRow("Adresse DMX :", self.addr_spin)

        self.group_combo = QComboBox()
        groups = ["face", "contre", "douche1", "douche2", "douche3", "lat",
                  "lyre", "barre", "strobe", "fumee", "public"]
        for g in groups:
            self.group_combo.addItem(g)
        if preset:
            idx = self.group_combo.findText(preset.get('group', 'face'))
            if idx >= 0:
                self.group_combo.setCurrentIndex(idx)
        layout.addRow("Groupe :", self.group_combo)

        self.profile_combo = QComboBox()
        self._populate_profiles(self.type_combo.currentText())
        if preset and 'profile' in preset:
            idx = self.profile_combo.findData(preset['profile'])
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        layout.addRow("Profil DMX :", self.profile_combo)

        self.type_combo.currentTextChanged.connect(self._on_type_changed)

    def _next_address(self):
        if not self._projectors:
            return 1
        _CH = {"PAR LED": 5, "Moving Head": 8, "Barre LED": 5, "Stroboscope": 2, "Machine a fumee": 2}
        return max(p.start_address + _CH.get(getattr(p, 'fixture_type', 'PAR LED'), 5)
                   for p in self._projectors)

    def _populate_profiles(self, fixture_type):
        from artnet_dmx import DMX_PROFILES, profile_display_text
        self.profile_combo.clear()
        TYPE_PROFILES = {
            "PAR LED":        ["RGB", "RGBD", "RGBDS", "RGBSD", "DRGB", "DRGBS",
                               "RGBW", "RGBWD", "RGBWDS", "RGBWZ", "RGBWA", "RGBWAD", "RGBWOUV"],
            "Moving Head":    ["MOVING_5CH", "MOVING_8CH", "MOVING_RGB", "MOVING_RGBW"],
            "Barre LED":      ["LED_BAR_RGB", "RGB", "RGBD", "RGBDS"],
            "Stroboscope":    ["STROBE_2CH"],
            "Machine a fumee": ["2CH_FUMEE"],
        }
        allowed = TYPE_PROFILES.get(fixture_type, list(DMX_PROFILES.keys()))
        for key in allowed:
            if key in DMX_PROFILES:
                label = f"{key}  ({profile_display_text(DMX_PROFILES[key])})"
                self.profile_combo.addItem(label, key)

    def _on_type_changed(self, ftype):
        current_data = self.profile_combo.currentData()
        self._populate_profiles(ftype)
        # Restaurer la valeur si disponible
        idx = self.profile_combo.findData(current_data)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

    def get_data(self):
        from artnet_dmx import DMX_PROFILES
        return {
            'name': self.name_edit.text().strip(),
            'fixture_type': self.type_combo.currentText(),
            'start_address': self.addr_spin.value(),
            'group': self.group_combo.currentText(),
            'profile': self.profile_combo.currentData() or 'RGBDS',
        }


class AddFixtureDialog(QDialog):
    """Dialog pour ajouter une fixture (2 onglets: bibliotheque + formulaire)"""

    def __init__(self, projectors, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajouter une fixture")
        self.setMinimumSize(500, 380)
        self._projectors = projectors
        self._result_data = None

        self.setStyleSheet("""
            QDialog { background: #1a1a1a; color: white; }
            QTabWidget::pane { border: 1px solid #333; }
            QTabBar::tab { background: #2a2a2a; color: #aaa; padding: 6px 14px; }
            QTabBar::tab:selected { background: #333; color: white; }
            QListWidget { background: #222; border: 1px solid #333; color: white; }
            QListWidget::item:selected { background: #00d4ff; color: black; }
            QLineEdit, QComboBox, QSpinBox {
                background: #2a2a2a; color: white; border: 1px solid #444;
                border-radius: 3px; padding: 3px;
            }
            QLabel { color: #ccc; }
        """)

        root = QVBoxLayout(self)
        tabs = QTabWidget()

        # ── Onglet Bibliotheque ─────────────────────────────────────
        lib_w = QWidget()
        lib_layout = QVBoxLayout(lib_w)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)

        self.cat_list = QListWidget()
        self.cat_list.setMaximumWidth(150)
        for cat in FIXTURE_LIBRARY:
            self.cat_list.addItem(cat)
        splitter.addWidget(self.cat_list)

        self.preset_list = QListWidget()
        splitter.addWidget(self.preset_list)
        splitter.setSizes([140, 320])

        lib_layout.addWidget(splitter)

        self.cat_list.currentTextChanged.connect(self._on_category_changed)
        self.preset_list.itemDoubleClicked.connect(self._accept_library)
        self.cat_list.setCurrentRow(0)

        tabs.addTab(lib_w, "Bibliotheque")

        # ── Onglet Formulaire rapide ────────────────────────────────
        self._form = _FixtureFormWidget(projectors, parent=self)
        tabs.addTab(self._form, "Formulaire rapide")

        root.addWidget(tabs)
        self._tabs = tabs

        # Boutons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_category_changed(self, cat):
        self.preset_list.clear()
        for preset in FIXTURE_LIBRARY.get(cat, []):
            item = QListWidgetItem(preset['name'])
            item.setData(Qt.UserRole, preset)
            self.preset_list.addItem(item)

    def _accept_library(self, item):
        self._result_data = item.data(Qt.UserRole)
        self.accept()

    def _on_accept(self):
        if self._tabs.currentIndex() == 0:
            # Bibliotheque
            item = self.preset_list.currentItem()
            if item:
                self._result_data = item.data(Qt.UserRole)
                # Calculer adresse DMX compacte
                _CH = {"PAR LED": 5, "Moving Head": 8, "Barre LED": 5, "Stroboscope": 2, "Machine a fumee": 2}
                if self._projectors:
                    next_addr = max(
                        p.start_address + _CH.get(getattr(p, 'fixture_type', 'PAR LED'), 5)
                        for p in self._projectors
                    )
                else:
                    next_addr = 1
                self._result_data = dict(self._result_data)
                self._result_data['start_address'] = next_addr
                self.accept()
            else:
                QMessageBox.warning(self, "Aucun preset", "Selectionnez un preset dans la bibliotheque.")
        else:
            self._result_data = self._form.get_data()
            self.accept()

    def get_fixture_data(self):
        return self._result_data


class EditFixtureDialog(QDialog):
    """Dialog pour modifier une fixture existante"""

    def __init__(self, proj, projectors, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modifier la fixture")
        self.setMinimumSize(420, 300)
        self._result_data = None

        self.setStyleSheet("""
            QDialog { background: #1a1a1a; color: white; }
            QLineEdit, QComboBox, QSpinBox {
                background: #2a2a2a; color: white; border: 1px solid #444;
                border-radius: 3px; padding: 3px;
            }
            QLabel { color: #ccc; }
        """)

        preset = {
            'name': proj.name,
            'fixture_type': getattr(proj, 'fixture_type', 'PAR LED'),
            'start_address': proj.start_address,
            'group': proj.group,
        }
        root = QVBoxLayout(self)
        self._form = _FixtureFormWidget(projectors, preset=preset, parent=self)
        root.addWidget(self._form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_accept(self):
        self._result_data = self._form.get_data()
        self.accept()

    def get_fixture_data(self):
        return self._result_data


# ── Wizard "Nouveau plan de feu" ──────────────────────────────────────────────

class _CounterWidget(QWidget):
    """Grand compteur +/- utilisé dans le wizard"""
    valueChanged = Signal(int)

    def __init__(self, value=0, min_val=0, max_val=20, parent=None):
        super().__init__(parent)
        self._value = value
        self._min = min_val
        self._max = max_val

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(20)

        self.btn_minus = QPushButton("−")
        self.btn_minus.setFixedSize(60, 60)
        self.btn_minus.setStyleSheet("""
            QPushButton {
                background: #2a2a2a; color: white; border: 2px solid #444;
                border-radius: 30px; font-size: 30px; font-weight: bold;
            }
            QPushButton:hover  { background: #3a3a3a; border-color: #888; }
            QPushButton:pressed{ background: #444; }
            QPushButton:disabled{ color: #333; border-color: #2a2a2a; }
        """)
        row.addWidget(self.btn_minus)

        self.lbl = QLabel(str(value))
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setFixedWidth(90)
        self.lbl.setStyleSheet("color: white; font-size: 54px; font-weight: bold;")
        row.addWidget(self.lbl)

        self.btn_plus = QPushButton("+")
        self.btn_plus.setFixedSize(60, 60)
        self.btn_plus.setStyleSheet("""
            QPushButton {
                background: #00d4ff; color: black; border: none;
                border-radius: 30px; font-size: 30px; font-weight: bold;
            }
            QPushButton:hover  { background: #33ddff; }
            QPushButton:pressed{ background: #00aacc; }
            QPushButton:disabled{ background: #1a4455; color: #1a1a1a; }
        """)
        row.addWidget(self.btn_plus)

        self.btn_minus.clicked.connect(self._dec)
        self.btn_plus.clicked.connect(self._inc)
        self._refresh_buttons()

    def _dec(self):
        if self._value > self._min:
            self._value -= 1
            self.lbl.setText(str(self._value))
            self.valueChanged.emit(self._value)
            self._refresh_buttons()

    def _inc(self):
        if self._value < self._max:
            self._value += 1
            self.lbl.setText(str(self._value))
            self.valueChanged.emit(self._value)
            self._refresh_buttons()

    def _refresh_buttons(self):
        self.btn_minus.setEnabled(self._value > self._min)
        self.btn_plus.setEnabled(self._value < self._max)

    def value(self):
        return self._value

    def set_value(self, v):
        self._value = max(self._min, min(self._max, v))
        self.lbl.setText(str(self._value))
        self._refresh_buttons()


class _FixturePreviewBar(QWidget):
    """Rangée de petits cercles représentant les fixtures"""

    def __init__(self, count=0, color="#00d4ff", parent=None):
        super().__init__(parent)
        self._count = count
        self._color = QColor(color)
        self.setFixedHeight(36)
        self.setMinimumWidth(200)

    def set_count(self, n):
        self._count = n
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d0d0d"))

        n = self._count
        if n == 0:
            painter.setPen(QColor("#444"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(self.rect(), Qt.AlignCenter, "Aucune fixture")
            painter.end()
            return

        r = 12
        gap = 6
        total_w = n * r * 2 + (n - 1) * gap
        # Si trop large, réduire r
        if total_w > self.width() - 20:
            r = max(4, (self.width() - 20 - (n - 1) * gap) // (2 * n))
            total_w = n * r * 2 + (n - 1) * gap
        cx0 = (self.width() - total_w) // 2 + r
        cy = self.height() // 2

        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(self._color.lighter(140), 1))
        for i in range(n):
            cx = cx0 + i * (r * 2 + gap)
            painter.drawEllipse(QPoint(cx, cy), r, r)
        painter.end()


class NewPlanWizard(QDialog):
    """Assistant étape par étape pour créer un nouveau plan de feu"""

    _STEPS = [
        dict(
            group="face",   label="Groupe A — Face",
            subtitle="Combien de projecteurs face au public ?\n(éclairage frontal de scène)",
            ftype="PAR LED", profile="RGBDS", prefix="Face",
            color="#ffaa33", default=4, max=20,
        ),
        dict(
            group="contre", label="Groupe B — Contre-jour",
            subtitle="Combien de contre-jour ?\n(lumières arrière, hautes, sur les perches)",
            ftype="PAR LED", profile="RGBDS", prefix="Contre",
            color="#4488ff", default=6, max=20,
        ),
        dict(
            group="lat",    label="Groupe C — Latéraux",
            subtitle="Combien de projecteurs latéraux ?\n(éclairage de côté, jardin et cour)",
            ftype="PAR LED", profile="RGBDS", prefix="Lat",
            color="#88aaff", default=2, max=10,
        ),
        dict(
            group="douche1", label="Groupe D — Douches",
            subtitle="Combien de projecteurs en douche ?\n(éclairage vertical depuis le plafond)",
            ftype="PAR LED", profile="RGBDS", prefix="Douche",
            color="#44ee88", default=3, max=20,
        ),
        dict(
            group="lyre",   label="Groupe E — Lyres",
            subtitle="Combien de lyres / moving heads ?\n(laisser à 0 si aucun)",
            ftype="Moving Head", profile="MOVING_8CH", prefix="Lyre",
            color="#ee44ff", default=0, max=10,
        ),
        dict(
            group="fumee",  label="Machine à fumée",
            subtitle="Combien de machines à fumée / hazers ?\n(laisser à 0 si aucune)",
            ftype="Machine a fumee", profile="2CH_FUMEE", prefix="Fumée",
            color="#aaaaaa", default=0, max=4,
        ),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nouveau plan de feu")
        self.setModal(True)
        self.setMinimumSize(560, 500)
        self.setStyleSheet("""
            QDialog { background: #141414; color: white; }
        """)

        self._counts = [s['default'] for s in self._STEPS]
        self._step = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── En-tête ────────────────────────────────────────────────
        self._header = QWidget()
        self._header.setFixedHeight(72)
        self._header.setStyleSheet("background: #0d0d0d; border-bottom: 1px solid #2a2a2a;")
        hh = QHBoxLayout(self._header)
        hh.setContentsMargins(28, 0, 28, 0)

        self._title_lbl = QLabel()
        self._title_lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        self._title_lbl.setStyleSheet("color: white;")
        hh.addWidget(self._title_lbl)
        hh.addStretch()

        self._dots_lbl = QLabel()
        self._dots_lbl.setStyleSheet("color: #555; font-size: 18px; letter-spacing: 6px;")
        hh.addWidget(self._dots_lbl)

        root.addWidget(self._header)

        # ── Pages ─────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._step_pages = []
        for i, step in enumerate(self._STEPS):
            page = self._build_step_page(i, step)
            self._stack.addWidget(page)
            self._step_pages.append(page)

        self._summary_page = self._build_summary_page()
        self._stack.addWidget(self._summary_page)

        root.addWidget(self._stack)

        # ── Pied de page ───────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(68)
        footer.setStyleSheet("background: #0d0d0d; border-top: 1px solid #2a2a2a;")
        fh = QHBoxLayout(footer)
        fh.setContentsMargins(28, 0, 28, 0)
        fh.setSpacing(10)

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet(
            "background:#222; color:#888; border:1px solid #444; border-radius:4px; padding:0 16px;"
        )
        cancel_btn.clicked.connect(self.reject)
        fh.addWidget(cancel_btn)
        fh.addStretch()

        self._back_btn = QPushButton("← Retour")
        self._back_btn.setFixedHeight(38)
        self._back_btn.setStyleSheet(
            "background:#2a2a2a; color:white; border:1px solid #444; border-radius:4px; padding:0 16px;"
        )
        self._back_btn.clicked.connect(self._go_prev)
        fh.addWidget(self._back_btn)

        self._next_btn = QPushButton("Suivant →")
        self._next_btn.setFixedHeight(38)
        self._next_btn.setStyleSheet(
            "background:#00d4ff; color:black; font-weight:bold; border:none; border-radius:4px; padding:0 20px;"
        )
        self._next_btn.clicked.connect(self._go_next)
        fh.addWidget(self._next_btn)

        root.addWidget(footer)
        self._refresh_ui()

    # ── Construction des pages ─────────────────────────────────────

    def _build_step_page(self, idx, step):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(50, 36, 50, 24)
        vl.setSpacing(0)

        subtitle = QLabel(step['subtitle'])
        subtitle.setStyleSheet("color: #888; font-size: 13px;")
        subtitle.setAlignment(Qt.AlignCenter)
        vl.addWidget(subtitle)
        vl.addSpacing(36)

        counter = _CounterWidget(value=self._counts[idx], max_val=step['max'])
        counter.valueChanged.connect(lambda v, i=idx: self._on_count(i, v))
        vl.addWidget(counter, 0, Qt.AlignCenter)
        vl.addSpacing(28)

        preview = _FixturePreviewBar(count=self._counts[idx], color=step['color'])
        vl.addWidget(preview)
        vl.addSpacing(10)

        info_lbl = QLabel()
        info_lbl.setStyleSheet("color: #555; font-size: 11px;")
        info_lbl.setAlignment(Qt.AlignCenter)
        vl.addWidget(info_lbl)
        vl.addStretch()

        page._counter = counter
        page._preview = preview
        page._info = info_lbl
        page._idx = idx
        self._refresh_step_page(page)
        return page

    def _refresh_step_page(self, page):
        from artnet_dmx import DMX_PROFILES
        idx = page._idx
        step = self._STEPS[idx]
        count = self._counts[idx]
        ch_per = len(DMX_PROFILES.get(step['profile'], ['?'] * 5))
        page._preview.set_count(count)
        if count == 0:
            page._info.setText("Ce groupe sera vide")
        else:
            s = 's' if count > 1 else ''
            page._info.setText(
                f"{count} fixture{s} · {ch_per} canaux chacune · {count * ch_per} canaux au total"
            )

    def _build_summary_page(self):
        page = QWidget()
        vl = QVBoxLayout(page)
        vl.setContentsMargins(50, 28, 50, 24)
        vl.setSpacing(0)

        sub = QLabel("Voici votre plan de feu. Cliquez sur Configurer pour l'appliquer.")
        sub.setStyleSheet("color: #888; font-size: 12px;")
        sub.setAlignment(Qt.AlignCenter)
        vl.addWidget(sub)
        vl.addSpacing(20)

        self._summary_inner = QWidget()
        vl.addWidget(self._summary_inner)
        vl.addStretch()
        return page

    def _refresh_summary(self):
        from artnet_dmx import DMX_PROFILES

        # Nettoyer l'ancien layout
        old = self._summary_inner.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            import sip
            try:
                sip.delete(old)
            except Exception:
                pass

        grid = QGridLayout(self._summary_inner)
        grid.setSpacing(10)
        grid.setColumnStretch(2, 1)

        addr = 1
        total_fx = 0
        total_ch = 0
        row = 0

        for i, step in enumerate(self._STEPS):
            count = self._counts[i]
            profile = DMX_PROFILES.get(step['profile'], ['?'] * 5)
            ch = len(profile) * count

            # Ligne de séparateur légère entre groupes
            if row > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setStyleSheet("background: #222; margin: 0;")
                sep.setFixedHeight(1)
                grid.addWidget(sep, row, 0, 1, 4)
                row += 1

            # Indicateur couleur
            dot = QLabel("●")
            alpha = "ff" if count > 0 else "33"
            dot.setStyleSheet(f"color: {step['color']}; font-size: 18px;")
            dot.setAlignment(Qt.AlignCenter)
            dot.setFixedWidth(28)
            grid.addWidget(dot, row, 0)

            # Nom du groupe
            name = QLabel(step['label'])
            name.setStyleSheet(
                f"color: {'white' if count > 0 else '#444'}; font-size: 13px; font-weight: bold;"
            )
            grid.addWidget(name, row, 1)

            # Compte
            count_lbl = QLabel(f"{count} fixture{'s' if count != 1 else ''}" if count > 0 else "—")
            count_lbl.setStyleSheet("color: #888; font-size: 12px;")
            count_lbl.setAlignment(Qt.AlignCenter)
            grid.addWidget(count_lbl, row, 2)

            # Plage d'adresses
            if count > 0:
                addr_text = f"CH {addr} – {addr + ch - 1}"
                addr_lbl = QLabel(addr_text)
                addr_lbl.setStyleSheet("color: #00d4ff; font-size: 12px;")
                addr_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                grid.addWidget(addr_lbl, row, 3)
                addr += ch
                total_fx += count
                total_ch += ch

            row += 1

        # Total
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background: #333;")
        sep2.setFixedHeight(1)
        grid.addWidget(sep2, row, 0, 1, 4)
        row += 1

        if total_fx == 0:
            warn = QLabel("⚠  Aucune fixture configurée. Ajoutez au moins un projecteur.")
            warn.setStyleSheet("color: #ff8800; font-size: 12px;")
            warn.setAlignment(Qt.AlignCenter)
            grid.addWidget(warn, row, 0, 1, 4)
        else:
            total_lbl = QLabel(
                f"Total : {total_fx} fixture{'s' if total_fx > 1 else ''}  ·  {total_ch} canaux DMX utilisés"
            )
            total_lbl.setStyleSheet("color: #666; font-size: 11px;")
            total_lbl.setAlignment(Qt.AlignCenter)
            grid.addWidget(total_lbl, row, 0, 1, 4)

    # ── Navigation ─────────────────────────────────────────────────

    def _on_count(self, idx, value):
        self._counts[idx] = value
        self._refresh_step_page(self._step_pages[idx])

    def _go_prev(self):
        if self._step > 0:
            self._step -= 1
            self._refresh_ui()

    def _go_next(self):
        n = len(self._STEPS)
        if self._step < n:
            self._step += 1
            if self._step == n:
                self._refresh_summary()
            self._refresh_ui()
        else:
            self.accept()

    def _refresh_ui(self):
        n = len(self._STEPS)
        is_summary = (self._step == n)

        # Dots progress
        dots = "".join("●" if i < self._step else "○" for i in range(n))
        self._dots_lbl.setText(dots)

        if is_summary:
            self._stack.setCurrentWidget(self._summary_page)
            self._title_lbl.setText("Résumé")
            self._next_btn.setText("✓  Configurer")
            self._next_btn.setStyleSheet(
                "background:#22cc55; color:white; font-weight:bold;"
                " border:none; border-radius:4px; padding:0 20px;"
            )
        else:
            self._stack.setCurrentIndex(self._step)
            self._title_lbl.setText(self._STEPS[self._step]['label'])
            self._next_btn.setText("Suivant →")
            self._next_btn.setStyleSheet(
                "background:#00d4ff; color:black; font-weight:bold;"
                " border:none; border-radius:4px; padding:0 20px;"
            )

        self._back_btn.setEnabled(self._step > 0)

    # ── Résultat ───────────────────────────────────────────────────

    def get_result(self):
        """Retourne la liste de dicts {name, group, fixture_type, start_address, profile}"""
        from artnet_dmx import DMX_PROFILES
        fixtures = []
        addr = 1
        for i, step in enumerate(self._STEPS):
            count = self._counts[i]
            profile = list(DMX_PROFILES.get(step['profile'], ['R', 'G', 'B', 'Dim', 'Strobe']))
            ch = len(profile)
            for j in range(count):
                name = f"{step['prefix']} {j + 1}" if count > 1 else step['prefix']
                fixtures.append({
                    'name': name,
                    'group': step['group'],
                    'fixture_type': step['ftype'],
                    'start_address': addr,
                    'profile': profile,
                })
                addr += ch
        return fixtures


# ── _PatchCanvasProxy ────────────────────────────────────────────────────────
# Interface minimale requise par FixtureCanvas pour le dialog Patch DMX

class _PatchCanvasProxy:
    """Proxy léger permettant d'utiliser FixtureCanvas dans le dialog Patch DMX.
    Implémente l'interface attendue par FixtureCanvas (projectors, selected_lamps,
    _htp_overrides, _show_fixture_context_menu, _show_canvas_context_menu).
    """

    def __init__(self, projectors, main_window):
        self.projectors = projectors
        self.main_window = main_window
        self.selected_lamps = set()
        self._htp_overrides = None
        # Callbacks injectés par le dialog
        self._add_cb               = None
        self._wizard_cb            = None
        self._align_row_cb         = None   # Aligner sur la même ligne (même Y)
        self._distribute_cb        = None   # Centrer + distribuer également
        self._select_fixture_cb    = None   # Basculer sur l'onglet Fixtures + sélectionner la carte

    # ── Menus contextuels ───────────────────────────────────────────

    def _show_fixture_context_menu(self, global_pos, idx):
        if idx >= len(self.projectors):
            return
        proj = self.projectors[idx]
        menu = QMenu()
        menu.setStyleSheet(_MENU_STYLE)

        info = menu.addAction(f"{proj.name or proj.group}  ·  CH {proj.start_address}")
        info.setEnabled(False)
        menu.addSeparator()
        act_edit = menu.addAction("Modifier...")

        action = menu.exec(global_pos)
        if action == act_edit:
            self._edit_fixture(idx)

    def _show_canvas_context_menu(self, global_pos):
        menu = QMenu()
        menu.setStyleSheet(_MENU_STYLE)

        if self._add_cb:
            menu.addAction("➕  Ajouter fixture", self._add_cb)
        menu.addSeparator()

        act_all  = menu.addAction("Tout sélectionner")
        act_none = menu.addAction("Tout désélectionner")

        # Actions d'alignement rapide (visible quand sélection active)
        if self.selected_lamps and (self._align_row_cb or self._distribute_cb):
            menu.addSeparator()
            if self._align_row_cb:
                menu.addAction("⟶  Aligner sur la même ligne", self._align_row_cb)
            if self._distribute_cb:
                menu.addAction("⟺  Distribuer également",      self._distribute_cb)

        action = menu.exec(global_pos)
        if action == act_all:
            g_cnt = {}
            for p in self.projectors:
                g = p.group
                li = g_cnt.get(g, 0)
                g_cnt[g] = li + 1
                self.selected_lamps.add((g, li))
        elif action == act_none:
            self.selected_lamps.clear()

    # ── Modifier / Supprimer ────────────────────────────────────────

    def _edit_fixture(self, idx):
        # Si le dialog Patch DMX est ouvert, basculer sur l'onglet Fixtures + sélectionner la carte
        if self._select_fixture_cb:
            self._select_fixture_cb(idx)
            return
        # Fallback : dialog autonome (si appelé hors du dialog Patch DMX)
        proj = self.projectors[idx]
        dlg = EditFixtureDialog(proj, self.projectors)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_fixture_data()
            if data:
                proj.name         = data['name']
                proj.fixture_type = data['fixture_type']
                proj.group        = data['group']
                proj.start_address = data['start_address']
                if self.main_window and hasattr(self.main_window, '_rebuild_dmx_patch'):
                    self.main_window._rebuild_dmx_patch()

    def _delete_fixture(self, idx):
        proj = self.projectors[idx]
        reply = QMessageBox.question(
            None, "Supprimer",
            f"Supprimer '{proj.name or proj.group}' ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.projectors.pop(idx)
            self.selected_lamps.clear()
            if self.main_window and hasattr(self.main_window, '_rebuild_dmx_patch'):
                self.main_window._rebuild_dmx_patch()

    def _delete_selected_fixtures(self):
        if not self.selected_lamps:
            return
        n = len(self.selected_lamps)
        reply = QMessageBox.question(
            None, "Supprimer",
            f"Supprimer {n} fixture{'s' if n > 1 else ''} selectionnee{'s' if n > 1 else ''} ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        to_remove = set()
        g_cnt = {}
        for i, proj in enumerate(self.projectors):
            li = g_cnt.get(proj.group, 0)
            if (proj.group, li) in self.selected_lamps:
                to_remove.add(i)
            g_cnt[proj.group] = li + 1
        for i in sorted(to_remove, reverse=True):
            self.projectors.pop(i)
        self.selected_lamps.clear()
        if self.main_window and hasattr(self.main_window, '_rebuild_dmx_patch'):
            self.main_window._rebuild_dmx_patch()


# ── PlanDeFeuPreview ──────────────────────────────────────────────────────────

class PlanDeFeuPreview(QWidget):
    """Previsualisation du plan de feu sous la timeline"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setFixedHeight(120)
        self.setStyleSheet("background: #0a0a0a; border-top: 2px solid #3a3a3a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Plan de Feu - Previsualisation")
        title.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(5)

        self.projector_widgets = {}

        face_label = QLabel("Face:")
        face_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(face_label, 0, 0)
        self.face_widget = QLabel("O")
        self.face_widget.setFixedSize(40, 40)
        self.face_widget.setAlignment(Qt.AlignCenter)
        self.face_widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
        grid.addWidget(self.face_widget, 0, 1)

        for i in range(3):
            douche_label = QLabel(f"Douche {i+1}:")
            douche_label.setStyleSheet("color: #888; font-size: 11px;")
            grid.addWidget(douche_label, 0, 2 + i*2)
            widget = QLabel("O")
            widget.setFixedSize(40, 40)
            widget.setAlignment(Qt.AlignCenter)
            widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
            grid.addWidget(widget, 0, 3 + i*2)
            self.projector_widgets[f'douche{i+1}'] = widget

        contres_label = QLabel("Contres:")
        contres_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(contres_label, 0, 8)
        self.contres_widget = QLabel("O")
        self.contres_widget.setFixedSize(40, 40)
        self.contres_widget.setAlignment(Qt.AlignCenter)
        self.contres_widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
        grid.addWidget(self.contres_widget, 0, 9)

        layout.addLayout(grid)

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_preview)
        self.update_timer.start(50)

    def update_preview(self):
        if not self.main_window or not hasattr(self.main_window, 'projectors'):
            return

        for proj in self.main_window.projectors:
            widget = None

            if proj.group == "face":
                widget = self.face_widget
            elif proj.group == "contre":
                pass
            elif proj.group == "douche":
                widget = self.projector_widgets.get(f'douche{proj.index + 1}')

            if widget and proj.level > 0:
                color = proj.color
                widget.setStyleSheet(f"""
                    background: {color.name()};
                    border-radius: 20px;
                    font-size: 20px;
                """)
            elif widget:
                widget.setStyleSheet("""
                    background: #1a1a1a;
                    border-radius: 20px;
                    font-size: 20px;
                """)
