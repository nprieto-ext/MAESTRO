"""
Editeur de fixture DMX — MyStrow
Dialog de création et gestion de templates de fixtures pour le patch DMX.
"""
import copy
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QLineEdit, QComboBox, QFrame,
    QMessageBox, QListWidget, QListWidgetItem, QMenuBar,
    QFileDialog, QSplitter, QAbstractItemView, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QAction, QKeySequence

class _NoScrollCombo(QComboBox):
    """QComboBox qui ignore le scroll souris (évite de changer de canal par accident)."""
    def wheelEvent(self, event):
        event.ignore()


FIXTURE_FILE = Path.home() / ".mystrow_fixtures.json"

FIXTURE_TYPES = ["PAR LED", "Moving Head", "Barre LED", "Stroboscope", "Machine a fumee"]
GROUP_OPTIONS = [
    "face", "douche1", "douche2", "douche3", "lat", "contre",
    "lyre", "barre", "strobe", "fumee",
]
ALL_CHANNEL_TYPES = [
    "R", "G", "B", "W", "Dim", "Strobe", "UV", "Ambre", "Orange", "Zoom",
    "Smoke", "Fan", "Pan", "PanFine", "Tilt", "TiltFine",
    "Gobo1", "Gobo2", "Prism", "Focus", "ColorWheel", "Shutter", "Speed", "Mode",
]
CHANNEL_COLORS = {
    "R": "#cc2200", "G": "#00aa00", "B": "#0055ff", "W": "#bbbbbb",
    "Dim": "#888800", "Strobe": "#ffaa00", "UV": "#8800cc",
    "Ambre": "#ee6600", "Orange": "#ff4400", "Zoom": "#00ccaa",
    "Smoke": "#555555", "Fan": "#336699", "Pan": "#ff55aa",
    "PanFine": "#cc4488", "Tilt": "#00ddff", "TiltFine": "#00aacc",
    "Gobo1": "#aa8800", "Gobo2": "#886600", "Prism": "#dd00dd",
    "Focus": "#00aa88", "ColorWheel": "#ff8800", "Shutter": "#ff2266",
    "Speed": "#66ff66", "Mode": "#88aaff",
}

BUILTIN_FIXTURES = [
    # PAR LED
    {"name": "PAR LED RGB 3ch",    "fixture_type": "PAR LED",      "group": "face",   "profile": ["R","G","B"],                            "builtin": True},
    {"name": "PAR LED RGBDS 5ch",  "fixture_type": "PAR LED",      "group": "face",   "profile": ["R","G","B","Dim","Strobe"],             "builtin": True},
    {"name": "PAR LED RGBWD 5ch",  "fixture_type": "PAR LED",      "group": "face",   "profile": ["R","G","B","W","Dim"],                  "builtin": True},
    {"name": "PAR LED RGBWDS 6ch", "fixture_type": "PAR LED",      "group": "face",   "profile": ["R","G","B","W","Dim","Strobe"],         "builtin": True},
    # Moving Head
    {"name": "Lyre Spot 5ch",      "fixture_type": "Moving Head",  "group": "lyre",   "profile": ["Shutter","Dim","ColorWheel","Gobo1","Speed"],            "builtin": True},
    {"name": "Lyre Spot 8ch",      "fixture_type": "Moving Head",  "group": "lyre",   "profile": ["Pan","Tilt","Shutter","Dim","ColorWheel","Gobo1","Speed","Mode"], "builtin": True},
    {"name": "Lyre Wash RGB 8ch",  "fixture_type": "Moving Head",  "group": "lyre",   "profile": ["Pan","Tilt","R","G","B","Dim","Shutter","Speed"],         "builtin": True},
    {"name": "Lyre Wash RGBW 9ch", "fixture_type": "Moving Head",  "group": "lyre",   "profile": ["Pan","Tilt","R","G","B","W","Dim","Shutter","Speed"],     "builtin": True},
    # Barre LED
    {"name": "Barre LED RGB 5ch",  "fixture_type": "Barre LED",    "group": "barre",  "profile": ["R","G","B","Dim","Strobe"],             "builtin": True},
    # Stroboscope
    {"name": "Strobe 2ch",         "fixture_type": "Stroboscope",  "group": "strobe", "profile": ["Shutter","Dim"],                        "builtin": True},
    # Machine a fumee
    {"name": "Machine a fumee 2ch","fixture_type": "Machine a fumee","group": "fumee","profile": ["Smoke","Fan"],                          "builtin": True},
]

# ──────────────────────────────────────────────────────────────────────────────
# DmxPreviewWidget — barre colorée représentant les canaux
# ──────────────────────────────────────────────────────────────────────────────

class DmxPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._channels = []
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_channels(self, channels):
        self._channels = list(channels)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor("#1a1a1a"))
        n = len(self._channels)
        if n == 0:
            painter.setPen(QColor("#555"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(0, 0, w, h, Qt.AlignCenter, "Aucun canal défini")
            return
        block_w = max(22, min(72, w // n))
        total_w = block_w * n
        x0 = max(0, (w - total_w) // 2)
        for i, ch in enumerate(self._channels):
            x = x0 + i * block_w
            color = QColor(CHANNEL_COLORS.get(ch, "#444444"))
            painter.fillRect(x + 1, 4, block_w - 2, h - 8, color.darker(200))
            painter.setPen(QPen(color, 1))
            painter.drawRect(x + 1, 4, block_w - 2, h - 8)
            painter.setPen(QColor("#999"))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(x, 4, block_w, 12, Qt.AlignCenter, str(i + 1))
            painter.setPen(color.lighter(170))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            display = ch if len(ch) <= 6 else ch[:5] + "."
            painter.drawText(x, 16, block_w, h - 20, Qt.AlignCenter, display)
        painter.end()


# ──────────────────────────────────────────────────────────────────────────────
# ChannelRowWidget — une ligne de canal: numéro + type + ↑↓×
# ──────────────────────────────────────────────────────────────────────────────

class ChannelRowWidget(QWidget):
    remove_requested  = Signal(object)
    move_up_requested = Signal(object)
    move_dn_requested = Signal(object)
    changed           = Signal()

    def __init__(self, ch_num, ch_type, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setStyleSheet("background:#1e1e1e;border-radius:3px;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(4)

        color = CHANNEL_COLORS.get(ch_type, "#666")
        self._num_lbl = QLabel(f"{ch_num:02d}")
        self._num_lbl.setFixedSize(26, 26)
        self._num_lbl.setAlignment(Qt.AlignCenter)
        self._set_num_style(color)
        layout.addWidget(self._num_lbl)

        self._combo = _NoScrollCombo()
        self._combo.setFixedHeight(26)
        self._combo.setStyleSheet(
            "QComboBox{background:#2a2a2a;color:#e0e0e0;border:1px solid #3a3a3a;"
            "border-radius:3px;padding:1px 6px;font-size:12px;}"
            "QComboBox::drop-down{border:none;width:16px;}"
            "QComboBox QAbstractItemView{background:#222;color:#e0e0e0;}"
        )
        for ct in ALL_CHANNEL_TYPES:
            self._combo.addItem(ct)
        idx = ALL_CHANNEL_TYPES.index(ch_type) if ch_type in ALL_CHANNEL_TYPES else 0
        self._combo.setCurrentIndex(idx)
        self._combo.currentTextChanged.connect(self._on_type_changed)
        layout.addWidget(self._combo, 1)

        _btn_style = (
            "QPushButton{background:#2a2a2a;color:#999;border:1px solid #3a3a3a;"
            "border-radius:3px;font-size:10px;min-width:0;padding:0;}"
            "QPushButton:hover{background:#3a3a3a;color:#fff;border-color:#555;}"
        )
        for text, slot in [("▲", self._on_up), ("▼", self._on_dn)]:
            b = QPushButton(text)
            b.setFixedSize(24, 26)
            b.setStyleSheet(_btn_style)
            b.clicked.connect(slot)
            layout.addWidget(b)

        btn_rm = QPushButton("✕")
        btn_rm.setFixedSize(26, 26)
        btn_rm.setStyleSheet(
            "QPushButton{background:#2a0000;color:#cc4444;border:1px solid #3a1111;"
            "border-radius:3px;font-size:11px;font-weight:bold;min-width:0;padding:0;}"
            "QPushButton:hover{background:#440000;color:#ff6666;border-color:#553333;}"
        )
        btn_rm.clicked.connect(self._on_rm)
        layout.addWidget(btn_rm)

    def _set_num_style(self, color):
        self._num_lbl.setStyleSheet(
            f"QLabel{{background:{color}22;border:1px solid {color};"
            f"border-radius:3px;color:{color};font-weight:bold;font-size:11px;}}"
        )

    def _on_type_changed(self, ch_type):
        color = CHANNEL_COLORS.get(ch_type, "#666")
        self._set_num_style(color)
        self.changed.emit()

    def _on_up(self):  self.move_up_requested.emit(self)
    def _on_dn(self):  self.move_dn_requested.emit(self)
    def _on_rm(self):  self.remove_requested.emit(self)

    def set_num(self, n):
        self._num_lbl.setText(f"{n:02d}")

    def get_type(self):
        return self._combo.currentText()


# ──────────────────────────────────────────────────────────────────────────────
# FixtureEditorDialog
# ──────────────────────────────────────────────────────────────────────────────

class FixtureEditorDialog(QDialog):
    """Editeur de templates de fixtures DMX"""
    fixture_added = Signal(dict)

    _STYLE = """
        QDialog      { background: #141414; color: #e0e0e0; }
        QLabel        { color: #e0e0e0; }
        QLineEdit     { background: #222; color: #e0e0e0; border: 1px solid #3a3a3a;
                        border-radius: 4px; padding: 5px 8px; font-size: 13px; }
        QLineEdit:focus { border: 1px solid #00d4ff; }
        QComboBox     { background: #222; color: #e0e0e0; border: 1px solid #3a3a3a;
                        border-radius: 4px; padding: 4px 8px; font-size: 12px; }
        QComboBox::drop-down { border: none; width: 20px; }
        QComboBox QAbstractItemView { background: #222; color: #e0e0e0;
                        selection-background-color: #00d4ff33; }
        QListWidget   { background: #1a1a1a; color: #e0e0e0; border: 1px solid #2a2a2a;
                        border-radius: 4px; outline: none; }
        QListWidget::item { padding: 5px 10px; border-radius: 3px; }
        QListWidget::item:selected { background: #00d4ff22; color: #00d4ff; }
        QListWidget::item:hover { background: #2a2a2a; }
        QScrollArea   { background: transparent; border: none; }
        QScrollBar:vertical { background: #1a1a1a; width: 7px; border-radius: 3px; }
        QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 3px; min-height: 16px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Editeur de fixture — MyStrow")
        self.setMinimumSize(860, 580)
        self.resize(980, 660)
        self._fixtures   = []   # custom fixtures (user-saved)
        self._current_idx = -1  # index in _all_fixtures()
        self._is_builtin  = False
        self._channel_rows = []
        self._undo_stack   = []
        self._btn_add_to_patch = None

        self._load_fixtures()
        self._build_ui()
        self._rebuild_list()
        if self._all_fixtures():
            self._select_fixture(0)

    # ── Data helpers ─────────────────────────────────────────────────────────

    def _all_fixtures(self):
        return BUILTIN_FIXTURES + self._fixtures

    def _load_fixtures(self):
        try:
            if FIXTURE_FILE.exists():
                data = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self._fixtures = [f for f in data if not f.get("builtin")]
        except Exception:
            self._fixtures = []

    def _save_fixtures(self):
        try:
            FIXTURE_FILE.write_text(
                json.dumps(self._fixtures, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Sauvegarde impossible:\n{e}")

    def _push_undo(self):
        self._undo_stack.append(copy.deepcopy(self._fixtures))
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            return
        self._fixtures = self._undo_stack.pop()
        self._save_fixtures()
        self._rebuild_list()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(self._STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        menubar = QMenuBar()
        self._create_menu_bar(menubar)
        outer.addWidget(menubar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        outer.addWidget(splitter, 1)

        # ── Left panel ───────────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(236)
        left.setStyleSheet("QWidget{background:#1a1a1a;}")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        lv.setSpacing(6)

        hdr = QLabel("TEMPLATES")
        hdr.setStyleSheet("font-size:10px;color:#555;letter-spacing:2px;font-weight:bold;")
        lv.addWidget(hdr)

        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        lv.addWidget(self._list_widget, 1)

        btn_new = QPushButton("  + Nouvelle fixture")
        btn_new.setFixedHeight(34)
        btn_new.setStyleSheet(
            "QPushButton{background:#1e3a1e;color:#44cc44;border:1px solid #2a6a2a;"
            "border-radius:4px;font-size:12px;font-weight:bold;text-align:left;padding-left:8px;}"
            "QPushButton:hover{background:#2a4a2a;border:1px solid #44aa44;}"
        )
        btn_new.clicked.connect(self._new_fixture)
        lv.addWidget(btn_new)
        splitter.addWidget(left)

        # ── Right panel ──────────────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet("QWidget{background:#141414;}")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(16, 12, 16, 12)
        rv.setSpacing(8)

        self._header_lbl = QLabel("Nouvelle fixture")
        self._header_lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#00d4ff;")
        rv.addWidget(self._header_lbl)

        self._builtin_badge = QLabel("  ⚙  Template intégré — dupliquer pour créer votre version  ")
        self._builtin_badge.setStyleSheet(
            "QLabel{background:#1a2a1a;color:#777;border:1px solid #2a3a2a;"
            "border-radius:4px;padding:4px 10px;font-size:11px;}"
        )
        self._builtin_badge.setVisible(False)
        rv.addWidget(self._builtin_badge)

        _sep = lambda: self._make_sep()

        rv.addWidget(_sep())

        # Form row: Name / Type / Group
        form_row = QHBoxLayout()
        form_row.setSpacing(16)

        def _labeled(lbl_txt, widget):
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl = QLabel(lbl_txt)
            lbl.setStyleSheet("font-size:10px;color:#888;font-weight:bold;letter-spacing:1px;")
            col.addWidget(lbl)
            col.addWidget(widget)
            return col

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Nom de la fixture...")
        self._name_edit.setFixedHeight(34)
        self._name_edit.textChanged.connect(lambda t: self._header_lbl.setText(t or "Nouvelle fixture"))
        form_row.addLayout(_labeled("NOM", self._name_edit), 2)

        self._type_combo = _NoScrollCombo()
        self._type_combo.setFixedHeight(34)
        for ft in FIXTURE_TYPES:
            self._type_combo.addItem(ft)
        form_row.addLayout(_labeled("TYPE", self._type_combo), 1)
        rv.addLayout(form_row)

        rv.addWidget(_sep())

        # Channel builder header
        ch_hdr = QHBoxLayout()
        ch_lbl = QLabel("CANAUX DMX")
        ch_lbl.setStyleSheet("font-size:10px;color:#888;font-weight:bold;letter-spacing:1px;")
        ch_hdr.addWidget(ch_lbl)
        ch_hdr.addStretch()
        # Quick-load profile combo
        self._profile_combo = QComboBox()
        self._profile_combo.setFixedHeight(28)
        self._profile_combo.setFixedWidth(200)
        self._profile_combo.setStyleSheet(
            "QComboBox{background:#1e2a3a;color:#00d4ff;border:1px solid #00d4ff44;"
            "border-radius:4px;padding:2px 6px;font-size:11px;}"
            "QComboBox::drop-down{border:none;width:16px;}"
            "QComboBox QAbstractItemView{background:#222;color:#e0e0e0;}"
        )
        self._profile_combo.addItem("↓  Charger un profil...")
        try:
            from artnet_dmx import DMX_PROFILES, profile_display_text
            for pname, pch in DMX_PROFILES.items():
                self._profile_combo.addItem(f"{pname}  ({profile_display_text(pch)})", pch)
        except ImportError:
            pass
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        ch_hdr.addWidget(self._profile_combo)
        rv.addLayout(ch_hdr)

        # Channel rows scroll area
        self._ch_scroll = QScrollArea()
        self._ch_scroll.setWidgetResizable(True)
        self._ch_scroll.setFixedHeight(170)
        self._ch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._ch_container = QWidget()
        self._ch_container.setStyleSheet("QWidget{background:#1a1a1a;border-radius:4px;}")
        self._ch_vbox = QVBoxLayout(self._ch_container)
        self._ch_vbox.setContentsMargins(4, 4, 4, 4)
        self._ch_vbox.setSpacing(2)
        self._ch_vbox.addStretch()
        self._ch_scroll.setWidget(self._ch_container)
        rv.addWidget(self._ch_scroll)

        # Add-channel row
        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self._add_ch_combo = QComboBox()
        self._add_ch_combo.setFixedHeight(30)
        for ct in ALL_CHANNEL_TYPES:
            self._add_ch_combo.addItem(ct)
        add_row.addWidget(self._add_ch_combo)
        btn_add_ch = QPushButton("+ Ajouter canal")
        btn_add_ch.setFixedHeight(30)
        btn_add_ch.setStyleSheet(
            "QPushButton{background:#1a2a3a;color:#00d4ff;border:1px solid #00d4ff44;"
            "border-radius:4px;font-size:12px;padding:0 12px;}"
            "QPushButton:hover{background:#1e3a4a;border:1px solid #00d4ff;}"
        )
        btn_add_ch.clicked.connect(self._add_channel)
        add_row.addWidget(btn_add_ch)
        add_row.addStretch()
        rv.addLayout(add_row)

        rv.addWidget(_sep())

        # Preview
        prev_lbl = QLabel("PRÉVISUALISATION")
        prev_lbl.setStyleSheet("font-size:10px;color:#888;font-weight:bold;letter-spacing:1px;")
        rv.addWidget(prev_lbl)

        self._preview = DmxPreviewWidget()
        self._preview.setStyleSheet("background:#1a1a1a;border-radius:4px;")
        rv.addWidget(self._preview)

        self._ch_count_lbl = QLabel("0 canal")
        self._ch_count_lbl.setStyleSheet("font-size:11px;color:#555;")
        rv.addWidget(self._ch_count_lbl)

        rv.addStretch()
        rv.addWidget(_sep())

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_duplicate = QPushButton("Dupliquer")
        self._btn_duplicate.setFixedHeight(34)
        self._btn_duplicate.setStyleSheet(
            "QPushButton{background:#2a2a1a;color:#cccc44;border:1px solid #4a4a22;"
            "border-radius:4px;font-size:12px;padding:0 12px;}"
            "QPushButton:hover{background:#3a3a1a;border:1px solid #aaaa33;}"
        )
        self._btn_duplicate.clicked.connect(self._duplicate_fixture)
        btn_row.addWidget(self._btn_duplicate)

        self._btn_delete = QPushButton("Supprimer")
        self._btn_delete.setFixedHeight(34)
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet(
            "QPushButton{background:#2a0000;color:#cc4444;border:1px solid #4a2222;"
            "border-radius:4px;font-size:12px;padding:0 12px;}"
            "QPushButton:hover{background:#400000;border:1px solid #cc4444;}"
            "QPushButton:disabled{background:#1a1a1a;color:#444;border:1px solid #2a2a2a;}"
        )
        self._btn_delete.clicked.connect(self._delete_fixture)
        btn_row.addWidget(self._btn_delete)

        btn_row.addStretch()

        self._btn_save = QPushButton("💾  Enregistrer")
        self._btn_save.setFixedHeight(36)
        self._btn_save.setStyleSheet(
            "QPushButton{background:#1a2a3a;color:#00aaff;border:1px solid #00aaff44;"
            "border-radius:4px;font-size:13px;font-weight:bold;padding:0 16px;}"
            "QPushButton:hover{background:#1e3a4a;border:1px solid #00aaff;}"
        )
        self._btn_save.clicked.connect(self._save_current)
        btn_row.addWidget(self._btn_save)

        btn_row.addSpacing(12)

        self._btn_add_to_patch = QPushButton("⊕  Ajouter au patch")
        self._btn_add_to_patch.setFixedHeight(40)
        self._btn_add_to_patch.setStyleSheet(
            "QPushButton{background:#003322;color:#00d4ff;border:2px solid #00d4ff;"
            "border-radius:6px;font-size:14px;font-weight:bold;padding:0 20px;}"
            "QPushButton:hover{background:#004433;}"
            "QPushButton:pressed{background:#00d4ff22;}"
            "QPushButton:disabled{background:#1a1a1a;color:#444;border:1px solid #2a2a2a;}"
        )
        self._btn_add_to_patch.clicked.connect(self._add_to_patch)
        btn_row.addWidget(self._btn_add_to_patch)

        rv.addLayout(btn_row)
        splitter.addWidget(right)
        splitter.setSizes([236, 744])

        self._list_widget.currentRowChanged.connect(self._on_list_selection)

    def _make_sep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#2a2a2a;")
        return sep

    def _create_menu_bar(self, menubar):
        menubar.setStyleSheet("""
            QMenuBar { background: #1a1a1a; color: #e0e0e0; border-bottom: 1px solid #2a2a2a; }
            QMenuBar::item { padding: 4px 10px; border-radius: 3px; }
            QMenuBar::item:selected { background: #2a2a2a; }
            QMenu { background: #1e1e1e; color: #e0e0e0; border: 1px solid #3a3a3a; }
            QMenu::item { padding: 6px 20px 6px 12px; }
            QMenu::item:selected { background: #00d4ff22; color: #00d4ff; }
            QMenu::separator { background: #2a2a2a; height: 1px; margin: 3px 8px; }
        """)
        m_file = menubar.addMenu("Fichier")
        act_import = m_file.addAction("📂  Importer des fixtures...")
        act_export = m_file.addAction("📤  Exporter la fixture...")
        m_file.addSeparator()
        act_reset = m_file.addAction("↺  Réinitialiser aux défauts")

        m_edit = menubar.addMenu("Edition")
        act_undo = m_edit.addAction("↩  Annuler\tCtrl+Z")
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))

        act_import.triggered.connect(self._import_fixtures)
        act_export.triggered.connect(self._export_fixture)
        act_reset.triggered.connect(self._reset_to_defaults)
        act_undo.triggered.connect(self._undo)

    # ── List management ───────────────────────────────────────────────────────

    def _rebuild_list(self):
        self._list_widget.blockSignals(True)
        self._list_widget.clear()
        current_type = None
        for i, fx in enumerate(self._all_fixtures()):
            ftype = fx.get("fixture_type", "?")
            if ftype != current_type:
                current_type = ftype
                hdr = QListWidgetItem(f"  {ftype.upper()}")
                hdr.setFlags(Qt.NoItemFlags)
                hdr.setForeground(QColor("#555"))
                f = hdr.font(); f.setPointSize(8); hdr.setFont(f)
                hdr.setBackground(QColor("#111"))
                self._list_widget.addItem(hdr)
            is_builtin = fx.get("builtin", False)
            n_ch = len(fx.get("profile", []))
            icon = "◦" if is_builtin else "◈"
            item = QListWidgetItem(f"  {icon} {fx['name']}")
            item.setData(Qt.UserRole, i)
            item.setForeground(QColor("#666" if is_builtin else "#cccccc"))
            item.setToolTip(f"{fx.get('fixture_type','?')} · {n_ch} canaux · groupe: {fx.get('group','?')}")
            self._list_widget.addItem(item)
        self._list_widget.blockSignals(False)
        if self._current_idx >= 0:
            self._select_list_item(self._current_idx)

    def _on_list_selection(self, row):
        item = self._list_widget.item(row)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if idx is None:
            return
        self._select_fixture(idx)

    def _select_fixture(self, idx):
        all_fx = self._all_fixtures()
        if idx < 0 or idx >= len(all_fx):
            return
        fx = all_fx[idx]
        self._current_idx = idx
        self._is_builtin  = fx.get("builtin", False)

        self._name_edit.blockSignals(True)
        self._name_edit.setText(fx.get("name", ""))
        self._name_edit.blockSignals(False)
        self._header_lbl.setText(fx.get("name", ""))

        fi = self._type_combo.findText(fx.get("fixture_type", "PAR LED"))
        if fi >= 0:
            self._type_combo.setCurrentIndex(fi)

        self._set_channels(fx.get("profile", ["R", "G", "B"]))

        self._builtin_badge.setVisible(self._is_builtin)
        self._btn_delete.setEnabled(not self._is_builtin)
        self._btn_save.setEnabled(not self._is_builtin)
        self._select_list_item(idx)

    def _select_list_item(self, fx_idx):
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item and item.data(Qt.UserRole) == fx_idx:
                self._list_widget.blockSignals(True)
                self._list_widget.setCurrentRow(i)
                self._list_widget.blockSignals(False)
                self._list_widget.scrollToItem(item)
                return

    # ── Channel rows ─────────────────────────────────────────────────────────

    def _set_channels(self, channels):
        for row in self._channel_rows:
            self._ch_vbox.removeWidget(row)
            row.deleteLater()
        self._channel_rows.clear()
        for i, ch in enumerate(channels):
            self._append_channel_row(i + 1, ch)
        self._update_preview()

    def _append_channel_row(self, num, ch_type):
        row = ChannelRowWidget(num, ch_type)
        row.remove_requested.connect(self._remove_channel_row)
        row.move_up_requested.connect(self._move_channel_up)
        row.move_dn_requested.connect(self._move_channel_dn)
        row.changed.connect(self._update_preview)
        self._ch_vbox.insertWidget(self._ch_vbox.count() - 1, row)
        self._channel_rows.append(row)

    def _remove_channel_row(self, row):
        if row in self._channel_rows:
            self._channel_rows.remove(row)
            self._ch_vbox.removeWidget(row)
            row.deleteLater()
            self._renumber_rows()
            self._update_preview()

    def _move_channel_up(self, row):
        idx = self._channel_rows.index(row) if row in self._channel_rows else -1
        if idx <= 0:
            return
        self._channel_rows[idx], self._channel_rows[idx - 1] = self._channel_rows[idx - 1], self._channel_rows[idx]
        self._ch_vbox.removeWidget(row)
        self._ch_vbox.insertWidget(idx - 1, row)
        self._renumber_rows()
        self._update_preview()

    def _move_channel_dn(self, row):
        idx = self._channel_rows.index(row) if row in self._channel_rows else -1
        if idx < 0 or idx >= len(self._channel_rows) - 1:
            return
        self._channel_rows[idx], self._channel_rows[idx + 1] = self._channel_rows[idx + 1], self._channel_rows[idx]
        self._ch_vbox.removeWidget(row)
        self._ch_vbox.insertWidget(idx + 1, row)
        self._renumber_rows()
        self._update_preview()

    def _renumber_rows(self):
        for i, row in enumerate(self._channel_rows):
            row.set_num(i + 1)

    def _add_channel(self):
        ch_type = self._add_ch_combo.currentText()
        self._append_channel_row(len(self._channel_rows) + 1, ch_type)
        self._update_preview()
        self._ch_scroll.verticalScrollBar().setValue(
            self._ch_scroll.verticalScrollBar().maximum()
        )

    def _get_current_channels(self):
        return [row.get_type() for row in self._channel_rows]

    def _update_preview(self):
        channels = self._get_current_channels()
        self._preview.set_channels(channels)
        n = len(channels)
        self._ch_count_lbl.setText(f"{n} canal{'x' if n > 1 else ''}")

    def _on_profile_selected(self, idx):
        if idx == 0:
            return
        channels = self._profile_combo.itemData(idx)
        if channels:
            self._set_channels(channels)
        self._profile_combo.setCurrentIndex(0)

    # ── Form data ─────────────────────────────────────────────────────────────

    def _get_form_data(self):
        return {
            "name":         self._name_edit.text().strip(),
            "fixture_type": self._type_combo.currentText(),
            "group":        "face",
            "profile":      self._get_current_channels(),
        }

    # ── CRUD actions ──────────────────────────────────────────────────────────

    def _new_fixture(self):
        self._current_idx = -1
        self._is_builtin  = False
        self._name_edit.blockSignals(True)
        self._name_edit.setText("")
        self._name_edit.blockSignals(False)
        self._header_lbl.setText("Nouvelle fixture")
        self._type_combo.setCurrentIndex(0)
        self._set_channels(["R", "G", "B"])
        self._builtin_badge.setVisible(False)
        self._btn_delete.setEnabled(False)
        self._btn_save.setEnabled(True)
        self._list_widget.blockSignals(True)
        self._list_widget.clearSelection()
        self._list_widget.blockSignals(False)
        self._name_edit.setFocus()

    def _save_current(self):
        data = self._get_form_data()
        if not data["name"]:
            QMessageBox.warning(self, "Nom requis", "Veuillez entrer un nom pour la fixture.")
            self._name_edit.setFocus()
            return
        if not data["profile"]:
            QMessageBox.warning(self, "Canaux requis", "Ajoutez au moins un canal DMX.")
            return
        self._push_undo()
        all_fx = self._all_fixtures()
        if (self._current_idx >= 0 and self._current_idx < len(all_fx)
                and not all_fx[self._current_idx].get("builtin")):
            custom_idx = self._current_idx - len(BUILTIN_FIXTURES)
            if 0 <= custom_idx < len(self._fixtures):
                self._fixtures[custom_idx] = data
        else:
            existing_names = {f["name"] for f in self._fixtures}
            name = data["name"]
            if name in existing_names:
                c = 2
                while f"{name} ({c})" in existing_names:
                    c += 1
                data["name"] = f"{name} ({c})"
                self._name_edit.setText(data["name"])
            self._fixtures.append(data)
            self._current_idx = len(BUILTIN_FIXTURES) + len(self._fixtures) - 1
        self._save_fixtures()
        self._rebuild_list()
        self._btn_delete.setEnabled(True)

    def _duplicate_fixture(self):
        data = self._get_form_data()
        name = data["name"] or "Fixture"
        data["name"] = name + " (copie)"
        self._push_undo()
        self._fixtures.append(data)
        self._save_fixtures()
        self._current_idx = len(BUILTIN_FIXTURES) + len(self._fixtures) - 1
        self._is_builtin  = False
        self._rebuild_list()
        self._builtin_badge.setVisible(False)
        self._btn_delete.setEnabled(True)
        self._btn_save.setEnabled(True)
        self._name_edit.setText(data["name"])
        self._header_lbl.setText(data["name"])

    def _delete_fixture(self):
        if self._is_builtin:
            return
        name = self._name_edit.text().strip() or "cette fixture"
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la fixture « {name} » ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        all_fx = self._all_fixtures()
        if 0 <= self._current_idx < len(all_fx):
            custom_idx = self._current_idx - len(BUILTIN_FIXTURES)
            if 0 <= custom_idx < len(self._fixtures):
                self._push_undo()
                self._fixtures.pop(custom_idx)
                self._save_fixtures()
                self._current_idx = -1
                self._rebuild_list()
                self._new_fixture()

    def _add_to_patch(self):
        data = self._get_form_data()
        if not data["name"]:
            QMessageBox.warning(self, "Nom requis", "Entrez un nom pour la fixture.")
            return
        if not data["profile"]:
            QMessageBox.warning(self, "Canaux requis", "Ajoutez au moins un canal DMX.")
            return
        self.fixture_added.emit(data)
        self._btn_add_to_patch.setText("✓  Ajouté !")
        self._btn_add_to_patch.setEnabled(False)
        QTimer.singleShot(1400, self._reset_add_btn)

    def _reset_add_btn(self):
        if self._btn_add_to_patch:
            self._btn_add_to_patch.setText("⊕  Ajouter au patch")
            self._btn_add_to_patch.setEnabled(True)

    # ── Import / Export ───────────────────────────────────────────────────────

    def _import_fixtures(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer des fixtures", str(Path.home()),
            "Fixtures MyStrow (*.mft *.json)"
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                raise ValueError("Format invalide")
            self._push_undo()
            existing = {f["name"] for f in self._fixtures}
            imported = 0
            for fx in data:
                if "name" not in fx or "profile" not in fx:
                    continue
                fx.pop("builtin", None)
                name = fx["name"]
                if name in existing:
                    c = 2
                    while f"{name} ({c})" in existing:
                        c += 1
                    fx["name"] = f"{name} ({c})"
                self._fixtures.append(fx)
                existing.add(fx["name"])
                imported += 1
            self._save_fixtures()
            self._rebuild_list()
            QMessageBox.information(self, "Import réussi", f"{imported} fixture(s) importée(s).")
        except Exception as e:
            QMessageBox.warning(self, "Erreur d'import", f"Impossible d'importer:\n{e}")

    def _export_fixture(self):
        data = self._get_form_data()
        if not data["name"]:
            QMessageBox.warning(self, "Rien à exporter", "Sélectionnez ou créez une fixture d'abord.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter la fixture",
            str(Path.home() / f"{data['name']}.mft"),
            "Fixture MyStrow (*.mft)"
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            QMessageBox.information(self, "Export réussi", f"Fixture exportée :\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Erreur d'export", f"Impossible d'exporter:\n{e}")

    def _reset_to_defaults(self):
        if QMessageBox.question(
            self, "Réinitialiser",
            "Supprimer toutes les fixtures personnalisées et revenir aux défauts ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self._push_undo()
        self._fixtures = []
        self._save_fixtures()
        self._current_idx = -1
        self._rebuild_list()
        if BUILTIN_FIXTURES:
            self._select_fixture(0)
