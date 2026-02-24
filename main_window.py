"""
Fenetre principale de l'application - MainWindow
Module extrait de maestro.py pour une meilleure organisation
"""
import sys
import os
import json
import random
import ctypes
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QSplitter, QScrollArea, QSlider,
    QToolButton, QMenu, QMenuBar, QFileDialog, QMessageBox, QDialog,
    QComboBox, QTableWidget, QTableWidgetItem, QWidgetAction, QSpinBox,
    QTabWidget, QProgressBar, QApplication, QLineEdit, QStackedWidget,
    QHeaderView
)
from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QPoint
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QPixmap, QIcon, QFont,
    QPalette, QPolygon
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget

from core import (
    APP_NAME, VERSION, MIDI_AVAILABLE,
    rgb_to_akai_velocity, fmt_time, create_icon, media_icon, resource_path
)
from projector import Projector
from artnet_dmx import ArtNetDMX, DMX_PROFILES, CHANNEL_TYPES, profile_for_mode, profile_name, profile_display_text
from audio_ai import AudioColorAI
from midi_handler import MIDIHandler
from ui_components import DualColorButton, EffectButton, FaderButton, ApcFader, CartoucheButton
from plan_de_feu import PlanDeFeu, ColorPickerBlock, _PatchCanvasProxy
from recording_waveform import RecordingWaveform
from sequencer import Sequencer
from timeline_editor import LightTimelineEditor
from updater import UpdateBar, UpdateChecker, download_update, AboutDialog
from license_manager import LicenseState, LicenseResult, verify_license
from license_ui import LicenseBanner, ActivationDialog, LicenseWarningDialog


class VideoOutputWindow(QWidget):
    """Fenetre de sortie video plein ecran sur un second moniteur"""

    PAGE_VIDEO = 0
    PAGE_BLACK = 1
    PAGE_IMAGE = 2

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Sortie Video - Maestro")
        self.setStyleSheet("background: black;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Page 0 : Video
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background: black;")
        self.stack.addWidget(self.video_widget)

        # Page 1 : Ecran noir
        self.black_label = QLabel()
        self.black_label.setStyleSheet("background: black;")
        self.stack.addWidget(self.black_label)

        # Page 2 : Image
        self.image_label = QLabel()
        self.image_label.setStyleSheet("background: black;")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self.image_label)

        self.stack.setCurrentIndex(self.PAGE_BLACK)

        # Watermark overlay (licence)
        self._watermark = None

    def set_watermark(self, visible):
        """Affiche ou masque le watermark de licence"""
        if visible and not self._watermark:
            self._watermark = QLabel(self)
            self._watermark.setAlignment(Qt.AlignCenter)
            self._watermark.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._create_watermark_pixmap()
            self._watermark.show()
            self._watermark.raise_()
        elif not visible and self._watermark:
            self._watermark.hide()
            self._watermark.deleteLater()
            self._watermark = None

    def _create_watermark_pixmap(self):
        """Cree le pixmap du watermark"""
        if not self._watermark:
            return
        import os
        base = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base, "Mystrow_blanc.png")
        if os.path.exists(logo_path):
            px = QPixmap(logo_path)
            # 30% de la taille de la fenetre
            target_w = max(200, int(self.width() * 0.3))
            scaled = px.scaledToWidth(target_w, Qt.SmoothTransformation)
            # Appliquer opacite 40%
            result = QPixmap(scaled.size())
            result.fill(Qt.transparent)
            painter = QPainter(result)
            painter.setOpacity(0.4)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            self._watermark.setPixmap(result)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._watermark:
            self._create_watermark_pixmap()
            # Centrer le watermark
            wm_size = self._watermark.sizeHint()
            x = (self.width() - wm_size.width()) // 2
            y = (self.height() - wm_size.height()) // 2
            self._watermark.setGeometry(x, y, wm_size.width(), wm_size.height())

    def show_black(self):
        """Affiche un ecran noir"""
        self.stack.setCurrentIndex(self.PAGE_BLACK)

    def show_video(self):
        """Affiche la video"""
        self.stack.setCurrentIndex(self.PAGE_VIDEO)

    def show_image(self, pixmap):
        """Affiche une image"""
        scaled = pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.stack.setCurrentIndex(self.PAGE_IMAGE)

    def closeEvent(self, event):
        """Cacher au lieu de detruire"""
        self.hide()
        event.ignore()


class MainWindow(QMainWindow):
    """Fenetre principale de l'application"""

    def __init__(self, license_result=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1800, 1000)

        # Licence (resultat cache pour toute la session)
        self._license = license_result or LicenseResult(
            state=LicenseState.NOT_ACTIVATED,
            dmx_allowed=False, watermark_required=True,
            message="Connectez-vous a votre compte MyStrow", action_label="Connexion"
        )

        # Icone de l'application
        self._create_window_icon()

        # Creation des projecteurs (fixtures)
        self._load_default_fixtures()

        # Variables d'etat
        self.active_pads = {}  # {col_idx: QPushButton} - un pad actif par colonne
        self.active_dual_pad = None
        self.audio_ai = AudioColorAI()
        self.fader_buttons = []
        self.faders = {}
        self.pads = {}
        self.effect_buttons = []
        self.active_effect = None
        self.effect_speed = 0
        self.effect_state = 0
        self.effect_saved_colors = {}
        self.blink_timer = None
        self.pause_mode = False

        # Mapping faders → groupes (independants)
        self.FADER_GROUPS = {
            0: ["face"],
            1: ["contre", "lat"],
            2: ["douche1", "douche2", "douche3"],
            3: ["public"],
            4: None,  # Memoire 1
            5: None,  # Memoire 2
            6: None,  # Memoire 3
            7: None,  # Memoire 4
        }
        self.memories = [[None]*8, [None]*8, [None]*8, [None]*8]  # 4 cols x 8 rows
        self.memory_custom_colors = [[None]*8, [None]*8, [None]*8, [None]*8]
        self.active_memory_pads = {}  # {col_akai: row} pad actif par colonne memoire

        # Configuration AKAI
        self.akai_active_brightness = 100
        self.akai_inactive_brightness = 20
        self.blackout_active = False

        # DMX Art-Net Handler
        self.dmx = ArtNetDMX()
        self._saved_custom_profiles = {}
        self.auto_patch_at_startup()

        self.dmx_send_timer = QTimer()
        self.dmx_send_timer.timeout.connect(self.send_dmx_update)
        self.dmx_send_timer.start(40)  # 25 FPS

        # MIDI Handler
        self.midi_handler = MIDIHandler()
        self.midi_handler.owner_window = self
        self.midi_handler.fader_changed.connect(self.on_midi_fader)
        self.midi_handler.pad_pressed.connect(self.on_midi_pad)

        # Dimmers max IA Lumiere par groupe
        self.ia_max_dimmers = {
            'face': 50, 'lat': 100, 'contre': 100,
            'douche1': 100, 'douche2': 100, 'douche3': 100,
            'public': 80,
        }
        self.load_ia_lumiere_config()

        # Fichiers recents
        self.recent_files = self.load_recent_files()
        self.current_show_path = None  # Chemin du show actuellement ouvert

        # Creation du menu
        self._create_menu()

        # Creation du panneau AKAI
        self.akai = self.create_akai_panel()

        # Player
        self.audio = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio)
        self.player_ui = type('obj', (object,), {
            'player': self.player,
            'audio': self.audio,
            'play': self.play_path,
            'trigger_pause': self.trigger_pause_mode
        })

        # Video frame
        self._create_video_frame()

        # Cartoucheur - player dedie
        self.cart_audio = QAudioOutput()
        self.cart_player = QMediaPlayer()
        self.cart_player.setAudioOutput(self.cart_audio)
        self.cart_player.mediaStatusChanged.connect(self.on_cart_media_status)
        self.cart_playing_index = -1

        # Sequenceur
        self.seq = Sequencer(self)
        self.seq.table.cellDoubleClicked.connect(self.seq.play_row)
        self.seq.table.setContextMenuPolicy(Qt.CustomContextMenu)

        # Transport
        self.transport = self.create_transport_panel()

        # Timer IA
        self.ai_timer = QTimer(self)
        self.ai_timer.timeout.connect(self.update_audio_ai)
        self.ai_timer.start(100)

        self.player.mediaStatusChanged.connect(self.on_media_status_changed)

        # Layout principal
        self._create_main_layout()

        self.player.playbackStateChanged.connect(self.update_play_icon)
        self.apply_styles()

        # Charger la configuration AKAI sauvegardee automatiquement
        self._load_akai_config_auto()

        # Plein ecran gere par maestro_new.py (apres splash)

        # Bloquer la mise en veille Windows
        self._prevent_sleep()

        # Suivi des modifications non sauvegardees (titre avec *)
        self._last_dirty_state = False
        self._dirty_timer = QTimer(self)
        self._dirty_timer.timeout.connect(self._update_dirty_title)
        self._dirty_timer.start(500)

        # Initialisation au demarrage
        QTimer.singleShot(100, self.activate_default_white_pads)
        QTimer.singleShot(200, self.turn_off_all_effects)
        QTimer.singleShot(1000, self.test_dmx_on_startup)

    def _prevent_sleep(self):
        """Empeche Windows de se mettre en veille tant que l'application tourne"""
        try:
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
            print("Anti-veille active")
        except Exception as e:
            print(f"Anti-veille: {e}")

    def _allow_sleep(self):
        """Restaure le comportement de veille normal"""
        try:
            ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass

    def _update_dirty_title(self):
        """Met a jour le titre avec * si modifications non sauvegardees"""
        is_dirty = self.seq.is_dirty
        if is_dirty == self._last_dirty_state:
            return
        self._last_dirty_state = is_dirty

        if self.current_show_path:
            base = f"{APP_NAME} - {os.path.basename(self.current_show_path)}"
        else:
            base = APP_NAME

        if is_dirty:
            self.setWindowTitle(f"{base} *")
        else:
            self.setWindowTitle(base)

    def _create_window_icon(self):
        """Charge l'icone de la fenetre depuis mystrow.ico"""
        ico_path = resource_path("mystrow.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))

    # Mapping nom de groupe -> nom d'affichage dans la timeline
    GROUP_DISPLAY = {
        "face":    "Groupe A",
        "contre":  "Groupe B",
        "lat":     "Groupe B",
        "douche1": "Groupe C",
        "douche2": "Groupe C",
        "douche3": "Groupe C",
        "public":  "Groupe D",
        "fumee": "Fumee",
        "lyre": "Lyres",
        "barre": "Barres",
        "strobe": "Strobos",
    }

    # Fixtures par defaut (nom, type, groupe interne)
    _DEFAULT_FIXTURES = [
        ("Face 1",   "PAR LED", "face"),
        ("Face 2",   "PAR LED", "face"),
        ("Face 3",   "PAR LED", "face"),
        ("Face 4",   "PAR LED", "face"),
        ("Douche 1", "PAR LED", "douche1"),
        ("Douche 2", "PAR LED", "douche2"),
        ("Douche 3", "PAR LED", "douche3"),
        ("Lat 1",    "PAR LED", "lat"),
        ("Lat 2",    "PAR LED", "lat"),
        ("Contre 1", "PAR LED", "contre"),
        ("Contre 2", "PAR LED", "contre"),
        ("Contre 3", "PAR LED", "contre"),
        ("Contre 4", "PAR LED", "contre"),
        ("Contre 5", "PAR LED", "contre"),
        ("Contre 6", "PAR LED", "contre"),
        ("Public",   "PAR LED", "public"),
        ("Fumee",    "Machine a fumee", "fumee"),
    ]

    # Canaux par type (pour adressage compact)
    _FIXTURE_CH = {
        "PAR LED": 5, "Moving Head": 8, "Barre LED": 5,
        "Stroboscope": 2, "Machine a fumee": 2,
    }

    def _load_default_fixtures(self):
        """Cree les fixtures par defaut avec adressage compact"""
        self.projectors = []
        addr = 1
        for name, ftype, group in self._DEFAULT_FIXTURES:
            p = Projector(group, name=name, fixture_type=ftype)
            p.start_address = addr
            addr += self._FIXTURE_CH.get(ftype, 5)
            self.projectors.append(p)
        # Attribut special fumee
        self.projectors[-1].fan_speed = 0

    def get_track_to_indices(self):
        """Retourne le mapping nom_affichage_groupe -> [indices projecteurs]"""
        mapping = {}
        for i, proj in enumerate(self.projectors):
            group_name = self.GROUP_DISPLAY.get(proj.group, proj.group.capitalize())
            mapping.setdefault(group_name, []).append(i)
        return mapping

    def _create_menu(self):
        """Cree la barre de menu"""
        bar = self.menuBar()

        file_menu = bar.addMenu("📁 Fichier")
        new_action = file_menu.addAction("📄 Nouveau Show", self.new_show)
        new_action.setShortcut("Ctrl+N")
        file_menu.addSeparator()
        open_action = file_menu.addAction("📂 Ouvrir Show...", self.load_show)
        open_action.setShortcut("Ctrl+O")
        save_action = file_menu.addAction("💾 Enregistrer Show", self.save_show)
        save_action.setShortcut("Ctrl+S")
        save_as_action = file_menu.addAction("💾 Enregistrer sous...", self.save_show_as)
        save_as_action.setShortcut("Ctrl+Shift+S")
        file_menu.addSeparator()
        self.recent_menu = file_menu.addMenu("📋 Recents")
        self.update_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction("📥 Importer une configuration...", self.import_akai_config)
        file_menu.addAction("📤 Exporter une configuration...", self.export_akai_config)
        file_menu.addSeparator()
        file_menu.addAction("🎨 Charger les configurations par defaut", self.load_default_presets)
        file_menu.addSeparator()
        file_menu.addAction("❌ Quitter", self.close)

        edit_menu = bar.addMenu("✏️ Edition")
        edit_menu.addAction("🔌 Patch DMX", self.show_dmx_patch_config)
        edit_menu.addSeparator()
        edit_menu.addAction("🔴 REC Lumière", self.open_light_editor)
        edit_menu.addAction("🔊 Volume", self._edit_current_volume)
        edit_menu.addAction("⏱ Définir la durée", self._edit_current_duration)
        edit_menu.addSeparator()
        edit_menu.addAction("💡 IA Lumière", self.show_ia_lumiere_config)
        edit_menu.addAction("⌨️ Raccourcis", self.show_shortcuts_dialog)

        conn_menu = bar.addMenu("🔗 Connexion")

        akai_menu = conn_menu.addMenu("🎹 Entrée Akai")
        akai_menu.addAction("🔍 Tester la connexion", self.test_akai_connection)
        akai_menu.addAction("🔄 Reinitialiser AKAI", self.reset_akai)

        self.node_menu = conn_menu.addMenu("🌐 Sortie Node")
        self.node_menu.addAction("🔍 Tester la connexion", self.test_node_connection)
        self.node_menu.addAction("⚙️ Paramétrer la sortie", self.open_node_connection)

        audio_menu = conn_menu.addMenu("🔊 Sortie Audio")
        audio_menu.addAction("🔉 Envoi un son de test", self.play_test_sound)
        self.audio_output_menu = audio_menu.addMenu("🎧 Sortie Audio")
        self.audio_output_menu.aboutToShow.connect(self._populate_audio_output_menu)

        video_menu = conn_menu.addMenu("🖥️ Sortie Vidéo")
        self.video_test_action = video_menu.addAction("🖼️ Envoi un logo de test", self.show_test_logo)
        self.video_screen_menu = video_menu.addMenu("🖥️ Diffuser video sur")
        self.video_screen_menu.aboutToShow.connect(self._populate_screen_menu)
        self.video_target_screen = 1  # Ecran cible par defaut (second ecran)

        about_menu = bar.addMenu("ℹ️ A propos")
        about_menu.addAction("ℹ️ A propos / Mises à jour", self.show_about)
        about_menu.addSeparator()
        about_menu.addAction("🔑 Licence", self._open_activation_dialog)

        bar.addAction("🔄 Restart", self.restart_application)

    def _create_video_frame(self):
        """Cree le frame video avec overlay image"""
        self.video_frame = QFrame()
        vv = QVBoxLayout(self.video_frame)
        vv.setContentsMargins(10, 10, 10, 10)

        # Titre + bouton toggle sortie video
        title_layout = QHBoxLayout()
        title = QLabel("Video")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        title_layout.addWidget(title)
        title_layout.addStretch()

        self.video_output_btn = QPushButton("OFF")
        self.video_output_btn.setCheckable(True)
        self.video_output_btn.setFixedSize(50, 24)
        self.video_output_btn.setStyleSheet("""
            QPushButton {
                background: #8b0000; color: white; border: none;
                border-radius: 12px; font-weight: bold; font-size: 10px;
            }
            QPushButton:checked {
                background: #228b22;
            }
        """)
        self.video_output_btn.clicked.connect(self.toggle_video_output)
        title_layout.addWidget(self.video_output_btn)

        vv.addLayout(title_layout)

        # Fenetre de sortie video (creee a la demande)
        self.video_output_window = None

        # QStackedWidget pour basculer entre video et image
        self.video_stack = QStackedWidget()
        self.video_stack.setStyleSheet("background: #000; border: 1px solid #2a2a2a; border-radius: 6px;")

        # Page 0 : QVideoWidget
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background: #000;")
        self.player.setVideoOutput(self.video_widget)
        self.video_stack.addWidget(self.video_widget)

        # Page 1 : QLabel pour afficher les images
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: #000;")
        self.video_stack.addWidget(self.image_label)

        self.video_stack.setCurrentIndex(0)
        vv.addWidget(self.video_stack)

    def _enforce_video_ratio(self):
        """Ajuste la hauteur video pour maintenir un ratio 16:9"""
        w = self.video_frame.width()
        if w > 0:
            target_h = int(w * 9 / 16) + 40  # +40 pour la barre titre
            sizes = self._right_splitter.sizes()
            if len(sizes) == 3:
                total = sum(sizes)
                sizes[2] = target_h
                sizes[0] = total - sizes[1] - sizes[2]
                if sizes[0] > 50:
                    self._right_splitter.setSizes(sizes)

    def show_image(self, path):
        """Affiche une image dans le preview integre"""
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return

        target_size = self.video_stack.size()
        if target_size.width() > 0 and target_size.height() > 0:
            scaled = pixmap.scaled(target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            scaled = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.image_label.setPixmap(scaled)
        self.video_stack.setCurrentIndex(1)

    def hide_image(self):
        """Revient a l'affichage video dans le preview integre"""
        self.video_stack.setCurrentIndex(0)

    def toggle_video_output(self):
        """Active/desactive la sortie video externe"""
        if self.video_output_btn.isChecked():
            # ON - creer/montrer la fenetre
            self.video_output_btn.setText("ON")
            if not self.video_output_window:
                self.video_output_window = VideoOutputWindow()
                # Appliquer watermark si licence non active
                self.video_output_window.set_watermark(self._license.watermark_required)

            # Placer sur l'ecran cible choisi
            screens = QApplication.screens()
            target = self.video_target_screen
            if target < len(screens):
                screen = screens[target]
                self.video_output_window.setGeometry(screen.geometry())
                self.video_output_window.showFullScreen()
            else:
                self.video_output_window.resize(960, 540)
                self.video_output_window.show()

            # Forwarder les frames video vers la fenetre externe via le sink
            sink = self.video_widget.videoSink()
            if sink:
                sink.videoFrameChanged.connect(self._forward_video_frame)
            self._update_video_output_state()
        else:
            # OFF - cacher la fenetre
            self.video_output_btn.setText("OFF")
            # Deconnecter le forward de frames
            sink = self.video_widget.videoSink()
            if sink:
                try:
                    sink.videoFrameChanged.disconnect(self._forward_video_frame)
                except:
                    pass
            if self.video_output_window:
                self.video_output_window.hide()

    def _forward_video_frame(self, frame):
        """Forward une frame video vers la fenetre de sortie externe"""
        if self.video_output_window and self.video_output_window.isVisible():
            ext_sink = self.video_output_window.video_widget.videoSink()
            if ext_sink:
                ext_sink.setVideoFrame(frame)

    def _update_video_output_state(self):
        """Met a jour l'affichage de la fenetre video externe selon le media courant"""
        if not self.video_output_window or not self.video_output_window.isVisible():
            return

        # Determiner le type de media en cours
        row = self.seq.current_row
        if row < 0:
            self.video_output_window.show_black()
            return

        item = self.seq.table.item(row, 1)
        if not item:
            self.video_output_window.show_black()
            return

        path = item.data(Qt.UserRole)
        if not path:
            # C'est une PAUSE ou TEMPO
            self.video_output_window.show_black()
            return

        media_type = media_icon(path)
        if media_type == "video":
            self.video_output_window.show_video()
        elif media_type == "image":
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.video_output_window.show_image(pixmap)
            else:
                self.video_output_window.show_black()
        else:
            # Audio ou autre -> ecran noir
            self.video_output_window.show_black()

    def _create_main_layout(self):
        """Cree le layout principal"""
        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.addWidget(self.seq)
        mv.addWidget(self.transport)

        plan_scroll = QScrollArea()
        plan_scroll.setWidgetResizable(True)
        self.plan_de_feu = PlanDeFeu(self.projectors, self)
        if not self._license.dmx_allowed:
            self.plan_de_feu.set_dmx_blocked()
        plan_scroll.setWidget(self.plan_de_feu)
        plan_scroll.setStyleSheet("QScrollArea { border: none; }")

        self.color_picker_block = ColorPickerBlock(self.plan_de_feu)

        right = QSplitter(Qt.Vertical)
        right.setHandleWidth(2)
        right.setMinimumWidth(240)
        right.addWidget(plan_scroll)
        right.addWidget(self.color_picker_block)
        right.addWidget(self.video_frame)
        right.setStretchFactor(0, 2)
        right.setStretchFactor(1, 0)
        right.setStretchFactor(2, 3)
        right.setCollapsible(0, False)
        right.setCollapsible(1, False)
        right.setCollapsible(2, False)

        # Forcer ratio 16:9 sur la video
        self._right_splitter = right
        self._right_splitter_initialized = False
        right.splitterMoved.connect(self._enforce_video_ratio)

        main_split = QSplitter(Qt.Horizontal)
        main_split.setHandleWidth(2)
        main_split.addWidget(self.akai)
        main_split.addWidget(mid)
        main_split.addWidget(right)
        main_split.setStretchFactor(0, 0)  # AKAI = taille fixe
        main_split.setStretchFactor(1, 5)  # Sequenceur = priorite
        main_split.setStretchFactor(2, 2)
        main_split.setCollapsible(0, False)
        main_split.setCollapsible(1, False)
        main_split.setCollapsible(2, False)
        self._main_split = main_split

        # Barre de mise a jour (cachee par defaut)
        self.update_bar = UpdateBar()
        self.update_bar.hide()
        self.update_bar.later_clicked.connect(self._on_update_later)
        self.update_bar.update_clicked.connect(self._on_update_now)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.update_bar)
        central_layout.addWidget(main_split, 1)
        self.setCentralWidget(central)

        # Watermark sur le preview video integre
        self._setup_video_watermark()

    def showEvent(self, event):
        """Au premier affichage, fixer les tailles du splitter droit (ratio 16:9 video)"""
        super().showEvent(event)
        if not self._right_splitter_initialized:
            self._right_splitter_initialized = True
            QTimer.singleShot(0, self._init_right_splitter_sizes)

    def _init_right_splitter_sizes(self):
        """Calcule et applique les tailles initiales des splitters"""
        # Splitter horizontal : AKAI (fixe 370) | Centre | Droite
        total_w = self._main_split.width()
        if total_w > 0:
            akai_w = 370
            right_w = max(260, int(total_w * 0.22))
            mid_w = total_w - akai_w - right_w
            if mid_w < 200:
                mid_w = 200
                right_w = total_w - akai_w - mid_w
            self._main_split.setSizes([akai_w, mid_w, right_w])

        # Splitter vertical droit : Plan de feu | Color Picker | Video 16:9
        total = self._right_splitter.height()
        if total <= 0:
            return
        video_w = self.video_frame.width()
        if video_w <= 0:
            video_w = 400
        video_h = int(video_w * 9 / 16) + 40  # +40 pour la barre titre
        picker_h = self.color_picker_block.sizeHint().height()
        plan_h = total - video_h - picker_h
        if plan_h < 100:
            plan_h = 100
            video_h = total - plan_h - picker_h
        self._right_splitter.setSizes([plan_h, picker_h, video_h])

    def create_akai_panel(self):
        """Cree le panneau AKAI avec 8 colonnes + colonne effets"""
        frame = QFrame()
        frame.setFixedWidth(370)
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("AKAI APC mini")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(title)
        layout.addSpacing(6)

        # Grille de pads
        pads = QGridLayout()
        pads.setSpacing(4)

        base_colors = [
            QColor("white"), QColor("#ff0000"), QColor("#ff8800"), QColor("#ffdd00"),
            QColor("#00ff00"), QColor("#00dddd"), QColor("#0000ff"), QColor("#ff00ff")
        ]

        for r in range(8):
            for c in range(8):
                if c < 4:
                    # Pads couleur standard (cols 0-3: face, contre+lat, douche, public)
                    col = base_colors[r]
                    b = QPushButton()
                    b.setFixedSize(28, 28)
                    dim_color = QColor(int(col.red() * 0.5), int(col.green() * 0.5), int(col.blue() * 0.5))
                    b.setStyleSheet(f"""
                        QPushButton {{
                            background: {dim_color.name()};
                            border: 1px solid #2a2a2a;
                            border-radius: 4px;
                        }}
                    """)
                    b.setProperty("base_color", col)
                    b.setProperty("color2", None)
                    b.setProperty("dim_color", dim_color)
                    b.clicked.connect(lambda _, btn=b, col=c: self.activate_pad(btn, col))
                else:  # c in (4, 5, 6, 7)
                    # Memory pads individuels - chaque pad = une memoire
                    mem_col = c - 4
                    b = QPushButton()
                    b.setFixedSize(28, 28)
                    b.setStyleSheet("""
                        QPushButton {
                            background: #1a1a1a;
                            border: 1px solid #1a1a1a;
                            border-radius: 4px;
                        }
                    """)
                    b.setProperty("base_color", QColor("black"))
                    b.setProperty("color2", None)
                    b.setProperty("memory_col", mem_col)
                    b.setProperty("memory_row", r)
                    b.clicked.connect(lambda _, btn=b, mc=mem_col, mr=r: self._activate_memory_pad(btn, mc, mr))
                    b.setContextMenuPolicy(Qt.CustomContextMenu)
                    b.customContextMenuRequested.connect(
                        lambda pos, mc=mem_col, mr=r, btn=b: self._show_memory_context_menu(pos, mc, mr, btn)
                    )

                grid_col = c if c < 4 else c + 1  # colonne 4 = separateur
                pads.addWidget(b, r, grid_col)
                self.pads[(r, c)] = b

            effect_btn = EffectButton(r)
            effect_btn.clicked.connect(lambda _, idx=r: self.toggle_effect(idx))
            self.effect_buttons.append(effect_btn)
            pads.addWidget(effect_btn, r, 9)

        pads.setColumnMinimumWidth(4, 8)  # espace entre col 4 et col 5
        layout.addLayout(pads)
        layout.addSpacing(10)

        # Faders
        fader_container = QHBoxLayout()
        fader_container.setSpacing(8)

        for i in range(8):
            col_layout = QVBoxLayout()
            col_layout.setSpacing(4)

            btn = FaderButton(i, self.toggle_mute)
            self.fader_buttons.append(btn)
            col_layout.addWidget(btn, alignment=Qt.AlignCenter)

            fader = ApcFader(i, self.set_proj_level, vertical=False)
            self.faders[i] = fader
            col_layout.addWidget(fader)

            fader_container.addLayout(col_layout)

            if i == 3:
                fader_container.addSpacing(8)  # separation visuelle col 4 / col 5

        # Fader effet
        effect_col = QVBoxLayout()
        effect_col.setSpacing(4)

        last_effect_btn = EffectButton(8)
        last_effect_btn.clicked.connect(lambda: self.toggle_effect(8))
        self.effect_buttons.append(last_effect_btn)
        effect_col.addWidget(last_effect_btn, alignment=Qt.AlignCenter)

        effect_fader = ApcFader(8, self.set_effect_speed, vertical=False)
        self.faders[8] = effect_fader
        effect_col.addWidget(effect_fader)

        fader_container.addLayout(effect_col)
        layout.addLayout(fader_container)

        # Cartoucheur
        layout.addSpacing(20)
        cart_label = QLabel("Cartoucheur")
        cart_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(cart_label)
        layout.addSpacing(6)

        self.cartouches = []
        for i in range(4):
            cart = CartoucheButton(i, self.on_cartouche_clicked)
            cart.customContextMenuRequested.connect(
                lambda pos, idx=i: self.load_cartouche_media(idx)
            )
            layout.addWidget(cart)
            self.cartouches.append(cart)

        layout.addStretch()

        # Banniere de licence supprimee

        return frame

    def create_transport_panel(self):
        """Cree le panneau transport avec timeline"""
        frame = QFrame()
        frame.setFixedHeight(150)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        # Timeline
        timeline_container = QHBoxLayout()

        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet("color: #00d4ff; font-weight: bold; font-size: 12px;")
        self.time_label.setFixedWidth(50)
        timeline_container.addWidget(self.time_label)

        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setFixedHeight(30)
        self.timeline.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #ffffff;
                height: 12px;
                border-radius: 6px;
                border: 1px solid #00d4ff;
            }
            QSlider::handle:horizontal {
                background: #00d4ff;
                width: 24px;
                height: 24px;
                margin: -6px 0;
                border-radius: 12px;
                border: 3px solid #ffffff;
            }
        """)
        self.player.durationChanged.connect(self.timeline.setMaximum)
        self.player.positionChanged.connect(self.on_timeline_update)
        self.timeline.sliderMoved.connect(self.player.setPosition)
        timeline_container.addWidget(self.timeline)

        self.remaining_label = QLabel("-00:00")
        self.remaining_label.setStyleSheet("color: #ff8800; font-weight: bold; font-size: 12px;")
        self.remaining_label.setFixedWidth(60)
        self.remaining_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        timeline_container.addWidget(self.remaining_label)

        layout.addLayout(timeline_container)

        # Waveform
        self.recording_waveform = RecordingWaveform()
        self.recording_waveform.setFixedHeight(30)
        self.recording_waveform.hide()
        layout.addWidget(self.recording_waveform)

        layout.addSpacing(8)

        # Boutons transport
        btns = QHBoxLayout()

        btn_style = """
            QToolButton {
                background: #4a4a4a;
                border: 2px solid #6a6a6a;
                border-radius: 8px;
                padding: 14px;
            }
            QToolButton:hover {
                background: #5a5a5a;
                border: 2px solid #00d4ff;
            }
        """

        prev = QToolButton()
        prev.setIcon(create_icon("prev", "#ffffff"))
        prev.setIconSize(QSize(40, 40))
        prev.setStyleSheet(btn_style)
        prev.clicked.connect(lambda: self.seq.play_row(self.seq.current_row - 1))

        self.play_btn = QToolButton()
        self.play_btn.setIcon(create_icon("play", "#ffffff"))
        self.play_btn.setIconSize(QSize(48, 48))
        self.play_btn.setStyleSheet(btn_style + "QToolButton { padding: 16px; }")
        self.play_btn.clicked.connect(self.toggle_play)

        nxt = QToolButton()
        nxt.setIcon(create_icon("next", "#ffffff"))
        nxt.setIconSize(QSize(40, 40))
        nxt.setStyleSheet(btn_style)
        nxt.clicked.connect(lambda: self.seq.play_row(self.seq.current_row + 1))

        btns.addStretch()
        btns.addWidget(prev)
        btns.addWidget(self.play_btn)
        btns.addWidget(nxt)
        btns.addStretch()
        layout.addLayout(btns)

        return frame

    def trigger_pause_mode(self):
        """Active le mode pause sans clignotement"""
        self.pause_mode = True
        self.player.pause()
        if self.blink_timer:
            self.blink_timer.stop()
            self.blink_timer = None

    def toggle_play(self):
        """Toggle play/pause - gere aussi les TEMPO"""
        # Pause d'un TEMPO en cours
        if self.seq.tempo_running:
            self.seq.tempo_running = False
            self.seq.tempo_paused = True
            self.seq.tempo_timer.stop()
            if self.seq.timeline_playback_timer and self.seq.timeline_playback_timer.isActive():
                self.seq.timeline_playback_timer.stop()
            self.play_btn.setIcon(create_icon("play", "#ffffff"))
            return

        # Reprise d'un TEMPO en pause
        if self.seq.tempo_paused:
            self.seq.tempo_running = True
            self.seq.tempo_paused = False
            self.seq.tempo_timer.start(100)
            if hasattr(self.seq, 'timeline_playback_row') and self.seq.timeline_playback_timer:
                self.seq.timeline_playback_timer.start(50)
            self.play_btn.setIcon(create_icon("pause", "#ffffff"))
            return

        # Lecture normale
        if self.pause_mode:
            if self.blink_timer:
                self.blink_timer.stop()
            self.pause_mode = False
            self.player.play()
        elif self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def update_play_icon(self, s):
        """Met a jour l'icone play/pause"""
        if s == QMediaPlayer.PlayingState:
            self.play_btn.setIcon(create_icon("pause", "#ffffff"))
        else:
            self.play_btn.setIcon(create_icon("play", "#ffffff"))

    def on_timeline_update(self, position):
        """Met a jour la timeline"""
        try:
            duration = self.player.duration()
            if duration > 0 and self.timeline.maximum() != duration:
                self.timeline.setMaximum(duration)
            if duration > 0:
                position = min(position, duration)
            self.timeline.setValue(position)
            self.time_label.setText(fmt_time(position))
            if duration > 0:
                remaining = duration - position
                self.remaining_label.setText(f"-{fmt_time(remaining)}")
            if self.seq.recording and self.recording_waveform.isVisible():
                self.recording_waveform.set_position(position, duration)
        except:
            pass

    def on_media_status_changed(self, status):
        """Passe automatiquement au suivant ou gere les pauses"""
        if status == QMediaPlayer.EndOfMedia:
            if hasattr(self.seq, 'timeline_playback_timer') and self.seq.timeline_playback_timer and self.seq.timeline_playback_timer.isActive():
                self.seq.timeline_playback_timer.stop()

            if self.seq.recording:
                self.stop_recording()
                return

            # Reset IA Lumiere si le mode courant est IA
            current_mode = self.seq.get_dmx_mode(self.seq.current_row)
            if current_mode == "IA Lumiere":
                self.audio_ai.reset()

            next_row = self.seq.current_row + 1

            if next_row < self.seq.table.rowCount():
                next_mode = self.seq.get_dmx_mode(next_row)
                if (current_mode in ["IA Lumiere", "Programme"]) and next_mode == "Manuel":
                    self.full_blackout()

                self.seq.play_row(next_row)
            else:
                print("Fin de la sequence")
                self.update_play_icon(QMediaPlayer.StoppedState)
                self._update_video_output_state()

    def dmx_blackout(self):
        """Blackout DMX uniquement (projecteurs) - conserve l'eclairage AKAI"""
        for idx in range(9):
            if idx in self.faders:
                self.faders[idx].value = 0
                self.faders[idx].update()

        for p in self.projectors:
            p.level = 0
            p.color = QColor("black")

    def full_blackout(self):
        """Blackout complet"""
        # Vider les overrides HTP
        if hasattr(self, 'plan_de_feu'):
            self.plan_de_feu.set_htp_overrides(None)

        for idx in range(9):
            if idx in self.faders:
                self.faders[idx].value = 0
                self.faders[idx].update()

        for p in self.projectors:
            p.level = 0
            p.color = QColor("black")

        for col, pad in self.active_pads.items():
            if pad:
                old_color = pad.property("base_color")
                dim_color = QColor(int(old_color.red() * 0.5), int(old_color.green() * 0.5), int(old_color.blue() * 0.5))
                pad.setStyleSheet(f"QPushButton {{ background: {dim_color.name()}; border: 1px solid #2a2a2a; border-radius: 4px; }}")
        self.active_pads = {}

        for btn in self.effect_buttons:
            if btn.active:
                btn.active = False
                btn.update_style()

        if self.active_effect is not None:
            self.stop_effect()
            self.active_effect = None

        if MIDI_AVAILABLE and self.midi_handler.midi_out:
            for row in range(8):
                for col in range(8):
                    self.midi_handler.set_pad_led(row, col, 0, 0)

    def activate_pad(self, btn, col_idx):
        """Active un pad dans sa colonne (independant par colonne)"""
        color = btn.property("base_color")
        groups = {0: ["face"], 1: ["contre", "lat"], 2: ["douche1", "douche2", "douche3"], 3: ["public"]}
        target_groups = groups.get(col_idx, [])

        # Desactiver l'ancien pad de CETTE colonne uniquement
        prev = self.active_pads.get(col_idx)
        if prev and prev != btn:
            old_color = prev.property("base_color")
            dim_color = QColor(int(old_color.red() * 0.5), int(old_color.green() * 0.5), int(old_color.blue() * 0.5))
            prev.setStyleSheet(f"QPushButton {{ background: {dim_color.name()}; border: 1px solid #2a2a2a; border-radius: 4px; }}")

        btn.setStyleSheet(f"QPushButton {{ background: {color.name()}; border: 2px solid {color.lighter(130).name()}; border-radius: 4px; }}")
        self.active_pads[col_idx] = btn

        # Appliquer la couleur seulement si le fader de cette colonne est leve
        fader_value = self.faders[col_idx].value if col_idx in self.faders else 0
        for p in self.projectors:
            if p.group in target_groups:
                p.base_color = color
                if fader_value > 0:
                    brightness = fader_value / 100.0
                    p.color = QColor(
                        int(color.red() * brightness),
                        int(color.green() * brightness),
                        int(color.blue() * brightness)
                    )

    def activate_pad_dual(self, btn, col_idx):
        """Active un pad bicolore"""
        color1 = btn.property("base_color")
        color2 = btn.property("color2")

        if self.active_dual_pad and self.active_dual_pad != btn:
            self.active_dual_pad.active = False
            self.active_dual_pad.brightness = 0.3
            self.active_dual_pad.update()

        btn.active = not btn.active
        if btn.active:
            btn.brightness = 1.0
            self.active_dual_pad = btn
        else:
            btn.brightness = 0.3
            self.active_dual_pad = None
        btn.update()

        if btn.active:
            patterns = {
                "lat": [color1, color1],
                "contre": [color2, color1, color2, color2, color1, color2]
            }

            for group, pattern in patterns.items():
                projs = [p for p in self.projectors if p.group == group]
                for i, p in enumerate(projs):
                    if i < len(pattern):
                        p.base_color = pattern[i]
                        if p.level > 0:
                            brightness = p.level / 100.0
                            p.color = QColor(
                                int(pattern[i].red() * brightness),
                                int(pattern[i].green() * brightness),
                                int(pattern[i].blue() * brightness)
                            )

    def _activate_memory_pad(self, btn, mem_col, row):
        """Active un pad memoire - radio GLOBAL sur les 4 colonnes memoire.
        L'appui sur un pad desactive tous les autres pads actifs (toutes colonnes),
        puis active le nouveau. Cliquer sur le pad deja actif ne fait rien."""
        col_akai = 4 + mem_col

        # Clic sur le pad deja actif → rien
        if self.active_memory_pads.get(col_akai) == row:
            return

        # Activation impossible si aucune memoire stockee
        if self.memories[mem_col][row] is None:
            return

        # Desactiver TOUS les pads actifs sur les 4 colonnes memoire
        for mc in range(4):
            ca = 4 + mc
            prev_row = self.active_memory_pads.pop(ca, None)
            if prev_row is not None:
                self._clear_memory_from_projectors(mc, prev_row)
                self._style_memory_pad(mc, prev_row, active=False)
                self._update_memory_pad_led(mc, prev_row, active=False)

        # Activer le nouveau pad
        self.active_memory_pads[col_akai] = row
        self._style_memory_pad(mem_col, row, active=True)
        self._update_memory_pad_led(mem_col, row, active=True)
        self._apply_memory_to_projectors(mem_col, row)
        self._save_akai_config_auto()

    def _clear_memory_from_projectors(self, mem_col, row):
        """Remet a zero les projecteurs actifs (level > 0) d'une memoire."""
        mem = self.memories[mem_col][row]
        if not mem:
            return
        for i, proj_state in enumerate(mem["projectors"]):
            if i >= len(self.projectors):
                break
            if proj_state["level"] > 0:
                p = self.projectors[i]
                p.level = 0
                p.color = QColor("black")

    def _apply_memory_to_projectors(self, mem_col, row):
        """Applique directement une memoire sur les projecteurs.
        Seuls les projecteurs avec level > 0 dans le snapshot sont modifies,
        ce qui preserves les faders couleur (0-3) independants.
        L'ecriture directe de p.level permet aux effets de detecter ces projecteurs."""
        mem = self.memories[mem_col][row]
        if not mem:
            return
        col_akai = 4 + mem_col
        fader_value = self.faders[col_akai].value if col_akai in self.faders else 100
        brightness = fader_value / 100.0
        for i, proj_state in enumerate(mem["projectors"]):
            if i >= len(self.projectors):
                break
            if proj_state["level"] <= 0:
                continue
            p = self.projectors[i]
            level = int(proj_state["level"] * brightness)
            base_color = QColor(proj_state["base_color"])
            p.level = level
            p.base_color = base_color
            p.color = QColor(
                int(base_color.red() * level / 100.0),
                int(base_color.green() * level / 100.0),
                int(base_color.blue() * level / 100.0)
            )

    def _style_memory_pad(self, mem_col, row, active):
        """Style visuel d'un pad memoire"""
        col_akai = 4 + mem_col
        pad = self.pads.get((row, col_akai))
        if not pad:
            return

        color = self._get_memory_pad_color(mem_col, row)
        if color == QColor("black") or self.memories[mem_col][row] is None:
            pad.setStyleSheet("""
                QPushButton {
                    background: #1a1a1a;
                    border: 1px solid #1a1a1a;
                    border-radius: 4px;
                }
            """)
        elif active:
            pad.setStyleSheet(f"""
                QPushButton {{
                    background: {color.name()};
                    border: 2px solid {color.lighter(130).name()};
                    border-radius: 4px;
                }}
            """)
        else:
            dim_color = QColor(int(color.red() * 0.5), int(color.green() * 0.5), int(color.blue() * 0.5))
            pad.setStyleSheet(f"""
                QPushButton {{
                    background: {dim_color.name()};
                    border: 1px solid #2a2a2a;
                    border-radius: 4px;
                }}
            """)

    def _get_memory_pad_color(self, mem_col, row):
        """Retourne la couleur custom ou dominante du snapshot"""
        custom = self.memory_custom_colors[mem_col][row]
        if custom:
            return custom

        mem = self.memories[mem_col][row]
        if not mem:
            return QColor("black")
        color_counts = {}
        for ms in mem["projectors"]:
            if ms["level"] > 0:
                c = ms["base_color"]
                color_counts[c] = color_counts.get(c, 0) + 1
        if not color_counts:
            return QColor("black")
        dominant = max(color_counts, key=color_counts.get)
        return QColor(dominant)

    def _update_memory_pad_led(self, mem_col, row, active):
        """Envoie LED MIDI pour un pad memoire"""
        if not (MIDI_AVAILABLE and hasattr(self, 'midi_handler') and self.midi_handler.midi_out):
            return
        col_akai = 4 + mem_col
        note = (7 - row) * 8 + col_akai
        color = self._get_memory_pad_color(mem_col, row)
        if self.memories[mem_col][row] is None or color == QColor("black"):
            self.midi_handler.midi_out.send_message([0x90, note, 0])
        else:
            velocity = rgb_to_akai_velocity(color)
            channel = 0x96 if active else 0x90
            self.midi_handler.midi_out.send_message([channel, note, velocity])

    def _set_memory_custom_color(self, mem_col, row, color):
        """Definit une couleur personnalisee pour un pad memoire"""
        self.memory_custom_colors[mem_col][row] = color
        col_akai = 4 + mem_col
        is_active = self.active_memory_pads.get(col_akai) == row
        self._style_memory_pad(mem_col, row, active=is_active)
        self._update_memory_pad_led(mem_col, row, active=is_active)
        # Sauvegarde auto immediate
        self._save_akai_config_auto()

    def _record_memory(self, mem_col, row):
        """Capture l'etat visuel complet (projecteurs + HTP memoires) dans une memoire"""
        overrides = self._compute_htp_overrides()
        snapshot = []
        for p in self.projectors:
            if overrides and id(p) in overrides:
                level, color, base = overrides[id(p)]
                snapshot.append({
                    "group": p.group,
                    "base_color": base.name(),
                    "level": level
                })
            else:
                snapshot.append({
                    "group": p.group,
                    "base_color": p.base_color.name(),
                    "level": p.level
                })
        self.memories[mem_col][row] = {"projectors": snapshot}
        col_akai = 4 + mem_col
        is_active = self.active_memory_pads.get(col_akai) == row
        self._style_memory_pad(mem_col, row, active=is_active)
        self._update_memory_pad_led(mem_col, row, active=is_active)
        # Sauvegarde auto immediate
        self._save_akai_config_auto()

    def _show_memory_context_menu(self, pos, mem_col, row, btn):
        """Menu contextuel sur un pad memoire"""
        menu_style = """
            QMenu {
                background: #1e1e1e; color: white;
                border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;
            }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #3a3a3a; }
        """
        menu = QMenu(self)
        menu.setStyleSheet(menu_style)

        if self.memories[mem_col][row] is None:
            save_action = menu.addAction("Sauvegarder")
            save_action.triggered.connect(lambda: self._record_memory(mem_col, row))
        else:
            replace_action = menu.addAction("Remplacer")
            replace_action.triggered.connect(lambda: self._record_memory(mem_col, row))
            clear_action = menu.addAction("Effacer")
            clear_action.triggered.connect(lambda: self._clear_memory(mem_col, row))
            menu.addSeparator()

            # Sous-menu couleur du pad
            color_menu = menu.addMenu("Couleur du pad")
            color_menu.setStyleSheet(menu_style)

            auto_action = color_menu.addAction("Auto (dominante)")
            auto_action.triggered.connect(lambda: self._set_memory_custom_color(mem_col, row, None))

            pad_colors = [
                ("Blanc", QColor(255, 255, 255)),
                ("Rouge", QColor(255, 0, 0)),
                ("Orange", QColor(255, 136, 0)),
                ("Jaune", QColor(255, 221, 0)),
                ("Vert", QColor(0, 255, 0)),
                ("Cyan", QColor(0, 221, 221)),
                ("Bleu", QColor(0, 0, 255)),
                ("Magenta", QColor(255, 0, 255)),
            ]
            for name, col in pad_colors:
                px = QPixmap(16, 16)
                px.fill(col)
                action = color_menu.addAction(QIcon(px), name)
                action.triggered.connect(lambda _, c=col: self._set_memory_custom_color(mem_col, row, c))

        menu.exec(btn.mapToGlobal(pos))

    def _clear_memory(self, mem_col, row):
        """Efface une memoire individuelle"""
        self.memories[mem_col][row] = None
        self.memory_custom_colors[mem_col][row] = None
        col_akai = 4 + mem_col
        if self.active_memory_pads.get(col_akai) == row:
            del self.active_memory_pads[col_akai]
        self._style_memory_pad(mem_col, row, active=False)
        self._update_memory_pad_led(mem_col, row, active=False)
        # Sauvegarde auto immediate
        self._save_akai_config_auto()

    def set_proj_level(self, index, value):
        """Gere les faders - chaque fader est independant"""
        if index in (4, 5, 6, 7):
            # Faders 4-7: memoires - re-appliquer la memoire active avec la nouvelle intensite
            mem_col = index - 4
            active_row = self.active_memory_pads.get(index)
            if active_row is not None and self.memories[mem_col][active_row]:
                self._apply_memory_to_projectors(mem_col, active_row)
            return

        groups = self.FADER_GROUPS.get(index)
        if not groups:
            return

        # Auto-activation pad blanc si aucun pad actif dans CETTE colonne
        if index not in self.active_pads and value > 0 and index <= 3:
            white_pad = self.pads.get((0, index))
            if white_pad:
                color = white_pad.property("base_color")
                white_pad.setStyleSheet(f"QPushButton {{ background: {color.name()}; border: 2px solid {color.lighter(130).name()}; border-radius: 4px; }}")
                self.active_pads[index] = white_pad
                for p in self.projectors:
                    if p.group in groups:
                        p.base_color = color
        elif index in self.active_pads and value > 0 and index <= 3:
            # Resync base_color sur tous les projecteurs du groupe avec la couleur du pad actif
            # (une mémoire HTP peut avoir changé base_color d'un projecteur individuellement)
            active_color = self.active_pads[index].property("base_color")
            for p in self.projectors:
                if p.group in groups:
                    p.base_color = active_color

        brightness = value / 100.0 if value > 0 else 0
        for p in self.projectors:
            if p.group in groups:
                p.level = value
                if value > 0:
                    p.color = QColor(
                        int(p.base_color.red() * brightness),
                        int(p.base_color.green() * brightness),
                        int(p.base_color.blue() * brightness))
                else:
                    p.color = QColor("black")

    def toggle_mute(self, index, active):
        """Gere les mutes - chaque fader est independant"""
        if index in (4, 5, 6, 7):
            # Faders memoire : muter les projecteurs actifs du snapshot courant
            mem_col = index - 4
            active_row = self.active_memory_pads.get(index)
            if active_row is None or not self.memories[mem_col][active_row]:
                return
            mem = self.memories[mem_col][active_row]
            for i, proj_state in enumerate(mem["projectors"]):
                if i >= len(self.projectors):
                    break
                if proj_state["level"] > 0:
                    self.projectors[i].muted = active
            return

        groups = self.FADER_GROUPS.get(index)
        if not groups:
            return
        for p in self.projectors:
            if p.group in groups:
                p.muted = active

    def toggle_effect(self, effect_idx):
        """Active/desactive un effet"""
        btn = self.effect_buttons[effect_idx]
        btn.active = not btn.active
        if btn.active:
            effect_name = btn.current_effect
            if not effect_name:
                btn.active = False
                btn.update_style()
                return
            self.active_effect = effect_name
            self.start_effect(effect_name)
            for j, other_btn in enumerate(self.effect_buttons):
                if j != effect_idx and other_btn.active:
                    other_btn.active = False
                    other_btn.update_style()
                    if MIDI_AVAILABLE and self.midi_handler.midi_out:
                        self.midi_handler.set_pad_led(j, 8, 0)
        else:
            self.active_effect = None
            self.stop_effect()
        btn.update_style()
        # Mise a jour LED AKAI (utile quand l'effet est toggle depuis l'UI)
        if MIDI_AVAILABLE and self.midi_handler.midi_out and effect_idx < 8:
            velocity = 1 if btn.active else 0
            self.midi_handler.set_pad_led(effect_idx, 8, velocity, brightness_percent=100)

    def start_effect(self, effect_name):
        """Demarre l'effet selectionne par nom"""
        self.effect_state = 0
        self.effect_saved_colors = {}

        for p in self.projectors:
            self.effect_saved_colors[id(p)] = (p.base_color, p.color)

        if not hasattr(self, 'effect_timer'):
            self.effect_timer = QTimer()
            self.effect_timer.timeout.connect(self.update_effect)

        intervals = {
            "Strobe": 100, "Flash": 100, "Pulse": 30,
            "Wave": 50, "Random": 200, "Rainbow": 50,
            "Sparkle": 80, "Fire": 60,
        }
        self.effect_timer.start(intervals.get(effect_name, 100))

        if effect_name in ("Rainbow", "Wave"):
            self.effect_hue = 0
        elif effect_name == "Pulse":
            self.effect_brightness = 0
            self.effect_direction = 1

    def stop_effect(self):
        """Arrete l'effet en cours"""
        if hasattr(self, 'effect_timer'):
            self.effect_timer.stop()

        for p in self.projectors:
            p.dmx_mode = "Manuel"

        for p in self.projectors:
            if id(p) in self.effect_saved_colors:
                base_color, color = self.effect_saved_colors[id(p)]
                p.base_color = base_color
                p.color = color

    def update_effect(self):
        """Met a jour l'effet en cours"""
        if self.active_effect is None:
            return

        if self.effect_speed == 0:
            speed_factor = 1.0
        else:
            speed_factor = max(0.05, 1.0 - (self.effect_speed / 100.0 * 0.95))

        eff = self.active_effect

        if eff == "Strobe":
            # Alternance blanc/noir sur tous les projos
            self.effect_timer.setInterval(int(100 * speed_factor))
            for p in self.projectors:
                if p.group == "fumee":
                    continue
                if p.level > 0:
                    p.color = QColor(255, 255, 255) if self.effect_state % 2 == 0 else QColor("black")
            self.effect_state += 1

        elif eff == "Flash":
            # Alternance couleur/noir
            self.effect_timer.setInterval(int(100 * speed_factor))
            for p in self.projectors:
                if p.group == "fumee":
                    continue
                if p.level > 0:
                    if self.effect_state % 2 == 0:
                        brightness = p.level / 100.0
                        p.color = QColor(
                            int(p.base_color.red() * brightness),
                            int(p.base_color.green() * brightness),
                            int(p.base_color.blue() * brightness)
                        )
                    else:
                        p.color = QColor("black")
            self.effect_state += 1

        elif eff == "Pulse":
            # Respiration douce (fade in/out)
            for p in self.projectors:
                if p.group == "fumee":
                    continue
                if p.level > 0:
                    brightness = (p.level / 127.0) * (self.effect_brightness / 100.0)
                    p.color = QColor(
                        int(p.base_color.red() * brightness),
                        int(p.base_color.green() * brightness),
                        int(p.base_color.blue() * brightness)
                    )
            speed = 2 + int(self.effect_speed / 20)
            self.effect_brightness += self.effect_direction * speed
            if self.effect_brightness >= 100:
                self.effect_brightness = 100
                self.effect_direction = -1
            elif self.effect_brightness <= 0:
                self.effect_brightness = 0
                self.effect_direction = 1

        elif eff == "Wave":
            # Vague de couleur qui se deplace d'un projo a l'autre
            self.effect_timer.setInterval(int(50 * speed_factor))
            for i, p in enumerate(self.projectors):
                if p.group == "fumee":
                    continue
                if p.level > 0:
                    phase = (self.effect_state + i * 15) % 100
                    brightness = (p.level / 100.0) * (abs(50 - phase) / 50.0)
                    p.color = QColor(
                        int(p.base_color.red() * brightness),
                        int(p.base_color.green() * brightness),
                        int(p.base_color.blue() * brightness)
                    )
            self.effect_state += 3 + int(self.effect_speed / 25)

        elif eff == "Random":
            # Couleurs aleatoires sur chaque projo
            self.effect_timer.setInterval(int(200 * speed_factor))
            for p in self.projectors:
                if p.group == "fumee":
                    continue
                if p.level > 0:
                    p.color = QColor.fromHsv(random.randint(0, 359), 255, int(p.level * 2.55))
            self.effect_state += 1

        elif eff == "Rainbow":
            # Rotation arc-en-ciel sur tous les projos
            for i, p in enumerate(self.projectors):
                if p.group == "fumee":
                    continue
                if p.level > 0:
                    hue = (self.effect_hue + i * 30) % 360
                    color = QColor.fromHsv(hue, 255, 255)
                    brightness = p.level / 100.0
                    p.color = QColor(
                        int(color.red() * brightness),
                        int(color.green() * brightness),
                        int(color.blue() * brightness)
                    )
            self.effect_hue += int(5 * (1 + self.effect_speed / 30))

        elif eff == "Sparkle":
            # Scintillement aleatoire (certains projos flash blanc)
            self.effect_timer.setInterval(int(80 * speed_factor))
            for p in self.projectors:
                if p.group == "fumee":
                    continue
                if p.level > 0:
                    if random.random() < 0.3:
                        p.color = QColor(255, 255, 255)
                    else:
                        brightness = p.level / 100.0
                        p.color = QColor(
                            int(p.base_color.red() * brightness),
                            int(p.base_color.green() * brightness),
                            int(p.base_color.blue() * brightness)
                        )

        elif eff == "Fire":
            # Effet feu (rouge/orange/jaune aleatoire)
            self.effect_timer.setInterval(int(60 * speed_factor))
            fire_colors = [
                QColor(255, 50, 0), QColor(255, 100, 0), QColor(255, 150, 0),
                QColor(255, 200, 0), QColor(200, 30, 0), QColor(255, 80, 0),
            ]
            for p in self.projectors:
                if p.group == "fumee":
                    continue
                if p.level > 0:
                    base = random.choice(fire_colors)
                    brightness = p.level / 100.0
                    p.color = QColor(
                        int(base.red() * brightness),
                        int(base.green() * brightness),
                        int(base.blue() * brightness)
                    )

    def set_effect_speed(self, index, value):
        """Definit la vitesse de l'effet"""
        self.effect_speed = value

    def activate_default_white_pads(self):
        """Active les pads blancs au demarrage (cols 0-3) - un par colonne"""
        for col in range(4):
            white_pad = self.pads.get((0, col))
            if white_pad:
                color = white_pad.property("base_color")
                white_pad.setStyleSheet(f"QPushButton {{ background: {color.name()}; border: 2px solid {color.lighter(130).name()}; border-radius: 4px; }}")
                self.active_pads[col] = white_pad

        if MIDI_AVAILABLE and hasattr(self, 'midi_handler') and self.midi_handler.midi_out:
            for row in range(8):
                for col in range(8):
                    pad = self.pads.get((row, col))
                    if pad:
                        if col < 4:
                            base_color = pad.property("base_color")
                            velocity = rgb_to_akai_velocity(base_color)
                            brightness = 100 if row == 0 else 20
                            note = (7 - row) * 8 + col
                            channel = 0x96 if brightness >= 80 else 0x90
                            self.midi_handler.midi_out.send_message([channel, note, velocity])
                        else:
                            # Cols 4-7: memoires individuelles
                            mem_col = col - 4
                            col_akai = col
                            is_active = self.active_memory_pads.get(col_akai) == row
                            self._update_memory_pad_led(mem_col, row, active=is_active)

    def turn_off_all_effects(self):
        """Eteint tous les effets au demarrage"""
        for btn in self.effect_buttons:
            btn.active = False
            btn.update_style()

        if MIDI_AVAILABLE and hasattr(self, 'midi_handler') and self.midi_handler.midi_out:
            for i in range(8):
                note = 112 + i
                self.midi_handler.midi_out.send_message([0x90, note, 0])

    def show_ia_color_dialog(self):
        """Dialogue de selection de couleur dominante pour IA Lumiere"""
        dialog = QDialog(self)
        dialog.setWindowTitle("IA Lumiere")
        dialog.setFixedSize(420, 220)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: white; border: none; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(12)

        title = QLabel("Choisissez la couleur dominante")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        colors_layout = QGridLayout()
        colors_layout.setSpacing(8)

        colors = [
            ("Rouge", QColor("#ff0000")),
            ("Bleu", QColor("#0066ff")),
            ("Vert", QColor("#00ff00")),
            ("Jaune", QColor("#ffdd00")),
            ("Violet", QColor("#aa00ff")),
            ("Orange", QColor("#ff8800")),
            ("Cyan", QColor("#00ddff")),
            ("Rose", QColor("#ff00aa")),
        ]

        selected_color = [None]

        for i, (name, color) in enumerate(colors):
            btn = QPushButton(name)
            btn.setFixedSize(90, 50)
            text_color = "black" if color.lightness() > 128 else "white"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color.name()};
                    color: {text_color};
                    border: 2px solid #3a3a3a;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 12px;
                }}
                QPushButton:hover {{ border: 3px solid white; }}
            """)
            btn.clicked.connect(lambda _, c=color: (selected_color.__setitem__(0, c), dialog.accept()))
            colors_layout.addWidget(btn, i // 4, i % 4)

        layout.addLayout(colors_layout)

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a; color: white; border: none;
                border-radius: 6px; padding: 8px 20px;
            }
            QPushButton:hover { background: #4a4a4a; }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(cancel_btn, alignment=Qt.AlignCenter)

        if dialog.exec() == QDialog.Accepted:
            return selected_color[0]
        return None

    def update_audio_ai(self):
        """IA Lumiere - Met a jour les projecteurs selon l'analyse audio avec effets creatifs"""
        try:
            if self.seq.current_row < 0:
                return
            dmx_mode = self.seq.get_dmx_mode(self.seq.current_row)
            if dmx_mode != "IA Lumiere":
                return
            if self.player.playbackState() != QMediaPlayer.PlayingState:
                return
            if not self.audio_ai.analyzed:
                return

            import math

            position = self.player.position()
            duration = self.player.duration()

            state = self.audio_ai.get_state_at(position, duration, max_dimmers=self.ia_max_dimmers)

            contre_alt = state.get('contre_alt')
            lat_alt = state.get('lat_alt')
            contre_effect = state.get('contre_effect')
            lat_effect = state.get('lat_effect')

            # Compteurs par groupe pour alterner les couleurs
            contre_idx = 0
            lat_idx = 0

            for p in self.projectors:
                if p.group not in state:
                    continue
                color, level = state[p.group]

                # Effets creatifs sur contres
                if p.group == 'contre':
                    # Couleur alternee bicolore (1 sur 2)
                    if contre_alt and contre_idx % 2 == 1:
                        color = contre_alt
                    contre_idx += 1

                # Effets creatifs sur lateraux
                elif p.group == 'lat':
                    # Couleur alternee bicolore (1 sur 2)
                    if lat_alt and lat_idx % 2 == 1:
                        color = lat_alt
                    # Strobe: alterner on/off
                    if lat_effect == "strobe":
                        strobe_on = (int(position / 80) % 2) == 0
                        if not strobe_on:
                            level = 0
                    lat_idx += 1

                p.level = level
                p.base_color = color
                if level > 0:
                    brightness = level / 100.0
                    p.color = QColor(
                        int(color.red() * brightness),
                        int(color.green() * brightness),
                        int(color.blue() * brightness)
                    )
                else:
                    p.color = QColor("black")

            if hasattr(self, 'plan_de_feu'):
                self.plan_de_feu.update()

        except Exception as e:
            print(f"Erreur IA Lumiere: {e}")

    def play_path(self, path):
        """Joue un fichier media"""
        self._stop_all_cartouches()
        try:
            self.player.setSource(QUrl.fromLocalFile(path))
            try:
                self.player.durationChanged.disconnect()
            except:
                pass
            row = self.seq.current_row
            self.player.durationChanged.connect(lambda d: self.update_duration_display(d, row))
            self.player.play()
            self._update_video_output_state()
        except Exception as e:
            print(f"Erreur play: {e}")

    def update_duration_display(self, duration_ms, row):
        """Met a jour l'affichage de la duree"""
        if row >= 0 and duration_ms > 0:
            minutes = duration_ms // 60000
            seconds = (duration_ms % 60000) // 1000
            dur_text = f"{minutes:02d}:{seconds:02d}"
            dur_item = self.seq.table.item(row, 2)
            if dur_item:
                dur_item.setText(dur_text)

    def on_midi_fader(self, fader_idx, value):
        """Reception d'un mouvement de fader MIDI"""
        converted_value = int((value / 127.0) * 100)

        if fader_idx == 8:
            self.set_effect_speed(fader_idx, converted_value)
            if fader_idx in self.faders:
                self.faders[fader_idx].value = converted_value
                self.faders[fader_idx].update()
        elif 0 <= fader_idx <= 7:
            self.set_proj_level(fader_idx, converted_value)
            if fader_idx in self.faders:
                self.faders[fader_idx].value = converted_value
                self.faders[fader_idx].update()

    def on_midi_pad(self, row, col):
        """Reception d'un appui de pad MIDI"""
        if col == 8:
            self.toggle_effect(row)
            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                velocity = 1 if self.effect_buttons[row].active else 0
                self.midi_handler.set_pad_led(row, col, velocity, brightness_percent=100)
            return

        pad = self.pads.get((row, col))
        if pad:
            if col < 4:
                # Pads couleur standard
                for r in range(8):
                    if r != row:
                        other_pad = self.pads.get((r, col))
                        if other_pad:
                            other_color = other_pad.property("base_color")
                            other_velocity = rgb_to_akai_velocity(other_color)
                            self.midi_handler.set_pad_led(r, col, other_velocity, brightness_percent=20)

                self.activate_pad(pad, col)
                if MIDI_AVAILABLE and self.midi_handler.midi_out:
                    base_color = pad.property("base_color")
                    velocity = rgb_to_akai_velocity(base_color)
                    self.midi_handler.set_pad_led(row, col, velocity, brightness_percent=100)
            elif col in (4, 5, 6, 7):
                # Memory pads individuels
                mem_col = col - 4
                if self.memories[mem_col][row] is not None:
                    self._activate_memory_pad(pad, mem_col, row)
                    # Update LEDs de toute la colonne
                    for r in range(8):
                        is_active = self.active_memory_pads.get(col) == r
                        self._update_memory_pad_led(mem_col, r, active=is_active)

    def new_show(self):
        """Cree un nouveau show"""
        self.clear_sequence()

    def clear_sequence(self):
        """Vide le sequenceur"""
        if self.seq.table.rowCount() == 0:
            QMessageBox.information(self, "Programme vide", "La sequence est deja vide.")
            return

        if self.seq.is_dirty:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Vider la sequence")
            msg.setText("Voulez-vous sauvegarder avant de vider ?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            res = msg.exec()

            if res == QMessageBox.Yes:
                if not self.save_show():
                    return
            elif res == QMessageBox.Cancel:
                return
        else:
            res = QMessageBox.question(self, "Vider la sequence",
                "Voulez-vous vraiment supprimer tous les medias ?",
                QMessageBox.Yes | QMessageBox.No)
            if res == QMessageBox.No:
                return

        self.seq.clear_sequence()
        self.current_show_path = None
        self.setWindowTitle(APP_NAME)

    def save_show(self):
        """Sauvegarde le show (ecrase si deja ouvert, sinon demande le chemin)"""
        # Utiliser le chemin existant ou demander un nouveau
        if self.current_show_path:
            path = self.current_show_path
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Sauvegarder Show", "", "TUI Show (*.tui)")
            if not path:
                return False

        data = []
        for r in range(self.seq.table.rowCount()):
            path_item = self.seq.table.item(r, 1)
            vol_item = self.seq.table.item(r, 3)

            user_data = str(path_item.data(Qt.UserRole)) if path_item else ""

            if user_data == "PAUSE":
                # Pause indefinie
                pause_entry = {'type': 'pause'}
                dmx_mode = self.seq.get_dmx_mode(r)
                pause_entry['d'] = dmx_mode
                if r in self.seq.sequences:
                    sequence = self.seq.sequences[r]
                    if 'clips' in sequence:
                        pause_entry['sequence'] = {
                            'clips': sequence['clips'],
                            'duration': sequence['duration']
                        }
                data.append(pause_entry)
            elif user_data.startswith("PAUSE:"):
                # Pause temporisee
                seconds = int(user_data.split(":")[1])
                dmx_mode = self.seq.get_dmx_mode(r)
                pause_entry = {'type': 'pause', 'duration': seconds, 'd': dmx_mode}
                if r in self.seq.sequences:
                    sequence = self.seq.sequences[r]
                    if 'clips' in sequence:
                        pause_entry['sequence'] = {
                            'clips': sequence['clips'],
                            'duration': sequence['duration']
                        }
                data.append(pause_entry)
            else:
                dmx_mode = self.seq.get_dmx_mode(r)
                if path_item and vol_item:
                    row_data = {
                        'type': 'media',
                        'p': path_item.data(Qt.UserRole),
                        'v': vol_item.text(),
                        'd': dmx_mode
                    }
                    if dmx_mode == "IA Lumiere" and r in self.seq.ia_colors:
                        row_data['ia_color'] = self.seq.ia_colors[r].name()
                    if r in self.seq.ia_analysis:
                        row_data['ia_analysis'] = self.seq.ia_analysis[r]
                    if r in self.seq.sequences:
                        sequence = self.seq.sequences[r]
                        # Gerer les deux formats: 'clips' (timeline) et 'keyframes' (ancien)
                        if 'clips' in sequence:
                            row_data['sequence'] = {
                                'clips': sequence['clips'],
                                'duration': sequence['duration']
                            }
                        elif 'keyframes' in sequence:
                            row_data['sequence'] = {
                                'keyframes': sequence['keyframes'],
                                'duration': sequence['duration']
                            }
                    if r in self.seq.image_durations:
                        row_data['image_duration'] = self.seq.image_durations[r]
                    data.append(row_data)

        # Cartouches
        cart_data = []
        for cart in self.cartouches:
            cart_data.append({"path": cart.media_path, "volume": cart.volume})

        # Serialiser les couleurs custom (QColor -> str ou None)
        custom_colors_serial = []
        for mc in range(4):
            col_colors = []
            for mr in range(8):
                c = self.memory_custom_colors[mc][mr]
                col_colors.append(c.name() if c else None)
            custom_colors_serial.append(col_colors)

        # Serialiser les pads actifs {col_akai_str: row}
        active_pads_serial = {str(k): v for k, v in self.active_memory_pads.items()}

        # Sauvegarder l'etat complet du plan de feu (avec HTP applique)
        overrides = self._compute_htp_overrides()
        plan_de_feu_state = []
        for proj in self.projectors:
            # Utiliser l'override HTP si present, sinon l'etat direct
            if overrides and id(proj) in overrides:
                level, color, base = overrides[id(proj)]
                plan_de_feu_state.append({
                    "group": proj.group,
                    "level": level,
                    "base_color": base.name(),
                    "muted": proj.muted
                })
            else:
                plan_de_feu_state.append({
                    "group": proj.group,
                    "level": proj.level,
                    "base_color": proj.base_color.name(),
                    "muted": proj.muted
                })

        # Sauvegarder l'etat des faders
        faders_state = {}
        for idx, fader in self.faders.items():
            faders_state[str(idx)] = fader.value

        # Sauvegarder les pads couleur actifs (colonnes 0-3)
        active_color_pads = {}
        for col_idx, btn in self.active_pads.items():
            base_color = btn.property("base_color")
            if base_color:
                active_color_pads[str(col_idx)] = base_color.name()

        save_data = {
            "version": 5,
            "sequence": data,
            "cartouches": cart_data,
            "memories": self.memories,
            "memory_custom_colors": custom_colors_serial,
            "active_memory_pads": active_pads_serial,
            "plan_de_feu": plan_de_feu_state,
            "faders": faders_state,
            "active_color_pads": active_color_pads
        }

        try:
            with open(path, 'w') as f:
                json.dump(save_data, f, indent=2)
            self.seq.is_dirty = False
            self.current_show_path = path
            self.add_recent_file(path)
            self.setWindowTitle(f"{APP_NAME} - {os.path.basename(path)}")
            # Clear total apres sauvegarde
            self.full_blackout()
            self.plan_de_feu.refresh()
            return True
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder: {e}")
            return False

    def save_show_as(self):
        """Sauvegarde le show sous un nouveau nom"""
        old_path = self.current_show_path
        self.current_show_path = None  # Force le dialogue
        if not self.save_show():
            self.current_show_path = old_path  # Restaurer si annule
            return False
        return True

    def load_show(self, path=None):
        """Charge un show"""
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Ouvrir Show", "", "TUI Show (*.tui)")
        if not path:
            return

        try:
            with open(path, 'r') as f:
                raw = json.load(f)

            # Retrocompatibilite: ancien format = tableau, nouveau = objet
            if isinstance(raw, list):
                data = raw
                cart_data = []
                mem_data = None
                custom_colors_data = None
                active_pads_data = None
            else:
                data = raw.get("sequence", [])
                cart_data = raw.get("cartouches", [])
                mem_data = raw.get("memories")
                custom_colors_data = raw.get("memory_custom_colors")
                active_pads_data = raw.get("active_memory_pads")

            self.seq.table.setRowCount(0)
            self.seq.sequences = {}
            self.seq.ia_colors = {}
            self.seq.ia_analysis = {}
            self.seq.image_durations = {}
            self.seq._loading = True

            try:
                for item in data:
                    item_type = item.get('type')

                    # PAUSE (indefinie ou temporisee) + retrocompat TEMPO
                    if item_type in ('pause', 'tempo'):
                        self.seq.add_pause()
                        row = self.seq.table.rowCount() - 1

                        # Determiner la duree
                        duration_val = item.get('duration')
                        if duration_val is not None:
                            pause_seconds = int(duration_val)
                            pause_item = self.seq.table.item(row, 1)
                            if pause_item:
                                pause_item.setData(Qt.UserRole, f"PAUSE:{pause_seconds}")
                                minutes = pause_seconds // 60
                                seconds = pause_seconds % 60
                                pause_item.setText(f"Pause ({minutes}m {seconds}s)" if minutes > 0 else f"Pause ({pause_seconds}s)")
                            dur_item = self.seq.table.item(row, 2)
                            if dur_item:
                                minutes = pause_seconds // 60
                                seconds = pause_seconds % 60
                                dur_item.setText(f"{minutes:02d}:{seconds:02d}")

                        # Charger le mode DMX
                        if 'd' in item:
                            combo = self.seq._get_dmx_combo(row)
                            if combo:
                                if item['d'] == "Play Lumiere" and combo.findText("Play Lumiere") == -1:
                                    combo.addItem("Play Lumiere")
                                combo.setCurrentText(item['d'])

                        # Charger la sequence lumiere
                        if 'sequence' in item:
                            seq_data = item['sequence']
                            if 'clips' in seq_data:
                                self.seq.sequences[row] = {
                                    'clips': seq_data['clips'],
                                    'duration': seq_data['duration']
                                }

                    else:
                        self.seq.add_files([item['p']])
                        row = self.seq.table.rowCount() - 1
                        vol_item = self.seq.table.item(row, 3)
                        if vol_item and vol_item.text() != "--":
                            vol_item.setText(item.get('v', '100'))
                        if 'd' in item:
                            # Restaurer la couleur IA avant d'appliquer le mode
                            if 'ia_color' in item:
                                self.seq.ia_colors[row] = QColor(item['ia_color'])
                            if 'ia_analysis' in item:
                                self.seq.ia_analysis[row] = item['ia_analysis']
                            combo = self.seq._get_dmx_combo(row)
                            if combo:
                                if item['d'] == "Play Lumiere" and combo.findText("Play Lumiere") == -1:
                                    combo.addItem("Play Lumiere")
                                combo.setCurrentText(item['d'])
                                self.seq.on_dmx_changed(row, item['d'])
                        if 'sequence' in item:
                            seq_data = item['sequence']
                            # Gerer les deux formats: 'clips' et 'keyframes'
                            if 'clips' in seq_data:
                                self.seq.sequences[row] = {
                                    'clips': seq_data['clips'],
                                    'duration': seq_data['duration']
                                }
                            elif 'keyframes' in seq_data:
                                self.seq.sequences[row] = {
                                    'keyframes': seq_data['keyframes'],
                                    'duration': seq_data['duration']
                                }
                        if 'image_duration' in item:
                            self.seq.image_durations[row] = int(item['image_duration'])
            finally:
                self.seq._loading = False

            # Restaurer les cartouches
            for i, cd in enumerate(cart_data):
                if i < len(self.cartouches):
                    self.cartouches[i].volume = cd.get("volume", 100)
                    if cd.get("path"):
                        p = cd["path"]
                        self.cartouches[i].media_path = p
                        self.cartouches[i].media_title = Path(p).stem
                        ext = Path(p).suffix.lower()
                        if ext in CartoucheButton.VIDEO_EXTS:
                            self.cartouches[i].media_icon = "\U0001f3ac"
                        elif ext in CartoucheButton.AUDIO_EXTS:
                            self.cartouches[i].media_icon = "\U0001f3b5"
                        else:
                            self.cartouches[i].media_icon = ""
                    self.cartouches[i].set_idle()

            # Restaurer les memoires (retrocompat ancien format 1D -> 2D, 3 cols -> 4 cols)
            self.memories = [[None]*8, [None]*8, [None]*8, [None]*8]
            self.memory_custom_colors = [[None]*8, [None]*8, [None]*8, [None]*8]
            self.active_memory_pads = {}

            if mem_data:
                if isinstance(mem_data, list) and len(mem_data) >= 1:
                    if isinstance(mem_data[0], list):
                        # Nouveau format 2D
                        for mc in range(min(4, len(mem_data))):
                            for mr in range(min(8, len(mem_data[mc]))):
                                self.memories[mc][mr] = mem_data[mc][mr]
                    else:
                        # Ancien format 1D: chaque memoire migree vers row 0
                        for mc in range(min(4, len(mem_data))):
                            if mem_data[mc]:
                                self.memories[mc][0] = mem_data[mc]

            if custom_colors_data and isinstance(custom_colors_data, list):
                for mc in range(min(4, len(custom_colors_data))):
                    for mr in range(min(8, len(custom_colors_data[mc]))):
                        c = custom_colors_data[mc][mr]
                        self.memory_custom_colors[mc][mr] = QColor(c) if c else None

            if active_pads_data and isinstance(active_pads_data, dict):
                for k, v in active_pads_data.items():
                    self.active_memory_pads[int(k)] = v

            # Mettre a jour l'affichage des pads memoire
            for mc in range(4):
                col_akai = 4 + mc
                for mr in range(8):
                    is_active = self.active_memory_pads.get(col_akai) == mr
                    self._style_memory_pad(mc, mr, active=is_active)

            # Restaurer l'etat du plan de feu (v5+)
            if isinstance(raw, dict):
                plan_de_feu_data = raw.get("plan_de_feu")
                faders_data = raw.get("faders")
                active_color_pads_data = raw.get("active_color_pads")

                # Restaurer les faders
                if faders_data and isinstance(faders_data, dict):
                    for idx_str, value in faders_data.items():
                        idx = int(idx_str)
                        if idx in self.faders:
                            self.faders[idx].value = int(value)
                            self.faders[idx].update()

                # Restaurer les pads couleur actifs (colonnes 0-3)
                if active_color_pads_data and isinstance(active_color_pads_data, dict):
                    for col_str, color_name in active_color_pads_data.items():
                        col_idx = int(col_str)
                        target_color = QColor(color_name)
                        # Chercher le pad qui correspond a cette couleur
                        for row in range(8):
                            pad = self.pads.get((row, col_idx))
                            if pad:
                                pad_color = pad.property("base_color")
                                if pad_color and pad_color.name() == target_color.name():
                                    self.activate_pad(pad, col_idx)
                                    break

                # Restaurer l'etat des projecteurs
                if plan_de_feu_data and isinstance(plan_de_feu_data, list):
                    for i, pstate in enumerate(plan_de_feu_data):
                        if i < len(self.projectors):
                            proj = self.projectors[i]
                            proj.level = pstate.get("level", 0)
                            proj.base_color = QColor(pstate.get("base_color", "#000000"))
                            proj.muted = pstate.get("muted", False)
                            if proj.level > 0:
                                brt = proj.level / 100.0
                                proj.color = QColor(
                                    int(proj.base_color.red() * brt),
                                    int(proj.base_color.green() * brt),
                                    int(proj.base_color.blue() * brt))
                            else:
                                proj.color = QColor(0, 0, 0)

                self.plan_de_feu.refresh()

            self.seq.is_dirty = False
            self.current_show_path = path
            self.add_recent_file(path)
            self.setWindowTitle(f"{APP_NAME} - {os.path.basename(path)}")

            # Verification des fichiers medias
            self._check_missing_media()

        except Exception as e:
            self.seq._loading = False
            QMessageBox.critical(self, "Erreur", f"Impossible de charger: {e}")

    def _check_missing_media(self):
        """Verifie que tous les fichiers medias du show existent"""
        missing = []
        for row in range(self.seq.table.rowCount()):
            title_item = self.seq.table.item(row, 1)
            if not title_item:
                continue
            path = title_item.data(Qt.UserRole)
            if not path or str(path) == "PAUSE" or str(path).startswith("PAUSE:"):
                continue
            if not os.path.isfile(path):
                missing.append((row, Path(path).name, path))
                # Emoji erreur dans la colonne icone
                icon_item = self.seq.table.item(row, 0)
                if icon_item:
                    icon_item.setText("\u26a0\ufe0f")
                    icon_item.setData(Qt.UserRole, "\u26a0\ufe0f")
                # Marquer visuellement la ligne en rouge
                for col in range(self.seq.table.columnCount()):
                    item = self.seq.table.item(row, col)
                    if item:
                        item.setForeground(QColor("#ff4444"))

        if missing:
            details = "\n".join(
                f"  Ligne {r + 1} : {name}" for r, name, _ in missing
            )
            QMessageBox.warning(self, "Fichiers manquants",
                f"{len(missing)} fichier(s) introuvable(s) :\n\n"
                f"{details}\n\n"
                f"Ces medias ont ete deplaces, supprimes ou renommes.")

    # ==================== CONFIG AKAI (sauvegarde/chargement memoires) ====================

    _AKAI_CONFIG_PATH = str(Path.home() / '.maestro_akai_config.json')

    def _serialize_akai_config(self):
        """Serialise les memoires AKAI en dict JSON"""
        custom_colors_serial = []
        for mc in range(4):
            col_colors = []
            for mr in range(8):
                c = self.memory_custom_colors[mc][mr]
                col_colors.append(c.name() if c else None)
            custom_colors_serial.append(col_colors)

        active_pads_serial = {str(k): v for k, v in self.active_memory_pads.items()}

        return {
            "memories": self.memories,
            "memory_custom_colors": custom_colors_serial,
            "active_memory_pads": active_pads_serial
        }

    def _apply_akai_config(self, config):
        """Applique une config AKAI (memoires) depuis un dict"""
        mem_data = config.get("memories")
        custom_colors_data = config.get("memory_custom_colors")
        active_pads_data = config.get("active_memory_pads")

        self.memories = [[None]*8, [None]*8, [None]*8, [None]*8]
        self.memory_custom_colors = [[None]*8, [None]*8, [None]*8, [None]*8]
        self.active_memory_pads = {}

        if mem_data and isinstance(mem_data, list):
            if len(mem_data) >= 1 and isinstance(mem_data[0], list):
                for mc in range(min(4, len(mem_data))):
                    for mr in range(min(8, len(mem_data[mc]))):
                        self.memories[mc][mr] = mem_data[mc][mr]

        if custom_colors_data and isinstance(custom_colors_data, list):
            for mc in range(min(4, len(custom_colors_data))):
                for mr in range(min(8, len(custom_colors_data[mc]))):
                    c = custom_colors_data[mc][mr]
                    self.memory_custom_colors[mc][mr] = QColor(c) if c else None

        # active_memory_pads non restaure : toujours demarrer sans pad actif
        # (evite le pad du haut "toujours enclenche" au demarrage)

        # Rafraichir l'affichage des pads memoire
        for mc in range(4):
            col_akai = 4 + mc
            for mr in range(8):
                is_active = self.active_memory_pads.get(col_akai) == mr
                self._style_memory_pad(mc, mr, active=is_active)

    def _save_akai_config_auto(self):
        """Sauvegarde automatique de la config AKAI a la fermeture"""
        try:
            config = self._serialize_akai_config()
            with open(self._AKAI_CONFIG_PATH, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Erreur sauvegarde config AKAI: {e}")

    def _load_akai_config_auto(self):
        """Charge automatique de la config AKAI au demarrage.
        Premier lancement (pas de fichier) : applique les presets par defaut."""
        try:
            if not os.path.exists(self._AKAI_CONFIG_PATH):
                # Premier lancement : charger les presets par defaut
                print("Premier lancement : application des presets AKAI par defaut")
                self._apply_akai_config(self._build_default_akai_presets())
                self._save_akai_config_auto()
            else:
                with open(self._AKAI_CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                self._apply_akai_config(config)
                self._migrate_missing_pad_colors()
            # Toujours activer le pad du haut de chaque colonne memoire au demarrage
            self._activate_top_pads_default()
        except Exception as e:
            print(f"Erreur chargement config AKAI: {e}")

    # Couleurs de rangee par defaut (meme ordre que la grille AKAI cols 0-3)
    _DEFAULT_PAD_ROW_COLORS = [
        "#ffffff", "#ff0000", "#ff8800", "#ffdd00",
        "#00ff00", "#00dddd", "#0000ff", "#ff00ff",
    ]

    def _migrate_missing_pad_colors(self):
        """Migration : pour toute colonne memoire sans couleurs ou sans memoires,
        applique les presets par defaut (couleurs de rangee + snapshots DMX).
        S'execute une seule fois apres chargement d'un ancien fichier de config."""
        needs_save = False
        _presets = None  # charge les presets une seule fois si necessaire

        for mc in range(4):
            has_colors   = any(self.memory_custom_colors[mc][mr] is not None for mr in range(8))
            has_memories = any(self.memories[mc][mr] is not None for mr in range(8))

            if not has_colors or not has_memories:
                if _presets is None:
                    _presets = self._build_default_akai_presets()

                if not has_memories:
                    for mr in range(8):
                        self.memories[mc][mr] = _presets["memories"][mc][mr]

                if not has_colors:
                    for mr in range(8):
                        self.memory_custom_colors[mc][mr] = QColor(self._DEFAULT_PAD_ROW_COLORS[mr])

                col_akai = 4 + mc
                for mr in range(8):
                    is_active = self.active_memory_pads.get(col_akai) == mr
                    self._style_memory_pad(mc, mr, active=is_active)

                needs_save = True
                print(f"Migration : colonne memoire {mc + 5} mise a jour")

        if needs_save:
            self._save_akai_config_auto()

    def _activate_top_pads_default(self):
        """Active le pad du haut (rangee 0) de chaque colonne memoire.
        Appele au demarrage. Les LEDs physiques AKAI sont envoyees par
        activate_default_white_pads() qui se declenche 100ms apres l'init."""
        for mc in range(4):
            if self.memories[mc][0] is not None:
                col_akai = 4 + mc
                self.active_memory_pads[col_akai] = 0
                self._style_memory_pad(mc, 0, active=True)
                self._apply_memory_to_projectors(mc, 0)

    def _build_default_akai_presets(self) -> dict:
        """
        Construit les presets Groupe B (Contres & LAT) par defaut pour les colonnes 5-8 (mem_col 0-3).

        Toutes les colonnes : LAT bicouleur symetrique + CONTRE bicouleur symetrique.
        (LAT gauche=dom / droite=acc ; CONTRE pattern D-A-D | D-A-D symetrique)

        Les 4 colonnes se distinguent par l'accord de couleur (accent) :
          Col 5 (mc=0) : Dominant + Harmonique adjacent  (teintes proches, doux)
          Col 6 (mc=1) : Dominant + Blanc pur            (effet naturel/scenique)
          Col 7 (mc=2) : Dominant + Complementaire       (contraste fort)
          Col 8 (mc=3) : Dominant + Split-comp / froid   (creatif)

        8 rangees = 8 couleurs dominantes = couleurs des pads (correspondance directe).
        """

        # (dom, [acc_col5, acc_col6, acc_col7, acc_col8])
        ROW_DATA = [
            ("#ffffff", ["#aabbff", "#ffe8aa", "#ffdd00", "#ff88cc"]),  # blanc   → bleu lavande / blanc chaud / jaune / rose
            ("#ff0000", ["#ff8800", "#ffffff", "#00dddd", "#ff00ff"]),  # rouge   → orange / blanc / cyan / magenta
            ("#ff8800", ["#ffdd00", "#ffffff", "#0000ff", "#ff0000"]),  # orange  → jaune / blanc / bleu / rouge
            ("#ffdd00", ["#ff8800", "#ffffff", "#8800ff", "#00ff00"]),  # jaune   → orange / blanc / violet / vert
            ("#00ff00", ["#00dddd", "#ffffff", "#ff00ff", "#0000ff"]),  # vert    → cyan / blanc / magenta / bleu
            ("#00dddd", ["#0000ff", "#ffffff", "#ff0000", "#8800ff"]),  # cyan    → bleu / blanc / rouge / violet
            ("#0000ff", ["#8800ff", "#ffffff", "#ff8800", "#00dddd"]),  # bleu    → violet / blanc / orange / cyan
            ("#ff00ff", ["#ff0000", "#ffffff", "#00ff00", "#0000ff"]),  # magenta → rouge / blanc / vert / bleu
        ]

        # Structure projectors : 23 dans l'ordre de _create_projectors()
        # [0-3]   FACE (4)
        # [4-6]   DOUCHE1 (3), [7-9] DOUCHE2 (3), [10-12] DOUCHE3 (3)
        # [13-14] LAT (2)   : [13]=gauche, [14]=droite
        # [15-20] CONTRE (6): [15-17]=gauche, [18-20]=droite
        # [21]    PUBLIC (1), [22] FUMEE (1)

        def proj(group, color, level=100):
            return {"group": group, "base_color": color, "level": level}

        def off(group):
            return {"group": group, "base_color": "#000000", "level": 0}

        def make_snapshot(dom, acc):
            snapshot = []

            # FACE + DOUCHES : off
            for _ in range(4):
                snapshot.append(off("face"))
            for grp in ("douche1", "douche2", "douche3"):
                for _ in range(3):
                    snapshot.append(off(grp))

            # LAT bicouleur symetrique (gauche=dom, droite=acc)
            snapshot.append(proj("lat", dom))
            snapshot.append(proj("lat", acc))

            # CONTRE bicouleur symetrique : pattern D-A-D | D-A-D
            for _ in range(2):  # gauche x3 puis droite x3
                snapshot.append(proj("contre", dom))
                snapshot.append(proj("contre", acc))
                snapshot.append(proj("contre", dom))

            snapshot.append(off("public"))
            snapshot.append(off("fumee"))

            return {"projectors": snapshot}

        memories      = [[None] * 8 for _ in range(4)]
        custom_colors = [[None] * 8 for _ in range(4)]

        for mc in range(4):
            for row in range(8):
                dom, accs = ROW_DATA[row]
                acc = accs[mc]
                memories[mc][row] = make_snapshot(dom, acc)
                custom_colors[mc][row] = dom  # couleur du pad = dominant

        return {
            "memories": memories,
            "memory_custom_colors": custom_colors,
            "active_memory_pads": {},
        }

    def load_default_presets(self):
        """Charge (ou restaure) les configurations par defaut Groupe B (Contres & LAT)."""
        reply = QMessageBox.question(
            self,
            "Configurations par defaut",
            "Charger les presets Groupe B (Contres & LAT) par defaut ?\n\n"
            "Les memoires des colonnes 5 a 8 seront remplacees.\n"
            "Les colonnes 1 a 4 (couleurs) ne sont pas modifiees.",
            QMessageBox.Yes | QMessageBox.Cancel
        )
        if reply != QMessageBox.Yes:
            return

        presets = self._build_default_akai_presets()

        # Fusionner : ne remplacer que les 4 colonnes memoire, conserver le reste
        for mc in range(4):
            for mr in range(8):
                self.memories[mc][mr] = presets["memories"][mc][mr]
                c = presets["memory_custom_colors"][mc][mr]
                self.memory_custom_colors[mc][mr] = QColor(c) if c else None
                col_akai = mc + 4
                is_active = self.active_memory_pads.get(col_akai) == mr
                self._style_memory_pad(mc, mr, active=is_active)
                self._update_memory_pad_led(mc, mr, active=is_active)

        self._save_akai_config_auto()
        QMessageBox.information(
            self, "Configurations par defaut",
            "Presets Groupe B (Contres & LAT) charges avec succes !\n\n"
            "Col 5 : Groupe B — accord harmonique (teintes proches)\n"
            "Col 6 : Groupe B — avec blanc pur (naturel / scenique)\n"
            "Col 7 : Groupe B — couleur complementaire (fort contraste)\n"
            "Col 8 : Groupe B — split-complementaire (creatif)"
        )

    def export_akai_config(self):
        """Exporte la configuration AKAI dans un fichier"""
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter configuration AKAI", "",
            "Configuration AKAI (*.akai.json)")
        if not path:
            return
        if not path.endswith('.akai.json'):
            path += '.akai.json'
        try:
            config = self._serialize_akai_config()
            with open(path, 'w') as f:
                json.dump(config, f, indent=2)
            QMessageBox.information(self, "Export", "Configuration AKAI exportee avec succes.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'exporter: {e}")

    def import_akai_config(self):
        """Importe une configuration AKAI depuis un fichier"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer configuration AKAI", "",
            "Configuration AKAI (*.akai.json);;Tous les fichiers (*)")
        if not path:
            return
        try:
            with open(path, 'r') as f:
                config = json.load(f)
            self._apply_akai_config(config)
            QMessageBox.information(self, "Import", "Configuration AKAI importee avec succes.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'importer: {e}")

    # ==================== FIN CONFIG AKAI ====================

    def load_recent_files(self):
        """Charge la liste des fichiers recents"""
        try:
            recent_path = os.path.join(os.path.expanduser("~"), ".maestro_recent.json")
            if os.path.exists(recent_path):
                with open(recent_path, 'r') as f:
                    return json.load(f)
        except:
            pass
        return []

    def save_recent_files(self):
        """Sauvegarde la liste des fichiers recents"""
        try:
            recent_path = os.path.join(os.path.expanduser("~"), ".maestro_recent.json")
            with open(recent_path, 'w') as f:
                json.dump(self.recent_files, f)
        except:
            pass

    def add_recent_file(self, filepath):
        """Ajoute un fichier a la liste des recents"""
        if filepath in self.recent_files:
            self.recent_files.remove(filepath)
        self.recent_files.insert(0, filepath)
        self.recent_files = self.recent_files[:10]
        self.save_recent_files()
        self.update_recent_menu()

    def update_recent_menu(self):
        """Met a jour le menu des fichiers recents"""
        self.recent_menu.clear()
        if not self.recent_files:
            action = self.recent_menu.addAction("(Aucun fichier recent)")
            action.setEnabled(False)
            return
        for filepath in self.recent_files:
            if os.path.exists(filepath):
                filename = os.path.basename(filepath)
                action = self.recent_menu.addAction(filename)
                action.setData(filepath)
                action.triggered.connect(self.load_recent_file)

    def load_recent_file(self):
        """Charge un fichier depuis le menu recent"""
        action = self.sender()
        if action:
            filepath = action.data()
            self.load_show(filepath)

    def reconnect_midi(self):
        """Force la reconnexion MIDI"""
        if not MIDI_AVAILABLE:
            QMessageBox.information(self, "MIDI non disponible",
                "Le support MIDI n'est pas active.")
            return

        try:
            self.midi_handler.connect_akai()
            if self.midi_handler.midi_in and self.midi_handler.midi_out:
                QTimer.singleShot(200, self.activate_default_white_pads)
                QTimer.singleShot(300, self.turn_off_all_effects)
                QTimer.singleShot(400, self._sync_faders_to_projectors)
                QMessageBox.information(self, "Reconnexion reussie",
                    "AKAI APC mini reconnecte avec succes !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur de reconnexion: {e}")

    def open_light_editor(self, row=None):
        """Ouvre l'editeur de sequence lumiere"""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()

        if row is not None:
            current_row = row
        else:
            current_row = self.seq.table.currentRow()

        if current_row < 0:
            QMessageBox.warning(self, "Aucun media selectionne",
                "Selectionnez d'abord un media dans le sequenceur")
            return

        item = self.seq.table.item(current_row, 1)
        if not item or not item.data(Qt.UserRole):
            return

        path = item.data(Qt.UserRole)

        # Bloquer si pause indefinie
        if path == "PAUSE":
            QMessageBox.warning(self, "REC Lumiere",
                "Veuillez d'abord definir une duree pour cette pause\n"
                "avant de pouvoir creer une sequence lumiere.")
            return

        # Bloquer si image sans duree definie
        if media_icon(path) == "image":
            if current_row not in self.seq.image_durations:
                QMessageBox.warning(self, "REC Lumiere",
                    "Veuillez d'abord definir une duree\n"
                    "pour cette image avant de creer une sequence lumiere.\n\n"
                    "Clic droit > Definir la duree")
                return

        editor = LightTimelineEditor(self, current_row)
        editor.exec()

    def _edit_current_volume(self):
        """Edite le volume du media selectionne (audio/video uniquement)"""
        row = self.seq.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aucun media",
                "Selectionnez d'abord un media dans le sequenceur.")
            return
        title_item = self.seq.table.item(row, 1)
        if not title_item:
            return
        path = title_item.data(Qt.UserRole)
        if path and media_icon(path) in ("audio", "video"):
            self.seq.edit_media_volume(row)
        else:
            QMessageBox.warning(self, "Non applicable",
                "Le volume est disponible uniquement pour les fichiers audio et video.")

    def _edit_current_duration(self):
        """Edite la duree de l'image ou de la pause selectionnee"""
        row = self.seq.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aucun media",
                "Selectionnez d'abord un element dans le sequenceur.")
            return
        title_item = self.seq.table.item(row, 1)
        if not title_item:
            return
        data = str(title_item.data(Qt.UserRole) or "")
        if data == "PAUSE" or data.startswith("PAUSE:"):
            self.seq.edit_pause_duration(row)
        elif media_icon(data) == "image":
            self.seq.edit_image_duration(row)
        else:
            QMessageBox.warning(self, "Non applicable",
                "Cette fonction est disponible pour les images et les pauses.")

    def show_about(self):
        """Ouvre le dialogue A propos / mises à jour"""
        AboutDialog(self).exec()

    def on_update_available(self, version, exe_url, hash_url, sig_url=""):
        """Signal du checker async - montre la barre verte"""
        self.update_bar.set_info(version, exe_url, hash_url, sig_url)
        self.update_bar.show()

    def _on_update_later(self):
        """Bouton Plus tard - reminder 24h"""
        UpdateChecker.save_reminder(self.update_bar.version)
        self.update_bar.hide()

    def _on_update_now(self):
        """Bouton Mettre a jour - telechargement"""
        download_update(self,
            self.update_bar.version,
            self.update_bar.exe_url,
            self.update_bar.hash_url,
            self.update_bar.sig_url)

    # ==================== LICENCE ====================

    def _setup_video_watermark(self):
        """Ajoute un watermark flottant sur le preview video integre"""
        if self._license.watermark_required:
            self._video_watermark = QLabel(self.video_stack)
            self._video_watermark.setAlignment(Qt.AlignCenter)
            self._video_watermark.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._update_video_watermark()
            self._video_watermark.show()
            self._video_watermark.raise_()
        else:
            self._video_watermark = None

    def _update_video_watermark(self):
        """Met a jour le pixmap du watermark video"""
        if not hasattr(self, '_video_watermark') or not self._video_watermark:
            return
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Mystrow_blanc.png")
        if os.path.exists(logo_path):
            px = QPixmap(logo_path)
            target_w = max(150, int(self.video_stack.width() * 0.3))
            scaled = px.scaledToWidth(target_w, Qt.SmoothTransformation)
            result = QPixmap(scaled.size())
            result.fill(Qt.transparent)
            painter = QPainter(result)
            painter.setOpacity(0.4)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            self._video_watermark.setPixmap(result)
            # Centrer
            x = (self.video_stack.width() - scaled.width()) // 2
            y = (self.video_stack.height() - scaled.height()) // 2
            self._video_watermark.setGeometry(x, y, scaled.width(), scaled.height())

    def _open_activation_dialog(self):
        """Ouvre le dialogue d'activation de licence"""
        dlg = ActivationDialog(self, license_result=self._license)
        dlg.activation_success.connect(self._on_activation_success)
        dlg.exec()

    def _on_activation_success(self):
        """Appele apres une activation reussie - re-verifie et applique"""
        new_result = verify_license()
        self._license = new_result

        # Banniere supprimee

        # Activer/desactiver DMX
        if self._license.dmx_allowed:
            if not self.dmx.connected:
                self.test_dmx_on_startup()
        else:
            self.dmx.connected = False
            self.plan_de_feu.set_dmx_blocked()

        # Activer/desactiver menu Node
        if hasattr(self, 'node_menu'):
            self.node_menu.setEnabled(self._license.dmx_allowed)

        # Watermark video integre
        if not self._license.watermark_required:
            if hasattr(self, '_video_watermark') and self._video_watermark:
                self._video_watermark.hide()
                self._video_watermark.deleteLater()
                self._video_watermark = None
        else:
            if not hasattr(self, '_video_watermark') or not self._video_watermark:
                self._setup_video_watermark()

        # Watermark fenetre de sortie video
        if self.video_output_window:
            self.video_output_window.set_watermark(self._license.watermark_required)

    def show_license_warning_if_needed(self):
        """Affiche le dialogue d'avertissement si necessaire (appele apres show)"""
        if not self._license.show_warning:
            return
        result = LicenseWarningDialog(self._license, self).exec()
        if result == 2:  # Bouton "Activer"
            self._open_activation_dialog()

    def restart_application(self):
        """Redemarre l'application"""
        reply = QMessageBox.question(self, "Redemarrer",
            "Voulez-vous redemarrer l'application ?",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            if hasattr(self, 'midi_handler') and self.midi_handler:
                try:
                    if self.midi_handler.midi_in:
                        self.midi_handler.midi_in.close_port()
                    if self.midi_handler.midi_out:
                        self.midi_handler.midi_out.close_port()
                except:
                    pass
            python = sys.executable
            os.execv(python, [python] + sys.argv)

    def toggle_blackout_from_midi(self):
        """Toggle le blackout depuis le bouton 9 de l'AKAI"""
        self.blackout_active = not self.blackout_active

        if self.blackout_active:
            for proj in self.projectors:
                proj.color = QColor("black")
                proj.level = 0

            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                self.midi_handler.midi_out.send_message([0x90, 122, 3])
        else:
            for i, fader in self.faders.items():
                if i < 8:
                    self.set_proj_level(i, fader.value)

            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                self.midi_handler.midi_out.send_message([0x90, 122, 0])

    def toggle_fader_mute_from_midi(self, fader_idx):
        """Toggle le mute d'un fader depuis l'AKAI physique - tous independants"""
        if fader_idx == 8:
            return

        if 0 <= fader_idx < len(self.fader_buttons):
            btn = self.fader_buttons[fader_idx]
            btn.active = not btn.active
            btn.update_style()
            self.toggle_mute(fader_idx, btn.active)

            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                note = 100 + fader_idx
                velocity = 3 if btn.active else 0
                self.midi_handler.midi_out.send_message([0x90, note, velocity])

    # Mapping raccourcis clavier -> couleurs
    COLOR_SHORTCUTS = {
        Qt.Key_R: QColor(255, 0, 0),
        Qt.Key_G: QColor(0, 255, 0),
        Qt.Key_B: QColor(0, 0, 255),
        Qt.Key_C: QColor(0, 255, 255),
        Qt.Key_M: QColor(255, 0, 255),
        Qt.Key_Y: QColor(255, 255, 0),
        Qt.Key_W: QColor(255, 255, 255),
        Qt.Key_K: QColor(0, 0, 0),
        Qt.Key_O: QColor(255, 128, 0),
        Qt.Key_P: QColor(255, 105, 180),
    }

    def keyPressEvent(self, event):
        """Gere les raccourcis clavier"""
        key = event.key()

        if key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.toggle_play()
            event.accept()
        elif key == Qt.Key_PageDown:
            self.next_media()
            event.accept()
        elif key == Qt.Key_PageUp:
            self.previous_media()
            event.accept()
        elif key in (Qt.Key_F1, Qt.Key_F2, Qt.Key_F3, Qt.Key_F4):
            cart_index = key - Qt.Key_F1  # F1=0, F2=1, F3=2, F4=3
            if cart_index < len(self.cartouches):
                self.on_cartouche_clicked(cart_index)
            event.accept()
        elif key in self.COLOR_SHORTCUTS:
            self._apply_color_shortcut(self.COLOR_SHORTCUTS[key])
            event.accept()
        else:
            super().keyPressEvent(event)

    def _apply_color_shortcut(self, color):
        """Applique une couleur raccourci aux projecteurs selectionnes"""
        if not self.plan_de_feu.selected_lamps:
            return
        targets = []
        for g, i in self.plan_de_feu.selected_lamps:
            projs = [p for p in self.projectors if p.group == g]
            if i < len(projs):
                targets.append(projs[i])
        for proj in targets:
            proj.base_color = color
            proj.level = 100
            proj.color = QColor(color.red(), color.green(), color.blue())
        if self.dmx:
            self.dmx.update_from_projectors(self.projectors)
        self.plan_de_feu.refresh()

    def show_shortcuts_dialog(self):
        """Affiche le dialog listant tous les raccourcis clavier"""
        dlg = QDialog(self)
        dlg.setWindowTitle("Raccourcis clavier")
        dlg.setMinimumSize(700, 620)
        dlg.setStyleSheet("""
            QDialog { background: #1a1a1a; color: #e0e0e0; }
            QLabel { color: #e0e0e0; }
            QScrollArea { border: none; background: #1a1a1a; }
            QWidget#shortcut_content { background: #1a1a1a; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Raccourcis clavier")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #ffffff; padding-bottom: 4px;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content.setObjectName("shortcut_content")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(4)

        # Donnees : (groupe, [(touche, description), ...])
        shortcut_groups = [
            ("LECTURE", [
                ("Espace / Entree", "Play / Pause"),
                ("Page Down", "Media suivant"),
                ("Page Up", "Media precedent"),
                ("F1", "Cartouche 1"),
                ("F2", "Cartouche 2"),
                ("F3", "Cartouche 3"),
                ("F4", "Cartouche 4"),
            ]),
            ("FICHIERS", [
                ("Ctrl + N", "Nouveau show"),
                ("Ctrl + O", "Ouvrir show"),
                ("Ctrl + S", "Enregistrer show"),
                ("Ctrl + Shift + S", "Enregistrer sous"),
            ]),
            ("COULEURS RAPIDES", [
                ("W", "Blanc"),
                ("R", "Rouge"),
                ("O", "Orange"),
                ("Y", "Jaune"),
                ("G", "Vert"),
                ("C", "Cyan"),
                ("B", "Bleu"),
                ("M", "Magenta"),
                ("P", "Rose"),
                ("K", "Noir (eteindre)"),
            ]),
            ("PLAN DE FEU  -  Selection", [
                ("Ctrl + A", "Tout selectionner"),
                ("Escape", "Deselectionner tout"),
                ("Escape x3", "Eteindre tous les projecteurs"),
                ("F", "Selectionner les Faces"),
                ("1", "Contre + Lat pairs"),
                ("2", "Contre + Lat impairs"),
                ("3", "Tous Contre + Lat"),
                ("4", "Douche 1"),
                ("5", "Douche 2"),
                ("6", "Douche 3"),
            ]),
            ("EDITEUR TIMELINE", [
                ("Espace", "Play / Pause"),
                ("Ctrl + Z", "Annuler"),
                ("Ctrl + Y", "Retablir"),
                ("Suppr", "Supprimer les clips selectionnes"),
                ("Ctrl + A", "Selectionner tous les clips"),
                ("Ctrl + C", "Copier les clips"),
                ("Ctrl + X", "Couper les clips"),
                ("Ctrl + V", "Coller les clips"),
                ("C", "Activer / desactiver mode CUT"),
                ("Escape", "Quitter mode CUT / deselectionner"),
            ]),
        ]

        for group_name, shortcuts in shortcut_groups:
            # En-tete de groupe
            group_label = QLabel(f"  {group_name}")
            group_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
            group_label.setStyleSheet("color: #00d4ff; padding: 8px 0 2px 0;")
            scroll_layout.addWidget(group_label)

            for key, desc in shortcuts:
                row_frame = QFrame()
                row_frame.setStyleSheet("""
                    QFrame {
                        background: #222222; border-radius: 6px;
                        padding: 6px 12px; margin: 1px 0;
                    }
                    QFrame:hover { background: #2a2a2a; }
                """)
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(8, 4, 8, 4)

                # Touche avec style "keycap"
                key_label = QLabel(key)
                key_label.setMinimumWidth(180)
                key_label.setStyleSheet("""
                    color: #ffffff; font-weight: bold; font-size: 13px;
                    font-family: 'Consolas';
                """)
                row_layout.addWidget(key_label)

                row_layout.addStretch()

                desc_label = QLabel(desc)
                desc_label.setMinimumWidth(300)
                desc_label.setStyleSheet("color: #aaaaaa; font-size: 13px;")
                row_layout.addWidget(desc_label)

                scroll_layout.addWidget(row_frame)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        close_btn = QPushButton("Fermer")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #333333; color: #aaaaaa;
                padding: 10px 30px; border-radius: 6px; font-size: 13px;
                border: 1px solid #4a4a4a;
            }
            QPushButton:hover { background: #3a3a3a; color: #ffffff; }
        """)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        dlg.exec()

    def next_media(self):
        """Passe au media suivant"""
        if self.seq.current_row + 1 < self.seq.table.rowCount():
            self.seq.play_row(self.seq.current_row + 1)

    def previous_media(self):
        """Revient au media precedent"""
        if self.seq.current_row > 0:
            self.seq.play_row(self.seq.current_row - 1)

    # ==================== CARTOUCHEUR ====================

    def on_cartouche_clicked(self, index):
        """Gere le clic sur une cartouche (3 etats)"""
        cart = self.cartouches[index]
        if not cart.media_path:
            self._load_cartouche_file(index)
            return
        if cart.state == CartoucheButton.PLAYING:
            self._stop_cartouche(index)
        else:
            self._play_cartouche(index)

    def _play_cartouche(self, index):
        """Lance la lecture d'une cartouche"""
        cart = self.cartouches[index]
        if not cart.media_path:
            return

        # Stopper toute autre cartouche active
        for i, c in enumerate(self.cartouches):
            if i != index and c.state == CartoucheButton.PLAYING:
                c.set_idle()

        # Stopper le player principal si en lecture
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()

        # Video: rediriger vers le video_widget
        ext = os.path.splitext(cart.media_path)[1].lower()
        video_exts = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}
        if ext in video_exts:
            self.cart_player.setVideoOutput(self.video_widget)
        else:
            self.cart_player.setVideoOutput(None)

        self.cart_audio.setVolume(cart.volume / 100.0)
        self.cart_player.setSource(QUrl.fromLocalFile(cart.media_path))
        self.cart_player.play()
        cart.set_playing()
        self.cart_playing_index = index

    def _stop_cartouche(self, index):
        """Arrete la cartouche en cours"""
        self.cart_player.stop()
        self.cartouches[index].set_stopped()
        self.cart_playing_index = -1
        # Restaurer le video output du player principal
        self.player.setVideoOutput(self.video_widget)

    def _stop_all_cartouches(self):
        """Arrete toutes les cartouches et restaure l'etat"""
        if self.cart_playing_index >= 0:
            self.cart_player.stop()
            self.cart_playing_index = -1
        for cart in self.cartouches:
            cart.set_idle()
        self.player.setVideoOutput(self.video_widget)

    def on_cart_media_status(self, status):
        """Gere la fin de lecture d'une cartouche"""
        if status == QMediaPlayer.EndOfMedia:
            if 0 <= self.cart_playing_index < len(self.cartouches):
                self.cartouches[self.cart_playing_index].set_stopped()
                self.cart_playing_index = -1

    def load_cartouche_media(self, index):
        """Menu contextuel sur une cartouche (clic droit)"""
        from PySide6.QtWidgets import QWidgetAction, QSlider
        cart = self.cartouches[index]
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
                color: white;
            }
            QMenu::item:selected {
                background: #2a4a5a;
            }
            QMenu::separator {
                height: 1px;
                background: #3a3a3a;
                margin: 4px 8px;
            }
        """)

        # Volume slider
        vol_widget = QWidget()
        vol_layout = QHBoxLayout(vol_widget)
        vol_layout.setContentsMargins(12, 6, 12, 6)
        vol_layout.setSpacing(8)

        vol_icon = QLabel("Vol")
        vol_icon.setStyleSheet("color: #888; font-size: 11px; font-weight: bold;")
        vol_layout.addWidget(vol_icon)

        vol_slider = QSlider(Qt.Horizontal)
        vol_slider.setRange(0, 100)
        vol_slider.setValue(cart.volume)
        vol_slider.setFixedWidth(130)
        vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333; height: 6px; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff; width: 14px; height: 14px;
                margin: -4px 0; border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #005577, stop:1 #00d4ff);
                border-radius: 3px;
            }
        """)
        vol_layout.addWidget(vol_slider)

        vol_label = QLabel(f"{cart.volume}%")
        vol_label.setStyleSheet("color: #ddd; font-size: 11px; font-weight: bold; min-width: 32px;")
        vol_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        vol_layout.addWidget(vol_label)

        def on_vol_changed(v):
            vol_label.setText(f"{v}%")
            cart.volume = v
            cart._update_style()
            # Appliquer en temps reel si en lecture
            if self.cart_playing_index == index:
                self.cart_audio.setVolume(v / 100.0)

        vol_slider.valueChanged.connect(on_vol_changed)

        vol_action = QWidgetAction(menu)
        vol_action.setDefaultWidget(vol_widget)
        menu.addAction(vol_action)

        menu.addSeparator()

        load_action = menu.addAction("Charger un media")
        clear_action = None
        if cart.media_path:
            clear_action = menu.addAction("Vider la cartouche")

        action = menu.exec(cart.mapToGlobal(cart.rect().bottomLeft()))

        if action == load_action:
            self._load_cartouche_file(index)
        elif action == clear_action:
            self._clear_cartouche(index)

    def _load_cartouche_file(self, index):
        """Charge un fichier dans une cartouche"""
        path, _ = QFileDialog.getOpenFileName(
            self, f"Charger Cartouche {index + 1}", "",
            "Medias (*.mp3 *.wav *.ogg *.flac *.aac *.wma *.mp4 *.avi *.mkv *.mov *.wmv *.webm)"
        )
        if not path:
            return

        try:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            if size_mb > 300:
                QMessageBox.warning(self, "Fichier trop volumineux",
                    f"Le fichier fait {size_mb:.0f} Mo.\nLimite: 300 Mo pour les cartouches.")
                return
        except OSError:
            pass

        cart = self.cartouches[index]
        cart.media_path = path
        cart.media_title = Path(path).stem
        ext = Path(path).suffix.lower()
        if ext in CartoucheButton.VIDEO_EXTS:
            cart.media_icon = "\U0001f3ac"
        elif ext in CartoucheButton.AUDIO_EXTS:
            cart.media_icon = "\U0001f3b5"
        else:
            cart.media_icon = ""
        cart.set_idle()

    def _clear_cartouche(self, index):
        """Vide une cartouche"""
        if self.cart_playing_index == index:
            self.cart_player.stop()
            self.cart_playing_index = -1
            self.player.setVideoOutput(self.video_widget)
        cart = self.cartouches[index]
        cart.media_path = None
        cart.media_title = None
        cart.media_icon = ""
        cart.set_idle()

    # ==================== FIN CARTOUCHEUR ====================

    def closeEvent(self, e):
        """Gere la fermeture de la fenetre"""
        # Sauvegarder automatiquement la config AKAI
        self._save_akai_config_auto()

        # Fermer la fenetre de sortie video
        if self.video_output_window:
            self.video_output_window.close()
            self.video_output_window = None

        if hasattr(self, 'midi_handler'):
            self.midi_handler.close()

        if self.seq.is_dirty:
            res = QMessageBox.question(self, "Quitter",
                "Sauvegarder avant de quitter ?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if res == QMessageBox.Yes:
                if self.save_show():
                    self._allow_sleep()
                    e.accept()
                else:
                    e.ignore()
            elif res == QMessageBox.Cancel:
                e.ignore()
            else:
                self._allow_sleep()
                e.accept()
        else:
            self._allow_sleep()
            e.accept()

    def apply_styles(self):
        """Applique les styles CSS"""
        self.setStyleSheet("""
            QMainWindow { background: #050505; }
            QWidget { color: #ddd; font-family: 'Segoe UI'; font-size: 10pt; }
            QFrame { background: #0f0f0f; border: 1px solid #1a1a1a; border-radius: 8px; }
            QMenuBar { background: #1a1a1a; border-bottom: 1px solid #2a2a2a; padding: 4px; }
            QMenuBar::item { padding: 6px 12px; background: transparent; border-radius: 4px; }
            QMenuBar::item:selected { background: #2a2a2a; }
            QMenu { background: #1a1a1a; border: 1px solid #2a2a2a; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background: #2a2a2a; }
            QSplitter::handle { background: #1a1a1a; }
            QMessageBox { background: #1a1a1a; }
            QMessageBox QLabel { color: white; }
            QMessageBox QPushButton {
                color: black;
                background: #cccccc;
                border: 1px solid #999999;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
            }
            QMessageBox QPushButton:hover { background: #00d4ff; }
        """)

    # ==================== DMX PATCH ====================

    def auto_patch_at_startup(self):
        """Patch automatique au demarrage"""
        if self.load_dmx_patch_config():
            return

        # Appliquer le patch depuis start_address de chaque fixture
        for i, proj in enumerate(self.projectors):
            proj_key = f"{proj.group}_{i}"
            if proj.group == "fumee" or proj.fixture_type == "Machine a fumee":
                profile = list(DMX_PROFILES["2CH_FUMEE"])
            elif proj.fixture_type == "Moving Head":
                profile = list(DMX_PROFILES["MOVING_8CH"])
            elif proj.fixture_type == "Barre LED":
                profile = list(DMX_PROFILES["LED_BAR_RGB"])
            elif proj.fixture_type == "Stroboscope":
                profile = list(DMX_PROFILES["STROBE_2CH"])
            else:
                profile = list(DMX_PROFILES["RGBDS"])

            nb_ch = len(profile)
            channels = [proj.start_address + c for c in range(nb_ch)]
            self.dmx.set_projector_patch(proj_key, channels, profile=profile)

    def show_dmx_patch_config(self):
        """Interface de configuration DMX — master-detail + Plan de feu"""
        from plan_de_feu import FixtureCanvas, NewPlanWizard

        # ── Dialog ────────────────────────────────────────────────────────
        dialog = QDialog(self)
        dialog.setWindowTitle("Patch DMX")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        screen = QApplication.primaryScreen().availableGeometry()
        dw = max(1000, min(1350, screen.width() - 120))
        dh = max(650,  min(860,  screen.height() - 120))
        dialog.resize(dw, dh)
        dialog.move(screen.x() + (screen.width() - dw) // 2, screen.y() + (screen.height() - dh) // 2)

        _SS = """
            QDialog { background:#0f0f0f; color:#e0e0e0; }
            QTabWidget::pane { border:none; background:#0f0f0f; }
            QTabBar::tab { background:#181818; color:#444; padding:10px 26px;
                border:none; border-bottom:2px solid transparent; font-size:12px; }
            QTabBar::tab:selected { color:#fff; border-bottom:2px solid #00d4ff; background:#0f0f0f; }
            QTabBar::tab:hover { color:#aaa; background:#1c1c1c; }
            QScrollArea { border:none; background:transparent; }
            QScrollBar:vertical { background:#0a0a0a; width:5px; border-radius:2px; }
            QScrollBar::handle:vertical { background:#252525; border-radius:2px; min-height:20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QLineEdit { background:#171717; color:#fff; border:1px solid #242424;
                border-radius:7px; padding:7px 13px; font-size:13px; }
            QLineEdit:focus { border:1px solid #00d4ff44; background:#14141c; }
            QComboBox { background:#171717; color:#ddd; border:1px solid #242424;
                border-radius:7px; padding:7px 12px; font-size:12px; }
            QComboBox:focus { border-color:#00d4ff44; }
            QComboBox::drop-down { border:none; width:18px; }
            QComboBox QAbstractItemView { background:#1e1e1e; color:#e0e0e0;
                border:1px solid #333; selection-background-color:#00d4ff22;
                selection-color:#00d4ff; outline:none; padding:4px; }
            QComboBox QAbstractItemView::item { padding:6px 12px; border-radius:4px; }
            QSpinBox { background:#171717; color:#00d4ff; border:1px solid #242424;
                border-radius:7px; padding:6px 10px; font-size:17px; font-weight:bold; }
            QSpinBox:focus { border-color:#00d4ff44; }
            QSpinBox::up-button, QSpinBox::down-button { width:0; height:0; }
            QPushButton { background:#181818; color:#888; border:1px solid #242424;
                border-radius:6px; padding:6px 16px; font-size:12px; }
            QPushButton:hover { border-color:#00d4ff33; color:#ddd; background:#1e1e28; }
            QPushButton:pressed { background:#00d4ff11; }
            QLabel { color:#e0e0e0; }
            QFrame[frameShape="4"] { color:#1e1e1e; }
            QFrame[frameShape="5"] { color:#1e1e1e; }
        """
        dialog.setStyleSheet(_SS)

        _GC = {
            "face": "#ff8844", "contre": "#4488ff",
            "douche1": "#44cc88", "douche2": "#44cc88", "douche3": "#44cc88",
            "lat": "#aa55ff", "lyre": "#ff44cc", "barre": "#44aaff",
            "strobe": "#ffee44", "fumee": "#88aaaa", "public": "#ff6655",
        }
        GROUP_LETTERS = {
            "face": "A", "contre": "B", "lat": "B",
            "douche1": "C", "douche2": "C", "douche3": "C",
            "public": "D",
            "fumee": "Fumée", "lyre": "Lyres", "barre": "Barres", "strobe": "Strobos",
        }
        FIXTURE_TYPES = ["PAR LED", "Moving Head", "Barre LED", "Stroboscope", "Machine a fumee"]
        CH_COLORS = {
            "R":          "#cc1111",
            "G":          "#22aa33",
            "B":          "#1155dd",
            "W":          "#cccccc",
            "Dim":        "#cc9900",
            "Strobe":     "#bb33cc",
            "UV":         "#6611dd",
            "Ambre":      "#cc6600",
            "Orange":     "#dd4400",
            "Pan":        "#1199cc",
            "Tilt":       "#11ccaa",
            "Smoke":      "#5588aa",
            "Fan":        "#336677",
            "Gobo1":      "#993355",
            "Gobo2":      "#774455",
            "Shutter":    "#999911",
            "Speed":      "#557722",
            "Mode":       "#445566",
            "ColorWheel": "#aa2299",
            "Prism":      "#2266aa",
            "Focus":      "#776622",
            "PanFine":    "#0077bb",
            "TiltFine":   "#00aa88",
        }

        root = QVBoxLayout(dialog)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Menu bar ──────────────────────────────────────────────────────
        menubar = QMenuBar(dialog)
        menubar.setStyleSheet("""
            QMenuBar {
                background: #090909;
                color: #888;
                border-bottom: 1px solid #181818;
                padding: 2px 8px;
                font-size: 12px;
            }
            QMenuBar::item { padding: 5px 14px; background: transparent; border-radius: 4px; }
            QMenuBar::item:selected { background: #1a1a1a; color: #ddd; }
            QMenu {
                background: #111111;
                color: #cccccc;
                border: 1px solid #2a2a2a;
                padding: 4px;
                font-size: 12px;
            }
            QMenu::item { padding: 7px 28px; border-radius: 3px; }
            QMenu::item:selected { background: #00d4ff22; color: #00d4ff; }
            QMenu::separator { background: #1e1e1e; height: 1px; margin: 3px 8px; }
        """)
        m_file = menubar.addMenu("Fichier")
        act_new  = m_file.addAction("✨  Nouveau Patch")
        act_save = m_file.addAction("💾  Enregistrer Patch")
        m_file.addSeparator()
        act_dflt = m_file.addAction("↺  Patch par défaut")

        m_edit = menubar.addMenu("Edition")
        act_undo = m_edit.addAction("↩  Annuler\tCtrl+Z")
        act_redo = m_edit.addAction("↪  Rétablir\tCtrl+Y")
        m_edit.addSeparator()
        act_auto = m_edit.addAction("⚡  Auto Adresse")

        root.addWidget(menubar)

        # ── Toolbar ───────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(56)
        toolbar.setStyleSheet("background:#090909; border-bottom:1px solid #181818;")
        th = QHBoxLayout(toolbar)
        th.setContentsMargins(20, 0, 20, 0)
        th.setSpacing(8)
        lbl_ttl = QLabel("Patch DMX")
        lbl_ttl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_ttl.setStyleSheet("color:white; padding-right:16px;")
        th.addWidget(lbl_ttl)

        def _tbar_btn(text, color):
            b = QPushButton(text)
            b.setFixedHeight(34)
            b.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{color}; border:1px solid {color}33;"
                f" border-radius:6px; padding:6px 16px; font-size:12px; }}"
                f"QPushButton:hover {{ background:{color}18; border-color:{color}66; }}"
            )
            return b

        btn_add = _tbar_btn("➕  Ajouter", "#55cc77")
        th.addWidget(btn_add)
        th.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(
            "QPushButton { background:#181818; color:#777; border:1px solid #252525;"
            " border-radius:6px; padding:6px 22px; }"
            "QPushButton:hover { color:#fff; border-color:#444; }"
        )
        close_btn.clicked.connect(dialog.accept)
        th.addWidget(close_btn)
        root.addWidget(toolbar)

        # ── Bandeau conflits ──────────────────────────────────────────────
        conflict_banner = QLabel()
        conflict_banner.setFixedHeight(30)
        conflict_banner.setStyleSheet(
            "background:#1a0d00; color:#ffaa44; padding:0 20px; font-size:11px;"
            " border-bottom:1px solid #2e1800;"
        )
        conflict_banner.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        conflict_banner.setVisible(False)
        root.addWidget(conflict_banner)

        # ── Tabs ──────────────────────────────────────────────────────────
        tabs = QTabWidget()
        root.addWidget(tabs)

        # ════════════════════════════════════════════════════════════════
        # TAB 0 — FIXTURES  (master-detail)
        # ════════════════════════════════════════════════════════════════
        tab_fx = QWidget()
        tab_fx.setStyleSheet("background:#0f0f0f;")
        fx_root = QVBoxLayout(tab_fx)
        fx_root.setContentsMargins(0, 0, 0, 0)
        fx_root.setSpacing(0)

        spl = QSplitter(Qt.Horizontal)
        spl.setHandleWidth(1)
        spl.setStyleSheet("QSplitter::handle{background:#181818;}")

        # ── Panneau gauche : cards ────────────────────────────────────────
        left_w = QWidget()
        left_w.setMinimumWidth(240)
        left_w.setMaximumWidth(320)
        left_w.setStyleSheet("background:#090909;")
        lv = QVBoxLayout(left_w)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        filter_bar = QLineEdit()
        filter_bar.setPlaceholderText("  🔍  Filtrer...")
        filter_bar.setFixedHeight(40)
        filter_bar.setStyleSheet(
            "QLineEdit { background:#0e0e0e; color:#777; border:none;"
            " border-bottom:1px solid #181818; border-radius:0; padding:0 16px; font-size:12px; }"
            "QLineEdit:focus { color:#fff; border-bottom:1px solid #00d4ff33; }"
        )
        lv.addWidget(filter_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_w = QWidget()
        scroll_w.setStyleSheet("background:#090909;")
        card_vl = QVBoxLayout(scroll_w)
        card_vl.setContentsMargins(0, 4, 0, 4)
        card_vl.setSpacing(1)
        card_vl.addStretch()
        scroll.setWidget(scroll_w)
        lv.addWidget(scroll, 1)

        bstrip = QWidget()
        bstrip.setFixedHeight(40)
        bstrip.setStyleSheet("background:#060606; border-top:1px solid #141414;")
        bsv = QHBoxLayout(bstrip)
        bsv.setContentsMargins(8, 0, 8, 0)
        bsv.setSpacing(4)

        lbl_cnt = QLabel("")
        lbl_cnt.setStyleSheet("color:#333333; font-size:10px; padding-left:8px;")
        bsv.addWidget(lbl_cnt)
        bsv.addStretch()
        lv.addWidget(bstrip)
        spl.addWidget(left_w)

        # ── Panneau droit : formulaire d'édition ──────────────────────────
        right_w = QWidget()
        right_w.setStyleSheet("background:#0f0f0f;")
        rv = QVBoxLayout(right_w)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        no_sel_w = QWidget()
        no_sel_w.setStyleSheet("background:#0f0f0f;")
        nsl = QVBoxLayout(no_sel_w)
        nsl.setAlignment(Qt.AlignCenter)
        lbl_nosel = QLabel("← Sélectionnez une fixture\npour la modifier")
        lbl_nosel.setAlignment(Qt.AlignCenter)
        lbl_nosel.setStyleSheet("color:#1e1e1e; font-size:16px;")
        nsl.addWidget(lbl_nosel)

        detail_w = QWidget()
        detail_w.setStyleSheet("background:#0f0f0f;")

        det_hbar = QWidget()
        det_hbar.setFixedHeight(54)
        det_hbar.setStyleSheet("background:#090909; border-bottom:1px solid #181818;")
        dth = QHBoxLayout(det_hbar)
        dth.setContentsMargins(28, 0, 20, 0)
        dth.setSpacing(8)
        lbl_det_name = QLabel()
        lbl_det_name.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_det_name.setStyleSheet("color:#fff; border:none; background:transparent;")
        lbl_det_group = QLabel()
        lbl_det_group.setStyleSheet("font-size:12px; border:none; background:transparent;")
        dth.addWidget(lbl_det_name)
        dth.addWidget(lbl_det_group)
        dth.addStretch()
        btn_det_del = QPushButton("🗑  Supprimer")
        btn_det_del.setFixedHeight(30)
        btn_det_del.setStyleSheet(
            "QPushButton { background:transparent; color:#664444; border:1px solid #2e1818;"
            " border-radius:6px; padding:4px 14px; font-size:11px; }"
            "QPushButton:hover { color:#ff7777; border-color:#662222; background:#1a0808; }"
        )
        dth.addWidget(btn_det_del)

        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        form_w = QWidget()
        form_w.setStyleSheet("background:#0f0f0f;")
        fv = QVBoxLayout(form_w)
        fv.setContentsMargins(28, 22, 28, 22)
        fv.setSpacing(5)
        form_scroll.setWidget(form_w)

        def _sec(txt):
            l = QLabel(txt.upper())
            l.setStyleSheet(
                "color:#252525; font-size:9px; font-weight:bold; letter-spacing:2px;"
                " padding:10px 0 3px 0; border:none; background:transparent;"
            )
            return l

        def _hdiv():
            f = QFrame()
            f.setFrameShape(QFrame.HLine)
            f.setStyleSheet("color:#181818; max-height:1px; margin:8px 0;")
            return f

        fv.addWidget(_sec("Identité"))
        det_name_e = QLineEdit()
        det_name_e.setPlaceholderText("Nom de la fixture")
        det_name_e.setFixedHeight(44)
        det_name_e.setFont(QFont("Segoe UI", 14, QFont.Bold))
        det_name_e.setStyleSheet(
            "QLineEdit { background:#141414; color:#fff; border:1px solid #202020;"
            " border-radius:8px; padding:8px 16px; font-size:14px; }"
            "QLineEdit:focus { border:1px solid #00d4ff33; background:#14141c; }"
        )
        fv.addWidget(det_name_e)
        fv.addSpacing(6)

        tg_row = QHBoxLayout()
        tg_row.setSpacing(10)
        det_type_cb  = QComboBox()
        det_type_cb.setFixedHeight(38)
        for ft in FIXTURE_TYPES:
            det_type_cb.addItem(ft)
        det_group_cb = QComboBox()
        det_group_cb.setFixedHeight(38)
        tg_row.addWidget(det_type_cb, 1)
        tg_row.addWidget(det_group_cb, 1)
        fv.addLayout(tg_row)
        fv.addWidget(_hdiv())

        fv.addWidget(_sec("Adresse DMX"))
        addr_row = QHBoxLayout()
        addr_row.setSpacing(6)
        btn_am = QPushButton("−")
        btn_am.setFixedSize(36, 36)
        btn_am.setStyleSheet(
            "QPushButton { background:#141414; color:#555; border:1px solid #202020;"
            " border-radius:7px; font-size:19px; font-weight:bold; padding:0; }"
            "QPushButton:hover { color:#ccc; border-color:#3a3a3a; background:#1a1a1a; }"
        )
        addr_sb = QSpinBox()
        addr_sb.setRange(1, 512)
        addr_sb.setFixedHeight(36)
        addr_sb.setAlignment(Qt.AlignCenter)
        addr_sb.setFixedWidth(72)
        btn_ap = QPushButton("+")
        btn_ap.setFixedSize(36, 36)
        btn_ap.setStyleSheet(btn_am.styleSheet())
        lbl_addr_range = QLabel()
        lbl_addr_range.setStyleSheet("color:#2a2a2a; font-size:12px; padding-left:6px; border:none;")
        addr_row.addWidget(btn_am)
        addr_row.addWidget(addr_sb)
        addr_row.addWidget(btn_ap)
        addr_row.addWidget(lbl_addr_range)
        addr_row.addStretch()
        fv.addLayout(addr_row)
        lbl_conflict_det = QLabel()
        lbl_conflict_det.setStyleSheet("color:#ff6644; font-size:11px; padding:2px 0; border:none;")
        lbl_conflict_det.setVisible(False)
        fv.addWidget(lbl_conflict_det)
        fv.addWidget(_hdiv())

        fv.addWidget(_sec("Profil DMX"))
        det_profile_cb = QComboBox()
        det_profile_cb.setFixedHeight(38)
        for pname, pchannels in DMX_PROFILES.items():
            det_profile_cb.addItem(f"{pname}  —  {profile_display_text(pchannels)}", pname)
        det_profile_cb.addItem("Custom...", "__custom__")
        fv.addWidget(det_profile_cb)

        chips_w = QWidget()
        chips_w.setStyleSheet("background:transparent;")
        chips_vl = QVBoxLayout(chips_w)
        chips_vl.setContentsMargins(0, 8, 0, 0)
        chips_vl.setSpacing(4)
        fv.addWidget(chips_w)
        fv.addStretch()

        dv_outer = QVBoxLayout(detail_w)
        dv_outer.setContentsMargins(0, 0, 0, 0)
        dv_outer.setSpacing(0)
        dv_outer.addWidget(det_hbar)
        dv_outer.addWidget(form_scroll, 1)

        det_stack = QStackedWidget()
        det_stack.addWidget(no_sel_w)
        det_stack.addWidget(detail_w)
        det_stack.setCurrentIndex(0)
        rv.addWidget(det_stack, 1)

        spl.addWidget(right_w)
        spl.setSizes([280, dw - 282])
        fx_root.addWidget(spl)

        tabs.addTab(tab_fx, "📋  Fixtures")

        # ── Onglet 2 : Plan de feu ─────────────────────────────────────
        tab_canvas = QWidget()
        tab_canvas.setStyleSheet("background: #0a0a0a;")
        vl_canvas = QVBoxLayout(tab_canvas)
        vl_canvas.setContentsMargins(0, 0, 0, 0)
        vl_canvas.setSpacing(0)

        # ── Barre d'édition inline ────────────────────────────────
        _ES = (  # Selection buttons style — neutral
            "QPushButton { background:#111111; color:#4a4a4a; border:1px solid #1c1c1c;"
            " border-radius:5px; padding:3px 12px; font-size:11px; }"
            "QPushButton:hover { background:#1a1a1a; color:#888888; border-color:#2a2a2a; }"
            "QPushButton:pressed { background:#0e0e0e; }"
        )
        _EA = (  # Action buttons — blue tint
            "QPushButton { background:#0d1520; color:#4488bb; border:1px solid #1a2d40;"
            " border-radius:5px; padding:3px 14px; font-size:11px; }"
            "QPushButton:hover { background:#142030; color:#66aadd; border-color:#2a5070; }"
            "QPushButton:pressed { background:#090e18; }"
        )
        _ED = (  # Destructive button style — red
            "QPushButton { background:#130606; color:#663333; border:1px solid #220d0d;"
            " border-radius:5px; padding:3px 12px; font-size:11px; }"
            "QPushButton:hover { background:#1c0808; color:#dd4444; border-color:#551111; }"
            "QPushButton:pressed { background:#0e0404; }"
        )

        edit_strip = QWidget()
        edit_strip.setFixedHeight(42)
        edit_strip.setStyleSheet("background:#0c0c0c; border-bottom:1px solid #161616;")
        es = QHBoxLayout(edit_strip)
        es.setContentsMargins(10, 0, 10, 0)
        es.setSpacing(6)

        def _vsep():
            s = QFrame()
            s.setFrameShape(QFrame.VLine)
            s.setStyleSheet("QFrame{color:#1a1a1a;max-width:1px;margin:8px 4px;}")
            return s

        # ── Alignement ────────────────────────────────────────────────
        btn_align_row  = QPushButton("⟶  Aligner")
        btn_align_row.setToolTip("Aligner les fixtures sélectionnées sur la même ligne horizontale")
        btn_distribute = QPushButton("⟺  Centrer")
        btn_distribute.setToolTip("Centrer et répartir à espacement égal les fixtures sélectionnées")
        for b in [btn_align_row, btn_distribute]:
            b.setStyleSheet(_EA)
            b.setFixedHeight(28)
            es.addWidget(b)

        es.addWidget(_vsep())

        # ── Sélection ─────────────────────────────────────────────────
        btn_sel_all_c = QPushButton("Tout sél.")
        btn_desel_c   = QPushButton("Désél.")
        btn_groups_c  = QPushButton("Groupes  ▾")
        for b in [btn_sel_all_c, btn_desel_c, btn_groups_c]:
            b.setStyleSheet(_ES)
            b.setFixedHeight(28)
            es.addWidget(b)

        es.addStretch()

        # ── Réinitialiser positions ───────────────────────────────────
        btn_reset_pos_c = QPushButton("↺  Positions auto")
        btn_reset_pos_c.setToolTip("Remettre toutes les fixtures à leur position par défaut")
        btn_reset_pos_c.setStyleSheet(_ES)
        btn_reset_pos_c.setFixedHeight(28)
        es.addWidget(btn_reset_pos_c)

        vl_canvas.addWidget(edit_strip)

        proxy = _PatchCanvasProxy(self.projectors, self)
        canvas = FixtureCanvas(proxy)
        vl_canvas.addWidget(canvas)

        canvas_timer = QTimer(dialog)
        canvas_timer.timeout.connect(canvas.update)
        canvas_timer.start(80)

        tabs.addTab(tab_canvas, "🎭  Plan de feu")

        # ════════════════════════════════════════════════════════════════
        # DONNÉES + HELPERS
        # ════════════════════════════════════════════════════════════════
        fixture_data = []
        _sel        = [None]
        _cards      = []
        _history    = []
        _redo_stack = []

        def _rebuild_fd():
            fixture_data.clear()
            for i, proj in enumerate(self.projectors):
                fixture_data.append({
                    'name':          proj.name or proj.group,
                    'fixture_type':  getattr(proj, 'fixture_type', 'PAR LED'),
                    'group':         proj.group,
                    'start_address': proj.start_address,
                    'profile':       list(self.dmx._get_profile(f"{proj.group}_{i}")),
                })

        _rebuild_fd()

        def _push_history():
            snap = []
            for i, fd in enumerate(fixture_data):
                entry = dict(fd)
                if i < len(self.projectors):
                    p = self.projectors[i]
                    entry['canvas_x'] = getattr(p, 'canvas_x', None)
                    entry['canvas_y'] = getattr(p, 'canvas_y', None)
                snap.append(entry)
            _history.append(snap)
            _redo_stack.clear()
            if len(_history) > 40:
                _history.pop(0)

        def _snapshot_current():
            snap = []
            for i, fd in enumerate(fixture_data):
                entry = dict(fd)
                if i < len(self.projectors):
                    p = self.projectors[i]
                    entry['canvas_x'] = getattr(p, 'canvas_x', None)
                    entry['canvas_y'] = getattr(p, 'canvas_y', None)
                snap.append(entry)
            return snap

        def _restore_snap(snap):
            del self.projectors[:]
            fixture_data.clear()
            for fd_s in snap:
                p = Projector(fd_s['group'], name=fd_s['name'], fixture_type=fd_s['fixture_type'])
                p.start_address = fd_s['start_address']
                p.canvas_x = fd_s.get('canvas_x')
                p.canvas_y = fd_s.get('canvas_y')
                if p.fixture_type == "Machine a fumee":
                    p.fan_speed = 0
                self.projectors.append(p)
                fixture_data.append({
                    'name':          fd_s['name'],
                    'fixture_type':  fd_s['fixture_type'],
                    'group':         fd_s['group'],
                    'start_address': fd_s['start_address'],
                    'profile':       fd_s.get('profile', []),
                })
            self._rebuild_dmx_patch()
            _build_cards(filter_bar.text())
            _sel[0] = None
            det_stack.setCurrentIndex(0)
            proxy.selected_lamps.clear()
            canvas.update()

        def _undo():
            if not _history: return
            _redo_stack.append(_snapshot_current())
            _restore_snap(_history.pop())

        def _redo():
            if not _redo_stack: return
            _history.append(_snapshot_current())
            _restore_snap(_redo_stack.pop())

        def _get_conflicts():
            occ = {}
            for i, fd in enumerate(fixture_data):
                for c in range(fd['start_address'], fd['start_address'] + len(fd['profile'])):
                    occ.setdefault(c, []).append(i)
            return {i for lst in occ.values() if len(lst) > 1 for i in lst}

        def _update_conflict_banner(conflicts):
            if conflicts and tabs.currentIndex() == 0:
                n = len(conflicts)
                conflict_banner.setText(
                    f"  ⚠  {n} fixture{'s' if n > 1 else ''} avec des canaux DMX qui se chevauchent"
                    "  —  utilisez ⚡ Auto-addr. pour corriger"
                )
                conflict_banner.setVisible(True)
            else:
                conflict_banner.setVisible(False)

        tabs.currentChanged.connect(lambda _: _update_conflict_banner(_get_conflicts()))
        def _update_chips(profile):
            while chips_vl.count():
                item = chips_vl.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if not profile:
                return
            row_n = QWidget(); row_n.setStyleSheet("background:transparent;")
            rn = QHBoxLayout(row_n); rn.setContentsMargins(0, 0, 0, 0); rn.setSpacing(4)
            row_u = QWidget(); row_u.setStyleSheet("background:transparent;")
            ru = QHBoxLayout(row_u); ru.setContentsMargins(0, 0, 0, 0); ru.setSpacing(4)
            for ci, ch in enumerate(profile):
                col = CH_COLORS.get(ch, "#444455")
                cw = max(36, len(ch) * 7 + 14)
                # Calcul luminance pour choisir texte blanc ou noir
                _r = int(col[1:3], 16); _g = int(col[3:5], 16); _b = int(col[5:7], 16)
                text_col = "#ffffff" if (_r * 0.299 + _g * 0.587 + _b * 0.114) < 145 else "#111111"
                chip = QLabel(ch)
                chip.setFixedSize(cw, 24)
                chip.setAlignment(Qt.AlignCenter)
                chip.setStyleSheet(
                    f"background:{col}; color:{text_col}; border:none;"
                    f" border-radius:5px; font-size:10px; font-weight:bold;"
                )
                chip.setToolTip(f"Canal {ci + 1}: {ch}")
                num = QLabel(str(ci + 1))
                num.setFixedWidth(cw)
                num.setAlignment(Qt.AlignCenter)
                num.setStyleSheet(f"color:{col}; font-size:9px; font-weight:bold; border:none; background:transparent;")
                rn.addWidget(chip); ru.addWidget(num)
            rn.addStretch(); ru.addStretch()
            chips_vl.addWidget(row_n)
            chips_vl.addWidget(row_u)
        def _populate_group_combo():
            det_group_cb.blockSignals(True)
            det_group_cb.clear()
            seen = []
            for g in list(self.GROUP_DISPLAY.keys()) + ["lyre", "barre", "strobe"]:
                if g not in seen:
                    seen.append(g)
            for fd_item in fixture_data:
                if fd_item['group'] not in seen:
                    seen.append(fd_item['group'])
            for g in seen:
                letter  = GROUP_LETTERS.get(g, "")
                name    = self.GROUP_DISPLAY.get(g, g)
                display = f"{letter}  —  {name}" if letter else name
                det_group_cb.addItem(display, g)
            det_group_cb.blockSignals(False)

        def _update_addr_range():
            if _sel[0] is None or _sel[0] >= len(fixture_data):
                return
            fd  = fixture_data[_sel[0]]
            n   = len(fd['profile'])
            end = addr_sb.value() + n - 1
            if end > 512:
                lbl_addr_range.setText(f"→ CH {end}  ⚠ dépasse 512 !")
                lbl_addr_range.setStyleSheet("color:#ff6644; font-size:12px; padding-left:6px; border:none;")
            else:
                lbl_addr_range.setText(f"→ CH {end}   ({n} canal{'x' if n > 1 else ''})")
                lbl_addr_range.setStyleSheet("color:#2a2a2a; font-size:12px; padding-left:6px; border:none;")
        def _make_card(idx):
            fd    = fixture_data[idx]
            group = fd['group']
            gc    = _GC.get(group, "#666666")
            end_ch = fd['start_address'] + len(fd['profile']) - 1
            gname  = self.GROUP_DISPLAY.get(group, group)

            card = QFrame()
            card.setFixedHeight(60)
            card.setCursor(Qt.PointingHandCursor)

            def _upd(selected, conflict):
                _gc = card._gc  # lu dynamiquement pour refléter les changements de groupe
                bg = "#10102a" if selected else "#0b0b0b"
                card.setStyleSheet(
                    f"QFrame {{ background:{bg}; border-left:4px solid {_gc};"
                    f" border-top:1px solid {'#1e1e3a' if selected else '#141414'};"
                    f" border-bottom:1px solid #141414; border-right:none; border-radius:0; }}"
                )
                if hasattr(card, '_chlbl'):
                    card._chlbl.setStyleSheet(
                        f"color:{'#ff6644' if conflict else '#33ddff' if selected else '#00d4ff'};"
                        f" font-size:11px; font-weight:bold; border:none; background:transparent;"
                    )

            card._gc  = gc   # doit être défini avant le premier appel à _upd
            card._upd = _upd
            card._upd(False, False)

            hl = QHBoxLayout(card)
            hl.setContentsMargins(12, 0, 14, 0)
            hl.setSpacing(8)

            dot = QLabel("●")
            dot.setFixedWidth(13)
            dot.setAlignment(Qt.AlignCenter)
            dot.setStyleSheet("color:#1c1c1c; font-size:13px; border:none; background:transparent;")
            card._dot = dot
            hl.addWidget(dot)

            tv = QVBoxLayout()
            tv.setSpacing(2)
            tv.setContentsMargins(0, 0, 0, 0)
            nm = QLabel(fd['name'] or fd['group'])
            nm.setFont(QFont("Segoe UI", 11, QFont.Bold))
            nm.setStyleSheet("color:#ddd; font-size:12px; font-weight:bold; border:none; background:transparent;")
            card._namelbl = nm
            sub = QLabel(f"{fd['fixture_type']}  ·  {gname}")
            # Couleur tintee du groupe mais lisible (melange gc + gris neutre)
            _sub_col = "#{:02x}{:02x}{:02x}".format(
                (int(gc[1:3], 16) + 0x44) // 2,
                (int(gc[3:5], 16) + 0x44) // 2,
                (int(gc[5:7], 16) + 0x44) // 2,
            ) if len(gc) == 7 else "#545454"
            sub.setStyleSheet(f"color:{_sub_col}; font-size:10px; border:none; background:transparent;")
            card._sublbl_color = _sub_col
            card._sublbl = sub
            tv.addWidget(nm); tv.addWidget(sub)
            hl.addLayout(tv)
            hl.addStretch()

            chl = QLabel(f"CH {fd['start_address']}–{end_ch}")
            chl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            chl.setStyleSheet("color:#00d4ff; font-size:11px; font-weight:bold; border:none; background:transparent;")
            card._chlbl = chl
            hl.addWidget(chl)

            card.mousePressEvent = lambda e, i=idx: _select_card(i)
            return card
        def _build_cards(filter_text=""):
            while card_vl.count() > 1:
                item = card_vl.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            _cards.clear()
            ft = filter_text.strip().lower()
            conflicts = _get_conflicts()
            for idx, fd in enumerate(fixture_data):
                if ft:
                    hay = (fd['name'] + fd['fixture_type'] +
                           self.GROUP_DISPLAY.get(fd['group'], fd['group'])).lower()
                    if ft not in hay:
                        _cards.append(None)
                        continue
                card = _make_card(idx)
                card._upd(idx == _sel[0], idx in conflicts)
                _cards.append(card)
                card_vl.insertWidget(card_vl.count() - 1, card)
            n = len(fixture_data)
            lbl_cnt.setText(f"{n} fixture{'s' if n != 1 else ''}")
            _update_conflict_banner(conflicts)
        def _select_card(idx):
            if _sel[0] is not None and _sel[0] < len(_cards):
                old = _cards[_sel[0]]
                if old is not None:
                    old._upd(False, _sel[0] in _get_conflicts())
            _sel[0] = idx
            if idx is None:
                det_stack.setCurrentIndex(0)
                return
            conflicts = _get_conflicts()
            if idx < len(_cards) and _cards[idx] is not None:
                _cards[idx]._upd(True, idx in conflicts)
            det_stack.setCurrentIndex(1)
            fd = fixture_data[idx]
            gc = _GC.get(fd['group'], "#888")
            lbl_det_name.setText(fd['name'] or fd['group'])
            lbl_det_group.setText(f"  {self.GROUP_DISPLAY.get(fd['group'], fd['group'])}")
            lbl_det_group.setStyleSheet(f"color:{gc}; font-size:12px; border:none; background:transparent;")
            det_name_e.blockSignals(True);  det_name_e.setText(fd['name']);  det_name_e.blockSignals(False)
            det_type_cb.blockSignals(True)
            if fd['fixture_type'] in FIXTURE_TYPES:
                det_type_cb.setCurrentIndex(FIXTURE_TYPES.index(fd['fixture_type']))
            det_type_cb.blockSignals(False)
            _populate_group_combo()
            det_group_cb.blockSignals(True)
            for i in range(det_group_cb.count()):
                if det_group_cb.itemData(i) == fd['group']:
                    det_group_cb.setCurrentIndex(i); break
            det_group_cb.blockSignals(False)
            addr_sb.blockSignals(True);  addr_sb.setValue(fd['start_address']);  addr_sb.blockSignals(False)
            _update_addr_range()
            det_profile_cb.blockSignals(True)
            pn = profile_name(fd['profile'])
            if pn:
                pi = det_profile_cb.findData(pn)
                if pi >= 0:
                    det_profile_cb.setCurrentIndex(pi)
            else:
                det_profile_cb.setCurrentIndex(det_profile_cb.findData("__custom__"))
            det_profile_cb.blockSignals(False)
            _update_chips(fd['profile'])
            if idx in conflicts:
                others = []
                for j, fd2 in enumerate(fixture_data):
                    if j == idx: continue
                    s1, e1 = fd['start_address'], fd['start_address'] + len(fd['profile']) - 1
                    s2, e2 = fd2['start_address'], fd2['start_address'] + len(fd2['profile']) - 1
                    if s1 <= e2 and s2 <= e1:
                        others.append(fd2['name'] or fd2['group'])
                lbl_conflict_det.setText(f"⚠  Chevauchement avec : {", ".join(others)}")
                lbl_conflict_det.setVisible(True)
            else:
                lbl_conflict_det.setVisible(False)
            if idx < len(_cards) and _cards[idx] is not None:
                scroll.ensureWidgetVisible(_cards[idx])
        def _commit():
            idx = _sel[0]
            if idx is None or idx >= len(fixture_data): return
            _push_history()
            fd   = fixture_data[idx]
            proj = self.projectors[idx]
            fd['name']          = det_name_e.text().strip() or fd['group']
            fd['fixture_type']  = det_type_cb.currentText()
            fd['group']         = det_group_cb.currentData() or fd['group']
            fd['start_address'] = addr_sb.value()
            proj.name           = fd['name']
            proj.fixture_type   = fd['fixture_type']
            proj.group          = fd['group']
            proj.start_address  = fd['start_address']
            self._rebuild_dmx_patch()
            self.save_dmx_patch_config()
            conflicts = _get_conflicts()
            _update_conflict_banner(conflicts)
            # Mettre à jour TOUTES les cartes affectées (sélectionnée + celles en conflit)
            for ci, c2 in enumerate(_cards):
                if c2 is not None and ci != idx:
                    c2._upd(False, ci in conflicts)
            if idx < len(_cards) and _cards[idx] is not None:
                card = _cards[idx]
                # Mettre a jour la couleur de groupe (bordure + sous-titre)
                new_gc = _GC.get(fd['group'], "#666666")
                card._gc = new_gc
                _sub_col = "#{:02x}{:02x}{:02x}".format(
                    (int(new_gc[1:3], 16) + 0x44) // 2,
                    (int(new_gc[3:5], 16) + 0x44) // 2,
                    (int(new_gc[5:7], 16) + 0x44) // 2,
                ) if len(new_gc) == 7 else "#545454"
                card._namelbl.setText(fd['name'])
                card._sublbl.setText(
                    f"{fd['fixture_type']}  ·  {self.GROUP_DISPLAY.get(fd['group'], fd['group'])}"
                )
                card._sublbl.setStyleSheet(
                    f"color:{_sub_col}; font-size:10px; border:none; background:transparent;"
                )
                end_ch = fd['start_address'] + len(fd['profile']) - 1
                card._chlbl.setText(f"CH {fd['start_address']}–{end_ch}")
                card._upd(True, idx in conflicts)
            lbl_det_name.setText(fd['name'])
            gc = _GC.get(fd['group'], "#888")
            lbl_det_group.setText(f"  {self.GROUP_DISPLAY.get(fd['group'], fd['group'])}")
            lbl_det_group.setStyleSheet(f"color:{gc}; font-size:12px; border:none; background:transparent;")
            _update_addr_range()
            if idx in conflicts:
                others = []
                for j, fd2 in enumerate(fixture_data):
                    if j == idx: continue
                    s1, e1 = fd['start_address'], fd['start_address'] + len(fd['profile']) - 1
                    s2, e2 = fd2['start_address'], fd2['start_address'] + len(fd2['profile']) - 1
                    if s1 <= e2 and s2 <= e1:
                        others.append(fd2['name'] or fd2['group'])
                lbl_conflict_det.setText(f"⚠  Chevauchement avec : {", ".join(others)}")
                lbl_conflict_det.setVisible(True)
            else:
                lbl_conflict_det.setVisible(False)
        _name_tmr = QTimer(dialog)
        _name_tmr.setSingleShot(True)
        _name_tmr.setInterval(500)
        _name_tmr.timeout.connect(_commit)
        det_name_e.textChanged.connect(lambda _: _name_tmr.start())
        det_type_cb.currentIndexChanged.connect(lambda _: _commit())
        det_group_cb.currentIndexChanged.connect(lambda _: _commit())
        addr_sb.valueChanged.connect(lambda _: (_update_addr_range(), _commit()))
        btn_am.clicked.connect(lambda: addr_sb.setValue(max(1, addr_sb.value() - 1)))
        btn_ap.clicked.connect(lambda: addr_sb.setValue(min(512, addr_sb.value() + 1)))

        def _on_profile_changed(_):
            data = det_profile_cb.currentData()
            i = _sel[0]
            if i is None or i >= len(fixture_data): return
            if data == "__custom__":
                custom = self._show_custom_profile_dialog(fixture_data[i]['profile'])
                if custom:
                    fixture_data[i]['profile'] = custom
                prev = profile_name(fixture_data[i]['profile'])
                pi2  = det_profile_cb.findData(prev) if prev else -1
                det_profile_cb.blockSignals(True)
                det_profile_cb.setCurrentIndex(pi2 if pi2 >= 0 else det_profile_cb.findData("__custom__"))
                det_profile_cb.blockSignals(False)
            elif data in DMX_PROFILES:
                fixture_data[i]['profile'] = list(DMX_PROFILES[data])
            self._rebuild_dmx_patch()
            self.save_dmx_patch_config()
            _update_chips(fixture_data[i]['profile'])
            _update_addr_range()
            conflicts = _get_conflicts()
            _update_conflict_banner(conflicts)
            if i < len(_cards) and _cards[i] is not None:
                end_ch = fixture_data[i]['start_address'] + len(fixture_data[i]['profile']) - 1
                _cards[i]._chlbl.setText(f"CH {fixture_data[i]['start_address']}–{end_ch}")
                _cards[i]._upd(True, i in conflicts)

        det_profile_cb.currentIndexChanged.connect(_on_profile_changed)
        def _del_selected():
            idx = _sel[0]
            if idx is None or idx >= len(fixture_data): return
            fname = fixture_data[idx]['name']
            if QMessageBox.question(
                dialog, "Supprimer", f"Supprimer « {fname} » ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes: return
            _push_history()
            fixture_data.pop(idx)
            if 0 <= idx < len(self.projectors):
                self.projectors.pop(idx)
            _sel[0] = None
            self._rebuild_dmx_patch()
            _rebuild_fd()
            _build_cards(filter_bar.text())
            det_stack.setCurrentIndex(0)

        btn_det_del.clicked.connect(_del_selected)

        def _update_dots():
            for i, card in enumerate(_cards):
                if card is None or i >= len(self.projectors): continue
                proj = self.projectors[i]
                if proj.muted or proj.level == 0:
                    col = "#1c1c1c"
                else:
                    col = proj.color.name() if hasattr(proj, 'color') and proj.color.isValid() else card._gc
                card._dot.setStyleSheet(
                    f"color:{col}; font-size:13px; border:none; background:transparent;"
                )
        def _add_fixture():
            preset = self._show_fixture_library_dialog()
            if not preset: return
            _push_history()
            _CH = {"PAR LED": 5, "Moving Head": 8, "Barre LED": 5,
                   "Stroboscope": 2, "Machine a fumee": 2}
            next_addr = 1
            if self.projectors:
                last = max(self.projectors, key=lambda p: p.start_address)
                next_addr = last.start_address + _CH.get(getattr(last, 'fixture_type', 'PAR LED'), 5)
            p = Projector(
                preset.get('group', 'face'),
                name=preset.get('name', 'Fixture'),
                fixture_type=preset.get('fixture_type', 'PAR LED')
            )
            p.start_address = next_addr
            p.canvas_x = 0.5; p.canvas_y = 0.5
            if p.fixture_type == "Machine a fumee":
                p.fan_speed = 0
            self.projectors.append(p)
            self._rebuild_dmx_patch()
            _rebuild_fd()
            new_idx = len(fixture_data) - 1
            _build_cards(filter_bar.text())
            _select_card(new_idx)
        def _auto_address():
            if QMessageBox.question(
                dialog, "Auto-adresser",
                "Recalculer automatiquement toutes les adresses DMX ?\n"
                "Les adresses seront réassignées de façon continue, sans espaces.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes: return
            _push_history()
            addr = 1
            for fd in fixture_data:
                fd['start_address'] = addr
                addr += len(fd['profile'])
                if addr > 512: addr = 512
            for proj, fd in zip(self.projectors, fixture_data):
                proj.start_address = fd['start_address']
            self._rebuild_dmx_patch()
            self.save_dmx_patch_config()
            cur = _sel[0]
            _build_cards(filter_bar.text())
            if cur is not None: _select_card(cur)
        def _reset_defaults():
            if QMessageBox.question(
                dialog, "Réinitialiser",
                "Réinitialiser les fixtures par défaut ?\nToutes les modifications seront perdues.",
                QMessageBox.Yes | QMessageBox.No
            ) != QMessageBox.Yes: return
            _push_history()
            self.projectors.clear()
            addr = 1
            for name, ftype, group in self._DEFAULT_FIXTURES:
                p = Projector(group, name=name, fixture_type=ftype)
                profile = list(DMX_PROFILES["2CH_FUMEE"] if group == "fumee" else DMX_PROFILES["RGBDS"])
                p.start_address = addr
                addr += len(profile)
                self.projectors.append(p)
            self.projectors[-1].fan_speed = 0
            self._rebuild_dmx_patch()
            _rebuild_fd()
            _sel[0] = None
            _build_cards()
            det_stack.setCurrentIndex(0)
        def _open_wizard():
            if self.projectors:
                if QMessageBox.question(
                    dialog, "Nouveau plan de feu",
                    f"Cette action remplacera les {len(self.projectors)} fixture(s) existante(s).\n"
                    "Continuer vers l'assistant ?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                ) != QMessageBox.Yes: return
            wiz = NewPlanWizard(dialog)
            if wiz.exec() != QDialog.Accepted: return
            fixtures = wiz.get_result()
            if not fixtures: return
            _push_history()
            self.projectors.clear()
            for fdd in fixtures:
                p = Projector(fdd['group'], name=fdd['name'], fixture_type=fdd['fixture_type'])
                p.start_address = fdd['start_address']
                p.canvas_x = None; p.canvas_y = None
                if fdd['fixture_type'] == "Machine a fumee":
                    p.fan_speed = 0
                self.projectors.append(p)
            self._rebuild_dmx_patch()
            _rebuild_fd()
            _sel[0] = None
            _build_cards()
            det_stack.setCurrentIndex(0)

        act_new.triggered.connect(_open_wizard)
        act_save.triggered.connect(self.save_dmx_patch_config)
        act_dflt.triggered.connect(_reset_defaults)
        act_undo.triggered.connect(_undo)
        act_redo.triggered.connect(_redo)
        act_auto.triggered.connect(_auto_address)
        btn_add.clicked.connect(_add_fixture)
        filter_bar.textChanged.connect(lambda txt: _build_cards(txt))
        def _get_selected_projs():
            if not proxy.selected_lamps:
                return list(self.projectors)
            g_cnt = {}; result = []
            for proj in self.projectors:
                li = g_cnt.get(proj.group, 0)
                if (proj.group, li) in proxy.selected_lamps:
                    result.append(proj)
                g_cnt[proj.group] = li + 1
            return result if result else list(self.projectors)

        def _align_row():
            """Aligner toutes les fixtures sélectionnées sur la même ligne horizontale (Y moyen)"""
            projs = _get_selected_projs()
            if not projs: return
            avg_y = sum(getattr(p, 'canvas_y', 0.5) or 0.5 for p in projs) / len(projs)
            for p in projs: p.canvas_y = avg_y
            canvas.update(); self.save_dmx_patch_config()

        def _distribute():
            """Centrer le groupe sur le canvas et répartir à espacement égal"""
            projs = _get_selected_projs(); n = len(projs)
            if not n: return
            if n == 1:
                projs[0].canvas_x = 0.5
            else:
                sorted_p = sorted(projs, key=lambda p: getattr(p, 'canvas_x', 0.5) or 0.5)
                mg = 0.15  # 15% de marge de chaque cote -> etalement centré sur 0.5
                for i, p in enumerate(sorted_p):
                    p.canvas_x = max(0.07, min(0.93, mg + i * (1.0 - 2 * mg) / (n - 1)))
            canvas.update(); self.save_dmx_patch_config()

        btn_align_row.clicked.connect(_align_row)
        btn_distribute.clicked.connect(_distribute)
        def _select_all_canvas():
            g_cnt = {}
            for p in self.projectors:
                li = g_cnt.get(p.group, 0)
                proxy.selected_lamps.add((p.group, li)); g_cnt[p.group] = li + 1
            canvas.update()

        def _deselect_canvas():
            proxy.selected_lamps.clear(); canvas.update()

        def _show_groups_popup():
            _MS = ("QMenu{background:#1e1e1e;border:1px solid #3a3a3a;border-radius:6px;"
                   "padding:6px;color:white;font-size:11px;}"
                   "QMenu::item{padding:6px 20px;border-radius:3px;}"
                   "QMenu::item:selected{background:#333;}")
            m = QMenu(btn_groups_c); m.setStyleSheet(_MS)
            seen = []
            for p in self.projectors:
                if p.group not in seen: seen.append(p.group)
            if not seen: return
            for g in seen:
                act = m.addAction(self.GROUP_DISPLAY.get(g, g))
                act.triggered.connect(lambda checked, grp=g: _sel_group_canvas(grp))
            m.exec(btn_groups_c.mapToGlobal(QPoint(0, btn_groups_c.height())))

        def _sel_group_canvas(grp):
            proxy.selected_lamps.clear()
            g_cnt = {}
            for p in self.projectors:
                li = g_cnt.get(p.group, 0)
                if p.group == grp: proxy.selected_lamps.add((p.group, li))
                g_cnt[p.group] = li + 1
            canvas.update()
        def _delete_canvas_selection():
            n = len(proxy.selected_lamps)
            if not n: return
            if QMessageBox.question(
                dialog, "Supprimer",
                f"Supprimer {n} fixture{'s' if n > 1 else ''} sélectionnée{'s' if n > 1 else ''} ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes: return
            _push_history()
            g_cnt = {}; to_rm = set()
            for i, proj in enumerate(self.projectors):
                li = g_cnt.get(proj.group, 0)
                if (proj.group, li) in proxy.selected_lamps: to_rm.add(i)
                g_cnt[proj.group] = li + 1
            for i in sorted(to_rm, reverse=True): self.projectors.pop(i)
            proxy.selected_lamps.clear()
            self._rebuild_dmx_patch(); _rebuild_fd()
            _build_cards(filter_bar.text()); canvas.update()

        def _reset_canvas_positions():
            if QMessageBox.question(
                dialog, "Réinitialiser les positions",
                "Remettre toutes les fixtures à leur position automatique ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes: return
            _push_history()
            for proj in self.projectors: proj.canvas_x = None; proj.canvas_y = None
            self.save_dmx_patch_config(); canvas.update()
        btn_sel_all_c.clicked.connect(_select_all_canvas)
        btn_desel_c.clicked.connect(_deselect_canvas)
        btn_groups_c.clicked.connect(_show_groups_popup)
        btn_reset_pos_c.clicked.connect(_reset_canvas_positions)

        proxy._add_cb             = _add_fixture
        proxy._wizard_cb          = _open_wizard
        proxy._align_row_cb       = _align_row
        proxy._distribute_cb      = _distribute
        proxy._select_fixture_cb  = lambda idx: (tabs.setCurrentIndex(0), _select_card(idx))

        canvas_timer = QTimer(dialog)

        def _timer_tick():
            canvas.update()
            _update_dots()

        canvas_timer.timeout.connect(_timer_tick)
        canvas_timer.start(80)

        # Ctrl+Z sur le dialog
        def _dialog_key(event):
            if event.key() == Qt.Key_Z and (event.modifiers() & Qt.ControlModifier):
                _undo()
            elif event.key() == Qt.Key_Y and (event.modifiers() & Qt.ControlModifier):
                _redo()
            else:
                type(dialog).keyPressEvent(dialog, event)
        dialog.keyPressEvent = _dialog_key

        _build_cards()
        if fixture_data:
            _select_card(0)

        dialog.exec()
        canvas_timer.stop()

    def _show_fixture_library_dialog(self):
        """Dialog bibliotheque de fixtures. Retourne un dict preset ou None."""
        from PySide6.QtWidgets import QListWidget, QSplitter

        FIXTURE_LIBRARY = {
            "PAR LED": [
                {"name": "PAR LED RGB 3ch", "fixture_type": "PAR LED", "profile": "RGB", "group": "face"},
                {"name": "PAR LED RGBDS 5ch", "fixture_type": "PAR LED", "profile": "RGBDS", "group": "face"},
                {"name": "PAR LED RGBWD 5ch", "fixture_type": "PAR LED", "profile": "RGBWD", "group": "face"},
                {"name": "PAR LED RGBWDS 6ch", "fixture_type": "PAR LED", "profile": "RGBWDS", "group": "face"},
            ],
            "Lyre": [
                {"name": "Lyre Spot 8ch", "fixture_type": "Moving Head", "profile": "MOVING_8CH", "group": "lyre"},
                {"name": "Lyre Wash RGB 8ch", "fixture_type": "Moving Head", "profile": "MOVING_RGB", "group": "lyre"},
                {"name": "Lyre Wash RGBW 9ch", "fixture_type": "Moving Head", "profile": "MOVING_RGBW", "group": "lyre"},
                {"name": "Lyre Spot 5ch", "fixture_type": "Moving Head", "profile": "MOVING_5CH", "group": "lyre"},
            ],
            "Barre LED": [
                {"name": "Barre LED RGB 5ch", "fixture_type": "Barre LED", "profile": "LED_BAR_RGB", "group": "barre"},
            ],
            "Stroboscope": [
                {"name": "Strobe 2ch", "fixture_type": "Stroboscope", "profile": "STROBE_2CH", "group": "strobe"},
            ],
            "Machine a fumee": [
                {"name": "Machine a fumee 2ch", "fixture_type": "Machine a fumee", "profile": "2CH_FUMEE", "group": "fumee"},
            ],
        }

        dialog = QDialog(self)
        dialog.setWindowTitle("Bibliotheque de fixtures")
        dialog.setMinimumSize(500, 380)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a1a; color: #e0e0e0; }
            QListWidget { background: #222; color: #e0e0e0; border: 1px solid #3a3a3a; border-radius: 4px; }
            QListWidget::item { padding: 6px 10px; }
            QListWidget::item:selected { background: #00d4ff; color: #000; }
            QListWidget::item:hover { background: #2a2a2a; }
            QPushButton { background: #2a2a2a; color: #ccc; border: 1px solid #4a4a4a; border-radius: 4px; padding: 6px 14px; }
            QPushButton:hover { border: 1px solid #00d4ff; }
            QLabel { color: #e0e0e0; }
            QSplitter::handle { background: #3a3a3a; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title_lbl = QLabel("Choisir une fixture a ajouter")
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        splitter = QSplitter(Qt.Horizontal)

        cat_list = QListWidget()
        for cat in FIXTURE_LIBRARY.keys():
            cat_list.addItem(cat)
        cat_list.setMaximumWidth(160)
        splitter.addWidget(cat_list)

        preset_list = QListWidget()
        splitter.addWidget(preset_list)

        layout.addWidget(splitter)

        result = [None]

        def on_cat_changed():
            preset_list.clear()
            cat = cat_list.currentItem()
            if not cat:
                return
            for preset in FIXTURE_LIBRARY.get(cat.text(), []):
                preset_list.addItem(preset['name'])

        cat_list.currentItemChanged.connect(on_cat_changed)
        if FIXTURE_LIBRARY:
            cat_list.setCurrentRow(0)

        def accept():
            cat = cat_list.currentItem()
            preset_item = preset_list.currentItem()
            if not cat or not preset_item:
                return
            for p in FIXTURE_LIBRARY.get(cat.text(), []):
                if p['name'] == preset_item.text():
                    result[0] = p
                    break
            dialog.accept()

        preset_list.itemDoubleClicked.connect(lambda _: accept())

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Ajouter")
        ok_btn.setStyleSheet("QPushButton { background: #00d4ff; color: #000; font-weight: bold; padding: 8px 24px; } QPushButton:hover { background: #33ddff; }")
        cancel_b = QPushButton("Annuler")
        ok_btn.clicked.connect(accept)
        cancel_b.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_b)
        layout.addLayout(btn_row)

        dialog.exec()
        return result[0]

    def _show_custom_profile_dialog(self, initial=None):
        """Dialog pour composer un profil DMX custom. Retourne la liste ou None si annule."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Profil DMX Custom")
        dialog.setFixedSize(400, 420)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a1a; color: #e0e0e0; }
            QLabel { color: #e0e0e0; }
            QPushButton {
                background: #2a2a2a; color: #ffffff; border: 1px solid #4a4a4a;
                border-radius: 4px; padding: 6px 12px; font-size: 12px;
            }
            QPushButton:hover { border: 1px solid #00d4ff; background: #333; }
            QListWidget {
                background: #222; color: #fff; border: 1px solid #4a4a4a;
                border-radius: 4px; font-size: 13px; font-family: 'Consolas';
            }
            QListWidget::item:selected { background: #00d4ff; color: #000; }
            QComboBox {
                background: #2a2a2a; color: #ffffff;
                border: 1px solid #4a4a4a; border-radius: 4px;
                padding: 4px 8px; font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background: #2a2a2a; color: #ffffff;
                border: 1px solid #4a4a4a; selection-background-color: #00d4ff;
                selection-color: #000000;
            }
        """)

        from PySide6.QtWidgets import QListWidget

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Composer le profil")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Liste des canaux du profil
        list_widget = QListWidget()
        if initial:
            for ch in initial:
                list_widget.addItem(ch)
        layout.addWidget(list_widget)

        # Ajout d'un type de canal
        add_row = QHBoxLayout()
        type_combo = QComboBox()
        for ct in CHANNEL_TYPES:
            type_combo.addItem(ct)
        add_row.addWidget(type_combo)

        add_btn = QPushButton("Ajouter")
        add_btn.setStyleSheet("QPushButton { background: #00d4ff; color: #000; font-weight: bold; } QPushButton:hover { background: #33ddff; }")

        def add_channel():
            ch = type_combo.currentText()
            existing = [list_widget.item(r).text() for r in range(list_widget.count())]
            if ch in existing:
                QMessageBox.warning(dialog, "Doublon", f"Le canal '{ch}' est deja dans le profil.")
                return
            list_widget.addItem(ch)

        add_btn.clicked.connect(add_channel)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        # Boutons monter / descendre / supprimer
        action_row = QHBoxLayout()
        up_btn = QPushButton("Monter")
        down_btn = QPushButton("Descendre")
        del_btn = QPushButton("Supprimer")
        del_btn.setStyleSheet("QPushButton { background: #662222; color: #ff8888; border: 1px solid #883333; } QPushButton:hover { background: #883333; }")

        def move_item(direction):
            row = list_widget.currentRow()
            if row < 0:
                return
            new_row = row + direction
            if 0 <= new_row < list_widget.count():
                item = list_widget.takeItem(row)
                list_widget.insertItem(new_row, item)
                list_widget.setCurrentRow(new_row)

        up_btn.clicked.connect(lambda: move_item(-1))
        down_btn.clicked.connect(lambda: move_item(1))
        del_btn.clicked.connect(lambda: list_widget.takeItem(list_widget.currentRow()) if list_widget.currentRow() >= 0 else None)

        action_row.addWidget(up_btn)
        action_row.addWidget(down_btn)
        action_row.addWidget(del_btn)
        layout.addLayout(action_row)

        # Preview
        preview_label = QLabel("")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_label.setStyleSheet("color: #888; font-family: 'Consolas'; font-size: 12px; padding: 6px;")
        layout.addWidget(preview_label)

        def update_preview():
            items = [list_widget.item(r).text() for r in range(list_widget.count())]
            preview_label.setText("  ".join(items) if items else "(vide)")

        list_widget.model().rowsInserted.connect(update_preview)
        list_widget.model().rowsRemoved.connect(update_preview)
        list_widget.model().rowsMoved.connect(update_preview)
        update_preview()

        # OK / Annuler
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet("QPushButton { background: #00d4ff; color: #000; font-weight: bold; padding: 8px 24px; } QPushButton:hover { background: #33ddff; }")
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet("QPushButton { padding: 8px 24px; }")

        result = [None]

        def accept():
            items = [list_widget.item(r).text() for r in range(list_widget.count())]
            if not items:
                QMessageBox.warning(dialog, "Profil vide", "Le profil doit contenir au moins 1 canal.")
                return
            result[0] = items
            dialog.accept()

        ok_btn.clicked.connect(accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        dialog.exec()
        return result[0]

    def _ask_custom_profile_name(self):
        """Demande un nom court (max 8 car.) pour un profil custom. Retourne le nom ou None."""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, "Nom du profil",
            "Nom du profil (8 caracteres max) :",
        )
        if ok and name:
            name = name.strip()[:8]
            if name:
                return name
        return None

    def apply_dmx_modes(self, dialog, fixture_data):
        """Applique les fixtures configurees"""
        if not fixture_data:
            QMessageBox.warning(dialog, "Aucune fixture", "La liste de fixtures est vide.")
            return

        # Reconstruire self.projectors depuis fixture_data
        self.projectors = []
        for fd in fixture_data:
            p = Projector(fd['group'], name=fd['name'], fixture_type=fd['fixture_type'])
            p.start_address = fd['start_address']
            if fd['fixture_type'] == "Machine a fumee":
                p.fan_speed = 0
            self.projectors.append(p)

        # Mettre a jour le patch DMX
        self.dmx.clear_patch()
        for i, (proj, fd) in enumerate(zip(self.projectors, fixture_data)):
            proj_key = f"{proj.group}_{i}"
            profile = fd['profile']
            nb_ch = len(profile)
            channels = [proj.start_address + c for c in range(nb_ch)]
            self.dmx.set_projector_patch(proj_key, channels, profile=profile)

        self.save_dmx_patch_config()
        QMessageBox.information(dialog, "Patch applique",
            "Fixtures DMX appliquees avec succes !")
        dialog.accept()

    def _rebuild_dmx_patch(self):
        """Reconstruit le patch DMX depuis self.projectors et sauvegarde"""
        self.dmx.clear_patch()
        for i, proj in enumerate(self.projectors):
            proj_key = f"{proj.group}_{i}"
            ftype = getattr(proj, 'fixture_type', 'PAR LED')
            if ftype == "Machine a fumee" or proj.group == "fumee":
                profile = list(DMX_PROFILES["2CH_FUMEE"])
            elif ftype == "Moving Head":
                profile = list(DMX_PROFILES["MOVING_8CH"])
            elif ftype == "Barre LED":
                profile = list(DMX_PROFILES["LED_BAR_RGB"])
            elif ftype == "Stroboscope":
                profile = list(DMX_PROFILES["STROBE_2CH"])
            else:
                profile = list(DMX_PROFILES["RGBDS"])
            channels = [proj.start_address + c for c in range(len(profile))]
            self.dmx.set_projector_patch(proj_key, channels, profile=profile)
        self.save_dmx_patch_config()

    def save_dmx_patch_config(self):
        """Sauvegarde la configuration du patch DMX (nouveau format avec fixtures)"""
        fixtures_list = []
        for i, proj in enumerate(self.projectors):
            proj_key = f"{proj.group}_{i}"
            fixtures_list.append({
                'name': proj.name,
                'fixture_type': proj.fixture_type,
                'group': proj.group,
                'start_address': proj.start_address,
                'profile': self.dmx._get_profile(proj_key),
                'pos_x': getattr(proj, 'canvas_x', None),
                'pos_y': getattr(proj, 'canvas_y', None),
            })
        config = {
            'fixtures': fixtures_list,
            'custom_profiles': getattr(self, '_saved_custom_profiles', {}),
        }
        try:
            config_path = Path.home() / '.maestro_dmx_patch.json'
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Erreur sauvegarde patch: {e}")

    def load_dmx_patch_config(self):
        """Charge la configuration du patch DMX"""
        try:
            config_path = Path.home() / '.maestro_dmx_patch.json'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)

                # Nouveau format avec liste de fixtures
                if 'fixtures' in config:
                    self.projectors = []
                    for i, fd in enumerate(config['fixtures']):
                        p = Projector(
                            fd['group'],
                            name=fd.get('name', ''),
                            fixture_type=fd.get('fixture_type', 'PAR LED')
                        )
                        p.start_address = fd.get('start_address', (i * 10) + 1)
                        p.canvas_x = fd.get('pos_x', None)
                        p.canvas_y = fd.get('pos_y', None)
                        if fd.get('fixture_type') == "Machine a fumee":
                            p.fan_speed = 0
                        self.projectors.append(p)
                        proj_key = f"{p.group}_{i}"
                        profile = fd.get('profile', list(DMX_PROFILES['RGBDS']))
                        nb_ch = len(profile)
                        channels = [p.start_address + c for c in range(nb_ch)]
                        self.dmx.set_projector_patch(proj_key, channels, profile=profile)
                    self._saved_custom_profiles = config.get('custom_profiles', {})
                    return True

                # Retro-compat : ancien format (channels/modes/profiles)
                self.dmx.projector_channels = config.get('channels', {})
                self.dmx.projector_modes = config.get('modes', {})
                self._saved_custom_profiles = config.get('custom_profiles', {})
                if 'profiles' in config:
                    self.dmx.projector_profiles = config['profiles']
                else:
                    for key, mode in self.dmx.projector_modes.items():
                        self.dmx.projector_profiles[key] = profile_for_mode(mode)
                return True
        except Exception as e:
            print(f"Erreur chargement patch: {e}")
        return False

    def show_ia_lumiere_config(self):
        """Configuration des niveaux max IA Lumiere par groupe"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Parametres IA Lumiere")
        dialog.setFixedSize(520, 420)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: white; border: none; }
            QSlider::groove:horizontal {
                background: #2a2a2a; height: 8px; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff; width: 18px; height: 18px;
                margin: -5px 0; border-radius: 9px;
            }
            QSlider::sub-page:horizontal { background: #00d4ff; border-radius: 4px; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        title = QLabel("Niveaux maximum par groupe (IA Lumiere)")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        info = QLabel("Ces limites plafonnent le dimmer de chaque groupe\nlorsque le mode IA Lumiere est actif.")
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #888; font-size: 12px; padding: 5px;")
        layout.addWidget(info)

        sliders = {}
        groups = [
            ("Face", "face"),
            ("Lateraux & Contres", "lat"),
            ("Douche 1", "douche1"),
            ("Douche 2", "douche2"),
            ("Douche 3", "douche3"),
        ]

        for label_text, key in groups:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(12)

            label = QLabel(label_text)
            label.setMinimumWidth(150)
            label.setStyleSheet("font-size: 13px;")
            row_layout.addWidget(label)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            current_val = self.ia_max_dimmers.get(key, 100)
            slider.setValue(current_val)
            row_layout.addWidget(slider)

            value_label = QLabel(f"{current_val}%")
            value_label.setMinimumWidth(45)
            value_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #00d4ff;")
            slider.valueChanged.connect(lambda v, lbl=value_label: lbl.setText(f"{v}%"))
            row_layout.addWidget(value_label)

            sliders[key] = slider
            layout.addLayout(row_layout)

        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        apply_btn = QPushButton("✅ Appliquer")
        apply_btn.setStyleSheet("""
            QPushButton { background: #2a5a2a; color: white; border: none;
                border-radius: 6px; padding: 10px 25px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background: #3a7a3a; }
        """)
        apply_btn.clicked.connect(lambda: self._apply_ia_config(dialog, sliders))
        btn_layout.addWidget(apply_btn)

        cancel_btn = QPushButton("❌ Annuler")
        cancel_btn.setStyleSheet("""
            QPushButton { background: #3a3a3a; color: white; border: none;
                border-radius: 6px; padding: 10px 25px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background: #4a4a4a; }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        dialog.exec()

    def _apply_ia_config(self, dialog, sliders):
        """Applique la config IA Lumiere"""
        for key, slider in sliders.items():
            self.ia_max_dimmers[key] = slider.value()
        # Lat et Contre partagent le meme slider
        self.ia_max_dimmers['contre'] = self.ia_max_dimmers['lat']
        self.save_ia_lumiere_config()
        dialog.accept()

    def save_ia_lumiere_config(self):
        """Sauvegarde la configuration IA Lumiere"""
        try:
            config_path = Path.home() / '.maestro_ia_lumiere.json'
            with open(config_path, 'w') as f:
                json.dump(self.ia_max_dimmers, f, indent=2)
        except Exception as e:
            print(f"Erreur sauvegarde IA config: {e}")

    def load_ia_lumiere_config(self):
        """Charge la configuration IA Lumiere"""
        try:
            config_path = Path.home() / '.maestro_ia_lumiere.json'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    saved = json.load(f)
                self.ia_max_dimmers.update(saved)
        except Exception as e:
            print(f"Erreur chargement IA config: {e}")

    def test_dmx_on_startup(self):
        """Test automatique de la connexion DMX au demarrage"""
        # Bloquer DMX si licence non autorisee
        if not self._license.dmx_allowed:
            self.dmx.connected = False
            print("DMX bloque par la licence")
            return

        # Creer le socket UDP inconditionnellement (Art-Net = UDP sans confirmation,
        # pas besoin de ping pour ouvrir le socket)
        if self.dmx.connect():
            self.update_connection_indicators()

    def update_connection_indicators(self):
        """Met a jour les indicateurs de connexion"""
        akai_connected = False
        if MIDI_AVAILABLE and self.midi_handler.midi_in and self.midi_handler.midi_out:
            try:
                akai_connected = self.midi_handler.midi_in.is_port_open() and self.midi_handler.midi_out.is_port_open()
            except:
                pass

        if akai_connected:
            print("AKAI: Connecte")
        else:
            print("AKAI: Deconnecte")

        if self.dmx.connected:
            print(f"Boitier DMX: Connecte ({self.dmx.target_ip})")
        else:
            print("Boitier DMX: Deconnecte")

    # ==================== MENU CONNEXION ====================

    def test_akai_connection(self):
        """Teste la connexion AKAI APC mini, tente la reconnexion si deconnecte"""
        if not MIDI_AVAILABLE:
            QMessageBox.warning(self, "AKAI",
                "Module MIDI non installe.\n\nInstallez avec: py -m pip install rtmidi2")
            return

        connected = False
        if self.midi_handler.midi_in and self.midi_handler.midi_out:
            try:
                connected = self.midi_handler.midi_in.is_port_open() and self.midi_handler.midi_out.is_port_open()
            except:
                pass

        if connected:
            QMessageBox.information(self, "AKAI", "AKAI APC mini connecte et operationnel !")
        else:
            # Tenter la reconnexion automatique
            self.midi_handler.connect_akai()
            reconnected = False
            if self.midi_handler.midi_in and self.midi_handler.midi_out:
                try:
                    reconnected = self.midi_handler.midi_in.is_port_open() and self.midi_handler.midi_out.is_port_open()
                except:
                    pass

            if reconnected:
                QTimer.singleShot(200, self.activate_default_white_pads)
                QTimer.singleShot(300, self.turn_off_all_effects)
                QTimer.singleShot(400, self._sync_faders_to_projectors)
                QMessageBox.information(self, "AKAI",
                    "AKAI APC mini detecte et reconnecte avec succes !")
            else:
                QMessageBox.warning(self, "AKAI",
                    "AKAI APC mini non detecte.\n\n"
                    "Verifiez que le controleur est branche en USB.")

    def reset_akai(self):
        """Reinitialise la connexion, les LEDs et les faders de l'AKAI"""
        if not MIDI_AVAILABLE:
            QMessageBox.warning(self, "AKAI", "Module MIDI non installe.")
            return

        try:
            self.midi_handler.connect_akai()
            if self.midi_handler.midi_in and self.midi_handler.midi_out:
                QTimer.singleShot(200, self.activate_default_white_pads)
                QTimer.singleShot(300, self.turn_off_all_effects)
                # Synchroniser les faders UI avec les niveaux actuels des projecteurs
                QTimer.singleShot(400, self._sync_faders_to_projectors)
                QMessageBox.information(self, "AKAI", "AKAI reinitialise avec succes !")
            else:
                QMessageBox.warning(self, "AKAI",
                    "AKAI APC mini non detecte.\n\n"
                    "Verifiez que le controleur est branche en USB.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur reinitialisation AKAI: {e}")

    def _sync_faders_to_projectors(self):
        """Synchronise les faders UI avec les niveaux actuels des projecteurs"""
        for col_idx, groups in self.FADER_GROUPS.items():
            if groups is None or col_idx > 3:
                continue
            for p in self.projectors:
                if p.group in groups:
                    if col_idx in self.faders:
                        self.faders[col_idx].set_value(p.level)
                    break

    def open_node_connection(self):
        """Ouvre l'assistant de connexion et configuration du Node DMX."""
        from node_connection import NodeConnectionDialog
        dlg = NodeConnectionDialog(self)
        dlg.exec()

    def test_node_connection(self):
        """Diagnostic Node DMX : carte reseau + node"""
        if not self._license.dmx_allowed:
            QMessageBox.warning(self, "Sortie DMX",
                "Votre periode d'essai est terminee ou le logiciel n'est pas active.\nActivez une licence pour utiliser la sortie Art-Net.")
            return

        import socket as _socket
        from node_connection import _get_ethernet_adapters, _artpoll_packet, TARGET_IP, TARGET_PORT

        dlg = QDialog(self)
        dlg.setWindowTitle("Diagnostic Node DMX")
        dlg.setFixedSize(430, 250)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setStyleSheet(
            "QDialog { background: #1a1a1a; }"
            "QLabel { color: #cccccc; border: none; background: transparent; }"
        )

        root = QVBoxLayout(dlg)
        root.setContentsMargins(28, 22, 28, 18)
        root.setSpacing(16)

        title = QLabel("Diagnostic de la sortie Node DMX")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet("color: #00d4ff;")
        root.addWidget(title)

        def _make_check_row(label_text):
            row = QHBoxLayout()
            row.setSpacing(14)
            icon = QLabel("…")
            icon.setFont(QFont("Segoe UI", 16))
            icon.setFixedWidth(26)
            icon.setAlignment(Qt.AlignCenter)
            icon.setStyleSheet("color: #555555;")
            row.addWidget(icon)
            col = QVBoxLayout()
            col.setSpacing(1)
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
            col.addWidget(lbl)
            detail = QLabel("Vérification en cours...")
            detail.setFont(QFont("Segoe UI", 9))
            detail.setStyleSheet("color: #555555;")
            col.addWidget(detail)
            row.addLayout(col, 1)
            root.addLayout(row)
            return icon, detail

        icon_net, detail_net = _make_check_row("Carte réseau")
        icon_node, detail_node = _make_check_row("Node DMX")

        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_config = QPushButton("Ouvrir l'assistant de connexion")
        btn_config.setFixedHeight(30)
        btn_config.setStyleSheet(
            "QPushButton { background: #1e3a4a; color: #00d4ff; border: 1px solid #00d4ff;"
            " border-radius: 4px; padding: 0 14px; font-size: 10px; }"
            "QPushButton:hover { background: #254a5a; }"
        )
        btn_config.hide()
        btn_config.clicked.connect(lambda: (dlg.accept(), self.open_node_connection()))
        btn_row.addWidget(btn_config)
        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(30)
        btn_close.setStyleSheet(
            "QPushButton { background: #2a2a2a; color: #aaaaaa; border: 1px solid #3a3a3a;"
            " border-radius: 4px; padding: 0 14px; font-size: 10px; }"
            "QPushButton:hover { background: #333333; color: white; }"
        )
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        dlg.show()
        QApplication.processEvents()

        # --- Vérification 1 : carte réseau ---
        adapters = _get_ethernet_adapters()
        ok_adapters = [(n, ip) for n, ip in adapters if ip.startswith("2.")]

        if ok_adapters:
            name, ip = ok_adapters[0]
            icon_net.setText("✓")
            icon_net.setStyleSheet("color: #4CAF50;")
            detail_net.setText(f"{name}  —  IP : {ip}")
            detail_net.setStyleSheet("color: #4CAF50;")
            net_ok = True
        elif adapters:
            names = "  /  ".join(n for n, _ in adapters[:2])
            icon_net.setText("⚠")
            icon_net.setStyleSheet("color: #ff9800;")
            detail_net.setText(f"{names}  —  IP non configurée en 2.x.x.x")
            detail_net.setStyleSheet("color: #ff9800;")
            net_ok = False
        else:
            icon_net.setText("✗")
            icon_net.setStyleSheet("color: #f44336;")
            detail_net.setText("Aucune carte Ethernet détectée — vérifiez le câble RJ45")
            detail_net.setStyleSheet("color: #f44336;")
            net_ok = False

        QApplication.processEvents()

        # --- Vérification 2 : node ArtPoll ---
        node_ok = False
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            s.settimeout(1.5)
            s.sendto(_artpoll_packet(), (TARGET_IP, TARGET_PORT))
            data, _ = s.recvfrom(256)
            s.close()
            node_ok = data[:8] == b'Art-Net\x00'
        except Exception:
            node_ok = False

        if node_ok:
            icon_node.setText("✓")
            icon_node.setStyleSheet("color: #4CAF50;")
            detail_node.setText(f"Répond sur {TARGET_IP}  —  Art-Net opérationnel")
            detail_node.setStyleSheet("color: #4CAF50;")
            if not self.dmx.connected:
                self.dmx.connect()
        else:
            icon_node.setText("✗")
            icon_node.setStyleSheet("color: #f44336;")
            if net_ok:
                detail_node.setText(f"Pas de réponse sur {TARGET_IP}  —  vérifiez que le boîtier est allumé")
            else:
                detail_node.setText(f"Impossible de contacter {TARGET_IP}  —  configurez d'abord la carte réseau")
            detail_node.setStyleSheet("color: #f44336;")

        if not net_ok or not node_ok:
            btn_config.show()

        QApplication.processEvents()
        dlg.exec()

    def configure_node(self):
        """Configure les parametres du Node DMX"""
        if not self._license.dmx_allowed:
            QMessageBox.warning(self, "Sortie DMX",
                "Votre periode d'essai est terminee ou le logiciel n'est pas active.\nActivez une licence pour utiliser la sortie Art-Net.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Parametres NODE DMX")
        dialog.setFixedSize(350, 220)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: white; border: none; }
            QLineEdit {
                background: #2a2a2a; color: white; border: 1px solid #3a3a3a;
                border-radius: 4px; padding: 6px; font-size: 12px;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        title = QLabel("Configuration du Node DMX")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # IP
        ip_layout = QHBoxLayout()
        ip_layout.addWidget(QLabel("Adresse IP:"))
        ip_edit = QLineEdit(self.dmx.target_ip)
        ip_layout.addWidget(ip_edit)
        layout.addLayout(ip_layout)

        # Port
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        port_edit = QLineEdit(str(self.dmx.target_port))
        port_layout.addWidget(port_edit)
        layout.addLayout(port_layout)

        # Univers
        univers_layout = QHBoxLayout()
        univers_layout.addWidget(QLabel("Univers:"))
        univers_edit = QLineEdit(str(self.dmx.universe))
        univers_layout.addWidget(univers_edit)
        layout.addLayout(univers_layout)

        # Boutons
        btn_layout = QHBoxLayout()
        apply_btn = QPushButton("Appliquer")
        apply_btn.setStyleSheet("""
            QPushButton { background: #2a5a2a; color: white; border: none;
                border-radius: 6px; padding: 8px 20px; font-weight: bold; }
            QPushButton:hover { background: #3a7a3a; }
        """)

        def apply_config():
            self.dmx.target_ip = ip_edit.text().strip()
            try:
                self.dmx.target_port = int(port_edit.text().strip())
            except ValueError:
                pass
            try:
                self.dmx.universe = int(univers_edit.text().strip())
            except ValueError:
                pass
            # Reconnecter avec les nouveaux parametres
            self.dmx.connected = False
            self.dmx.connect()
            dialog.accept()
            QMessageBox.information(self, "NODE",
                f"Configuration appliquee:\n"
                f"IP: {self.dmx.target_ip}\n"
                f"Port: {self.dmx.target_port}\n"
                f"Univers: {self.dmx.universe}")

        apply_btn.clicked.connect(apply_config)
        btn_layout.addWidget(apply_btn)

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet("""
            QPushButton { background: #3a3a3a; color: white; border: none;
                border-radius: 6px; padding: 8px 20px; font-weight: bold; }
            QPushButton:hover { background: #4a4a4a; }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        dialog.exec()

    def play_test_sound(self):
        """Genere et joue un son de test 440Hz"""
        import wave
        import struct
        import tempfile

        # Generer un WAV 440Hz d'une seconde
        sample_rate = 44100
        duration = 1.0
        frequency = 440.0
        amplitude = 0.5

        filepath = os.path.join(tempfile.gettempdir(), "maestro_test_440hz.wav")
        try:
            with wave.open(filepath, 'w') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                num_samples = int(sample_rate * duration)
                import math
                for i in range(num_samples):
                    sample = amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate)
                    wf.writeframes(struct.pack('<h', int(sample * 32767)))

            self.cart_player.setSource(QUrl.fromLocalFile(filepath))
            self.cart_player.play()
            QMessageBox.information(self, "AUDIO", "Son de test 440Hz envoye !")
        except Exception as e:
            QMessageBox.warning(self, "AUDIO", f"Erreur generation son: {e}")

    def _populate_audio_output_menu(self):
        """Remplit dynamiquement le sous-menu Sortie Audio avec les peripheriques"""
        self.audio_output_menu.clear()
        devices = QMediaDevices.audioOutputs()
        current_device = self.audio.device()

        for dev in devices:
            action = self.audio_output_menu.addAction(dev.description())
            action.setCheckable(True)
            action.setChecked(dev.id() == current_device.id())
            action.triggered.connect(lambda checked, d=dev: self._set_audio_output(d))

    def _set_audio_output(self, device):
        """Change le peripherique de sortie audio"""
        self.audio.setDevice(device)
        self.cart_audio.setDevice(device)

    def _populate_screen_menu(self):
        """Remplit dynamiquement le sous-menu de choix d'ecran"""
        self.video_screen_menu.clear()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            label = f"Ecran {i + 1} ({screen.name()} - {geo.width()}x{geo.height()})"
            action = self.video_screen_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(i == self.video_target_screen)
            action.triggered.connect(lambda checked, idx=i: self._set_video_screen(idx))

    def _set_video_screen(self, screen_index):
        """Change l'ecran cible pour la sortie video"""
        self.video_target_screen = screen_index
        # Si la fenetre est deja ouverte, la deplacer
        if self.video_output_window and self.video_output_window.isVisible():
            screens = QApplication.screens()
            if screen_index < len(screens):
                screen = screens[screen_index]
                self.video_output_window.setGeometry(screen.geometry())
                self.video_output_window.showFullScreen()

    def show_test_logo(self):
        """Affiche le logo de test pendant 3 secondes (preview + externe si active)"""
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Mystrow_blanc.png")
        if not os.path.exists(logo_path):
            QMessageBox.warning(self, "VIDEO", "Fichier Mystrow_blanc.png introuvable.")
            return

        # Afficher dans le preview local (toujours)
        self.show_image(logo_path)

        # Afficher aussi dans la fenetre externe si elle est active
        if self.video_output_window and self.video_output_window.isVisible():
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                self.video_output_window.show_image(pixmap)

        # Masquer apres 3 secondes
        QTimer.singleShot(3000, self._hide_test_logo)

    def _hide_test_logo(self):
        """Cache le logo de test"""
        self.hide_image()
        if self.video_output_window and self.video_output_window.isVisible():
            self._update_video_output_state()

    def toggle_video_output_from_menu(self):
        """Active/desactive la sortie video depuis le menu"""
        self.video_output_btn.setChecked(not self.video_output_btn.isChecked())
        self.toggle_video_output()
        # Mettre a jour le texte du menu
        if self.video_output_btn.isChecked():
            self.video_menu_toggle.setText("🟢 Desactiver sortie video")
        else:
            self.video_menu_toggle.setText("🔴 Activer sortie video")

    def _compute_htp_overrides(self):
        """Calcule les valeurs HTP des memoires SANS modifier les projecteurs.
        Retourne un dict {id(proj): (level, QColor_display, QColor_base)} pour l'affichage."""
        overrides = {}

        for mem_col in range(4):
            col_akai = 4 + mem_col
            fv = self.faders[col_akai].value if col_akai in self.faders else 0
            active_row = self.active_memory_pads.get(col_akai)
            if fv > 0 and active_row is not None and self.memories[mem_col][active_row]:
                mem_projs = self.memories[mem_col][active_row]["projectors"]
                for i, proj in enumerate(self.projectors):
                    if i < len(mem_projs):
                        ms = mem_projs[i]
                        mem_level = int(ms["level"] * fv / 100.0)
                        # HTP: comparer avec le niveau actuel du projecteur ou override precedent
                        current_level = overrides[id(proj)][0] if id(proj) in overrides else proj.level
                        if mem_level > current_level:
                            base = QColor(ms["base_color"])
                            brt = mem_level / 100.0
                            color = QColor(
                                int(base.red() * brt),
                                int(base.green() * brt),
                                int(base.blue() * brt))
                            overrides[id(proj)] = (mem_level, color, base)

        return overrides

    def _apply_htp_to_projectors(self, overrides):
        """Applique temporairement les overrides HTP sur les projecteurs pour envoi DMX.
        Retourne la liste des etats sauvegardes pour restauration."""
        saved = []
        for proj in self.projectors:
            saved.append((proj.level, QColor(proj.color), QColor(proj.base_color)))
            if id(proj) in overrides:
                level, color, base = overrides[id(proj)]
                proj.level = level
                proj.color = color
                proj.base_color = base
        return saved

    def _apply_pad_overrides_htp(self):
        """Applique les pads AKAI actifs en HTP par-dessus l'etat courant des projecteurs.
        Retourne la liste des etats sauvegardes pour restauration apres envoi DMX."""
        _PAD_GROUPS = {
            0: ["face"],
            1: ["contre", "lat"],
            2: ["douche1", "douche2", "douche3"],
            3: ["public"],
        }
        saved = []
        for col_idx, btn in self.active_pads.items():
            if btn is None:
                continue
            color = btn.property("base_color")
            if color is None:
                continue
            fader_value = self.faders[col_idx].value if col_idx in self.faders else 0
            if fader_value <= 0:
                continue
            brightness = fader_value / 100.0
            pad_color = QColor(
                int(color.red() * brightness),
                int(color.green() * brightness),
                int(color.blue() * brightness),
            )
            for i, proj in enumerate(self.projectors):
                if proj.group in _PAD_GROUPS.get(col_idx, []) and fader_value > proj.level:
                    saved.append((i, proj.level, proj.color, proj.base_color))
                    proj.level = fader_value
                    proj.color = pad_color
                    proj.base_color = color
        return saved

    def send_dmx_update(self):
        """Envoie les donnees DMX avec HTP memoires + pads AKAI + refresh plan de feu"""
        # Calculer les overrides HTP sans modifier les projecteurs
        overrides = self._compute_htp_overrides()

        # Stocker les overrides sur le plan de feu (utilise par TOUS les appels a refresh)
        self.plan_de_feu.set_htp_overrides(overrides if overrides else None)

        if self.plan_de_feu.is_dmx_enabled() and self.dmx.connected:
            # Appliquer temporairement HTP memoires
            if overrides:
                saved_htp = self._apply_htp_to_projectors(overrides)

            # Appliquer temporairement les pads AKAI en HTP (fonctionne dans TOUS les modes)
            saved_pads = self._apply_pad_overrides_htp()

            # Envoyer DMX
            self.dmx.update_from_projectors(self.projectors, self.effect_speed)
            self.dmx.send_dmx()

            # Restaurer etat pads
            for i, level, color, base_color in saved_pads:
                self.projectors[i].level = level
                self.projectors[i].color = color
                self.projectors[i].base_color = base_color

            # Restaurer etat HTP memoires
            if overrides:
                for i, proj in enumerate(self.projectors):
                    proj.level, proj.color, proj.base_color = saved_htp[i]

    def stop_recording(self):
        """Arrete l'enregistrement"""
        if not self.seq.recording:
            return
        self.seq.recording = False
        if self.seq.recording_timer:
            self.seq.recording_timer.stop()
