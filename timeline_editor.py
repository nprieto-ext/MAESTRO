"""
Editeur de timeline lumiere - LightTimelineEditor
"""
import os
import json
import hashlib
import random
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QComboBox, QProgressBar, QCheckBox,
    QMessageBox, QApplication, QMenuBar, QMenu
)
from PySide6.QtCore import Qt, QTimer, QUrl, QPoint, QRect
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon, QPalette, QBrush, QCursor, QKeySequence
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from light_timeline import LightTrack, LightClip, ColorPalette
from core import media_icon


class _AnalysisCancelled(Exception):
    """Exception interne pour interrompre l'analyse audio"""
    pass


class RubberBandOverlay(QWidget):
    """Overlay transparent pour dessiner le rectangle de selection"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.rect = None

    def set_rect(self, rect):
        self.rect = rect
        self.update()

    def clear(self):
        self.rect = None
        self.update()

    def paintEvent(self, event):
        if self.rect:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Fond semi-transparent cyan
            painter.setBrush(QBrush(QColor(0, 212, 255, 50)))
            painter.setPen(QPen(QColor("#00d4ff"), 2, Qt.DashLine))
            painter.drawRect(self.rect)

            painter.end()


class LightTimelineEditor(QDialog):
    """Editeur de sequence lumiere - Theme coherent"""

    def __init__(self, main_window, media_row):
        super().__init__(main_window)
        self.main_window = main_window
        self.media_row = media_row

        # Recuperer infos du media
        item = main_window.seq.table.item(media_row, 1)
        self.media_path = item.data(Qt.UserRole) if item else ""
        self.media_name = item.text() if item else f"Media {media_row + 1}"

        # Detecter les PAUSE (indefinies et temporisees) et ancien format TEMPO
        self.is_tempo = False
        self.media_duration_override = 0
        if self.media_path == "PAUSE":
            self.is_tempo = True
            self.media_duration_override = 60000  # 60s par defaut pour editeur
            self.media_path = ""
            self.media_name = "Pause"
        elif self.media_path and (str(self.media_path).startswith("PAUSE:") or str(self.media_path).startswith("TEMPO:")):
            self.is_tempo = True
            pause_seconds = int(str(self.media_path).split(":")[1])
            self.media_duration_override = pause_seconds * 1000
            self.media_path = ""
            self.media_name = f"Pause ({pause_seconds}s)"

        self.setWindowTitle(f"🎬 Editeur - {self.media_name}")

        # Configuration palette tooltips
        palette = self.palette()
        palette.setColor(QPalette.ToolTipBase, QColor("white"))
        palette.setColor(QPalette.ToolTipText, QColor("black"))
        self.setPalette(palette)

        app_palette = QApplication.instance().palette()
        app_palette.setColor(QPalette.ToolTipBase, QColor("white"))
        app_palette.setColor(QPalette.ToolTipText, QColor("black"))
        QApplication.instance().setPalette(app_palette)

        # Theme global avec TOOLTIPS CORRIGES
        self.setStyleSheet("""
            QDialog {
                background: #0a0a0a;
            }
            * {
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QToolTip {
                background-color: #2a2a2a;
                color: #00d4ff;
                border: 2px solid #00d4ff;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            QMessageBox {
                background: #1a1a1a;
            }
            QMessageBox QLabel {
                color: white;
            }
            QMessageBox QPushButton {
                color: black;
                background: #cccccc;
                border: 1px solid #999999;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
            }
            QMessageBox QPushButton:hover {
                background: #00d4ff;
            }
        """)

        # Plein ecran avec boutons maximiser/minimiser
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)

        # Curseur de lecture
        if main_window.player.playbackState() == QMediaPlayer.PlayingState:
            self.playback_position = main_window.player.position()
        else:
            self.playback_position = 0

        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.update_playhead)

        # Demarrer le timer si le player principal joue deja
        if main_window.player.playbackState() == QMediaPlayer.PlayingState:
            self.playback_timer.start(40)

        # Recuperer duree du media
        self.media_duration = self.get_media_duration()

        # Historique undo
        self.history = []
        self.history_index = -1

        # Mode cut
        self.cut_mode = False

        # Selection multi-pistes (rubber band)
        self.rubber_band_active = False
        self.rubber_band_start = None
        self.rubber_band_rect = None
        self.rubber_band_origin_track = None

        # Clipboard pour copier/coller
        self.clipboard = []

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Menu bar
        menubar = self._create_menu_bar()
        layout.addWidget(menubar)

        # Header
        header = self._create_header()
        layout.addWidget(header)

        # Ruler
        self.ruler = QWidget()
        self.ruler.setFixedHeight(35)
        self.ruler.setStyleSheet("background: #1a1a1a; border-bottom: 1px solid #2a2a2a;")
        self.ruler.paintEvent = self.paint_ruler
        self.ruler.mousePressEvent = self.ruler_mouse_press
        self.ruler.mouseMoveEvent = self.ruler_mouse_move
        self.ruler.mouseReleaseEvent = self.ruler_mouse_release
        layout.addWidget(self.ruler)

        # Scroll area pour les pistes
        self.tracks_scroll = QScrollArea()
        self.tracks_scroll.setWidgetResizable(True)
        self.tracks_scroll.setStyleSheet("""
            QScrollArea { background: #0a0a0a; border: none; }
            QScrollBar:vertical { background: #1a1a1a; width: 12px; }
            QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 6px; }
            QScrollBar:horizontal { background: #1a1a1a; height: 12px; }
            QScrollBar::handle:horizontal { background: #3a3a3a; border-radius: 6px; }
        """)

        tracks_container = QWidget()
        tracks_container.setStyleSheet("background: #0a0a0a;")
        tracks_layout = QVBoxLayout(tracks_container)
        tracks_layout.setSpacing(0)
        tracks_layout.setContentsMargins(0, 0, 0, 0)

        # Creer les pistes
        self.track_face = LightTrack("Face", self.media_duration, self)
        self.track_douche1 = LightTrack("Douche 1", self.media_duration, self)
        self.track_douche2 = LightTrack("Douche 2", self.media_duration, self)
        self.track_douche3 = LightTrack("Douche 3", self.media_duration, self)
        self.track_contre = LightTrack("Contres", self.media_duration, self)

        # Piste waveform (masquee pour images et pauses)
        self.track_waveform = LightTrack("Audio", self.media_duration, self)
        self.track_waveform.setAcceptDrops(False)
        self.track_waveform.setMinimumHeight(80)

        is_image = self.media_path and media_icon(self.media_path) == "image"
        show_audio = not is_image and not self.is_tempo

        self.tracks = [
            self.track_face, self.track_douche1, self.track_douche2,
            self.track_douche3, self.track_contre
        ]

        for track in self.tracks:
            tracks_layout.addWidget(track)

        if show_audio:
            tracks_layout.addWidget(self.track_waveform)
        else:
            self.track_waveform.hide()
        tracks_layout.addStretch()

        # Stocker le container pour l'overlay
        self.tracks_container = tracks_container
        self.tracks_scroll.setWidget(tracks_container)
        layout.addWidget(self.tracks_scroll)

        # Creer l'overlay pour le rubber band (rectangle de selection visible)
        self.rubber_band_overlay = RubberBandOverlay(self.tracks_scroll.viewport())
        self.rubber_band_overlay.setGeometry(self.tracks_scroll.viewport().rect())
        self.rubber_band_overlay.hide()

        # Synchroniser ruler avec scroll horizontal
        self.tracks_scroll.horizontalScrollBar().valueChanged.connect(self.on_scroll_changed)

        # Palette de couleurs
        self.palette = ColorPalette(self)
        layout.addWidget(self.palette)

        # Footer
        footer = self._create_footer()
        layout.addWidget(footer)

        # Zoom par defaut
        self.current_zoom = 1.0

        # Player audio pour preview
        self.setup_audio_player()

        # Charger sequence existante
        self.load_existing_sequence()

        # Forcer affichage du curseur
        QTimer.singleShot(100, lambda: self.ruler.update())

        # Generer la forme d'onde (sauf pour les images et les pauses)
        is_image = self.media_path and media_icon(self.media_path) == "image"
        if self.media_path and os.path.exists(self.media_path) and not is_image and not self.is_tempo:
            QTimer.singleShot(50, self._load_waveform_async)

        # Maximiser la fenetre apres construction complete
        self.showMaximized()

    def _get_waveform_cache_path(self):
        """Retourne le chemin du fichier cache pour la forme d'onde"""
        if not self.media_path:
            return None
        abs_path = os.path.abspath(self.media_path)
        try:
            stat = os.stat(abs_path)
            key = f"{abs_path}:{stat.st_size}:{int(stat.st_mtime)}"
        except OSError:
            key = abs_path
        hash_key = hashlib.md5(key.encode()).hexdigest()
        cache_dir = os.path.join(os.path.expanduser("~"), '.maestro_cache')
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, f"{hash_key}.json")

    def _save_waveform_cache(self, waveform):
        """Sauvegarde la forme d'onde dans le cache fichier"""
        cache_path = self._get_waveform_cache_path()
        if cache_path and waveform:
            try:
                compact = [round(x, 3) for x in waveform]
                with open(cache_path, 'w') as f:
                    json.dump(compact, f)
                print(f"   Cache waveform sauvegarde: {cache_path}")
            except Exception as e:
                print(f"   Warning: impossible de sauvegarder le cache: {e}")

    def _load_waveform_from_cache(self):
        """Charge la forme d'onde depuis le cache fichier"""
        cache_path = self._get_waveform_cache_path()
        if cache_path and os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
            except Exception:
                pass
        return None

    def _apply_waveform(self, waveform):
        """Applique les donnees de forme d'onde a toutes les pistes et force le rafraichissement"""
        self.track_waveform.waveform_data = waveform
        for track in self.tracks:
            track.waveform_data = waveform
        self.track_waveform.update()
        for track in self.tracks:
            track.update()

    def _load_waveform_async(self):
        """Charge la waveform avec cache et dialog de progression"""
        # 1. Deja chargee depuis les donnees de sequence ?
        if self.track_waveform.waveform_data:
            print(f"   Waveform deja chargee depuis sequence ({len(self.track_waveform.waveform_data)} points)")
            self._apply_waveform(self.track_waveform.waveform_data)
            return

        # 2. Cache fichier ?
        cached = self._load_waveform_from_cache()
        if cached:
            self._apply_waveform(cached)
            print(f"   Waveform chargee depuis cache ({len(cached)} points)")
            return

        # 3. Generation avec barre de progression
        self._analysis_cancelled = False

        loading = QDialog(self)
        loading.setWindowTitle("Chargement")
        loading.setFixedSize(380, 170)
        loading.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        loading.setStyleSheet("""
            QDialog { background: #1a1a1a; border: 2px solid #00d4ff; border-radius: 10px; }
            QLabel { color: white; border: none; }
            QProgressBar { background: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 5px; text-align: center; color: white; }
            QProgressBar::chunk { background: #00d4ff; border-radius: 4px; }
        """)
        lay = QVBoxLayout(loading)
        lay.setContentsMargins(20, 15, 20, 15)
        is_vid = hasattr(self, 'is_video_file') and self.is_video_file
        status = QLabel("Extraction audio de la video... 0%" if is_vid else "Analyse audio en cours... 0%")
        status.setAlignment(Qt.AlignCenter)
        status.setStyleSheet("font-size: 14px; font-weight: bold;")
        lay.addWidget(status)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        lay.addWidget(bar)

        cancel_btn = QPushButton("Annuler l'analyse")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #5a2a2a; color: white; border: none;
                border-radius: 6px; padding: 8px 20px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #8b3a3a; }
        """)
        cancel_btn.clicked.connect(lambda: setattr(self, '_analysis_cancelled', True))
        lay.addWidget(cancel_btn, alignment=Qt.AlignCenter)

        loading.show()
        QApplication.processEvents()

        def on_progress(pct):
            if self._analysis_cancelled:
                raise _AnalysisCancelled()
            bar.setValue(pct)
            prefix = "Extraction audio" if is_vid else "Analyse audio"
            status.setText(f"{prefix}... {pct}%")
            QApplication.processEvents()
            if self._analysis_cancelled:
                raise _AnalysisCancelled()

        try:
            waveform = self.track_waveform.generate_waveform(
                self.media_path, max_samples=5000, progress_callback=on_progress
            )
            if self._analysis_cancelled:
                raise _AnalysisCancelled()
            if waveform:
                self._apply_waveform(waveform)
                # Sauvegarder dans le cache fichier
                self._save_waveform_cache(waveform)
                # Stocker dans les donnees de sequence (en memoire)
                if self.media_row in self.main_window.seq.sequences:
                    self.main_window.seq.sequences[self.media_row]['waveform'] = [round(x, 3) for x in waveform]
                bar.setValue(100)
                status.setText(f"{len(waveform)} points analyses")
            else:
                status.setText("Forme d'onde indisponible")
        except _AnalysisCancelled:
            print("Analyse annulee par l'utilisateur")
            loading.close()
            self.reject()
            return
        except Exception as e:
            status.setText(f"Erreur: {e}")
            print(f"Erreur forme d'onde: {e}")

        QApplication.processEvents()
        loading.close()

        # Forcer le rafraichissement apres fermeture du dialog
        self.track_waveform.update()
        for track in self.tracks:
            track.update()

    def _create_menu_bar(self):
        """Cree la barre de menus Edition / Outils / Effet"""
        menubar = QMenuBar()
        menu_style = """
            QMenuBar {
                background: #1a1a1a;
                color: white;
                border-bottom: 1px solid #3a3a3a;
                padding: 2px;
                font-size: 13px;
            }
            QMenuBar::item {
                padding: 6px 14px;
                background: transparent;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background: #3a3a3a;
            }
            QMenu {
                background: #2a2a2a;
                color: white;
                border: 2px solid #00d4ff;
                padding: 5px;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 30px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #00d4ff;
                color: black;
            }
            QMenu::separator {
                background: #4a4a4a;
                height: 1px;
                margin: 5px 10px;
            }
        """
        menubar.setStyleSheet(menu_style)

        # === EDITION ===
        edit_menu = menubar.addMenu("Edition")

        undo_action = edit_menu.addAction("Annuler\tCtrl+Z")
        undo_action.triggered.connect(self.undo)

        redo_action = edit_menu.addAction("Retablir\tCtrl+Y")
        redo_action.triggered.connect(self.redo)

        edit_menu.addSeparator()

        cut_action = edit_menu.addAction("Couper\tCtrl+X")
        cut_action.triggered.connect(self.cut_selected_clips)

        copy_action = edit_menu.addAction("Copier\tCtrl+C")
        copy_action.triggered.connect(self.copy_selected_clips)

        paste_action = edit_menu.addAction("Coller\tCtrl+V")
        paste_action.triggered.connect(self.paste_clips)

        edit_menu.addSeparator()

        select_all_action = edit_menu.addAction("Selectionner tout\tCtrl+A")
        select_all_action.triggered.connect(self.select_all_clips)

        delete_action = edit_menu.addAction("Supprimer\tSuppr")
        delete_action.triggered.connect(self.delete_selected_clips)

        delete_all_action = edit_menu.addAction("Supprimer tout")
        delete_all_action.triggered.connect(self.clear_all_clips)

        # === OUTILS ===
        tools_menu = menubar.addMenu("Outils")

        cut_tool_action = tools_menu.addAction("✂ Outil couper\tC")
        cut_tool_action.triggered.connect(self.toggle_cut_mode_from_menu)

        ai_action = tools_menu.addAction("✨ Generation par IA")
        ai_action.triggered.connect(self.generate_ai_sequence)

        # === EFFET ===
        effect_menu = menubar.addMenu("Effet")

        fade_in_action = effect_menu.addAction("🎬 Fade In")
        fade_in_action.triggered.connect(self.apply_fade_in_to_selection)

        fade_out_action = effect_menu.addAction("🎬 Fade Out")
        fade_out_action.triggered.connect(self.apply_fade_out_to_selection)

        remove_fades_action = effect_menu.addAction("❌ Supprimer les fades")
        remove_fades_action.triggered.connect(self.remove_fades_from_selection)

        effect_menu.addSeparator()

        no_effect_action = effect_menu.addAction("⭕ Aucun effet")
        no_effect_action.triggered.connect(lambda: self.apply_effect_to_selection(None))

        for eff in ["Strobe", "Flash", "Pulse", "Wave", "Random"]:
            action = effect_menu.addAction(f"⚡ {eff}")
            action.triggered.connect(lambda checked=False, e=eff: self.apply_effect_to_selection(e))

        return menubar

    def _create_header(self):
        """Cree le header avec titre et boutons"""
        header = QWidget()
        header.setStyleSheet("background: #1a1a1a; border-bottom: 2px solid #3a3a3a;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 10, 15, 10)

        title = QLabel(f"🎬 {self.media_name}")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; border: none; text-decoration: none;")
        header_layout.addWidget(title)

        duration_seconds = int(self.media_duration / 1000)
        dur_min = duration_seconds // 60
        dur_sec = duration_seconds % 60
        self.total_time_str = f"{dur_min}:{dur_sec:02d}"
        self.position_label = QLabel(f"⏱ 0:00 / {self.total_time_str}")
        self.position_label.setStyleSheet("color: #00d4ff; font-size: 13px; border: none; text-decoration: none;")
        header_layout.addWidget(self.position_label)

        header_layout.addStretch()

        btn_style = """
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                border-radius: 22px;
                font-size: 22px;
            }
            QPushButton:hover { background: #4a4a4a; }
        """

        # Undo
        undo_btn = QPushButton("↶")
        undo_btn.setToolTip("Annuler (Ctrl+Z)")
        undo_btn.clicked.connect(self.undo)
        undo_btn.setFixedSize(45, 45)
        undo_btn.setStyleSheet(btn_style)
        header_layout.addWidget(undo_btn)

        # Cut
        self.cut_btn = QPushButton("✂")
        self.cut_btn.setToolTip("Outil Couper (C)")
        self.cut_btn.clicked.connect(self.toggle_cut_mode)
        self.cut_btn.setFixedSize(45, 45)
        self.cut_btn.setCheckable(True)
        self.cut_btn.setStyleSheet(btn_style + """
            QPushButton:checked { background: #00d4ff; color: black; }
        """)
        header_layout.addWidget(self.cut_btn)

        header_layout.addSpacing(20)

        # Zoom
        zoom_btn_style = """
            QPushButton {
                background: #2a2a2a;
                color: white;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-size: 18px;
            }
            QPushButton:hover { background: #3a3a3a; }
        """

        zoom_out_btn = QPushButton("➖")
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_out_btn.setFixedSize(40, 40)
        zoom_out_btn.setFocusPolicy(Qt.NoFocus)
        zoom_out_btn.setStyleSheet(zoom_btn_style)
        header_layout.addWidget(zoom_out_btn)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("color: white; padding: 0 15px; font-size: 13px;")
        header_layout.addWidget(self.zoom_label)

        zoom_in_btn = QPushButton("➕")
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_in_btn.setFixedSize(40, 40)
        zoom_in_btn.setFocusPolicy(Qt.NoFocus)
        zoom_in_btn.setStyleSheet(zoom_btn_style)
        header_layout.addWidget(zoom_in_btn)

        return header

    def _create_footer(self):
        """Cree le footer avec controles audio et boutons"""
        footer = QWidget()
        footer.setStyleSheet("background: #1a1a1a; border-top: 2px solid #3a3a3a;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(15, 10, 15, 10)
        footer_layout.setSpacing(10)

        transport_btn_style = """
            QPushButton {
                background: #4a4a4a;
                border: 2px solid #6a6a6a;
                border-radius: 8px;
                padding: 14px 18px;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #5a5a5a;
                border: 2px solid #00d4ff;
            }
            QPushButton:pressed { background: #3a3a3a; }
        """

        # -10s
        back_btn = QPushButton("⏪")
        back_btn.setFixedSize(60, 60)
        back_btn.clicked.connect(lambda: self.seek_relative(-10000))
        back_btn.setStyleSheet(transport_btn_style)
        footer_layout.addWidget(back_btn)

        # Play/Pause
        self.play_pause_btn = QPushButton("▶")
        self.play_pause_btn.setFixedSize(70, 70)
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)
        self.play_pause_btn.setStyleSheet(transport_btn_style + """
            QPushButton { padding: 18px; font-size: 24px; }
        """)
        footer_layout.addWidget(self.play_pause_btn)

        # +10s
        fwd_btn = QPushButton("⏩")
        fwd_btn.setFixedSize(60, 60)
        fwd_btn.clicked.connect(lambda: self.seek_relative(10000))
        fwd_btn.setStyleSheet(transport_btn_style)
        footer_layout.addWidget(fwd_btn)

        footer_layout.addStretch()

        # Sauvegarder
        save_btn = QPushButton("💾 Sauvegarder")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #2a5a2a;
                color: white;
                padding: 10px 30px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background: #3a6a3a; }
        """)
        save_btn.clicked.connect(self.save_sequence)
        footer_layout.addWidget(save_btn)

        # Fermer
        close_btn = QPushButton("❌ Fermer")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #4a2a2a;
                color: white;
                padding: 10px 30px;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover { background: #5a3a3a; }
        """)
        close_btn.clicked.connect(self.close_editor)
        footer_layout.addWidget(close_btn)

        return footer

    def get_media_duration(self):
        """Recupere la duree reelle du media (audio et video)"""
        # TEMPO/PAUSE: utiliser la duree definie
        if hasattr(self, 'media_duration_override') and self.media_duration_override > 0:
            return self.media_duration_override

        # Image: utiliser la duree definie dans image_durations
        if self.media_path and media_icon(self.media_path) == "image":
            image_dur = self.main_window.seq.image_durations.get(self.media_row)
            if image_dur:
                return image_dur * 1000
            return 30000  # 30s par defaut

        is_video = self.media_path and media_icon(self.media_path) == "video"

        # QMediaPlayer avec outputs audio/video pour charger correctement le media
        try:
            import time

            temp_player = QMediaPlayer()
            temp_audio = QAudioOutput()
            temp_player.setAudioOutput(temp_audio)

            # Pour les fichiers video, ajouter un output video
            # Sans ca, Qt ne parse pas correctement le conteneur video
            if is_video:
                temp_video = QVideoWidget()
                temp_video.setFixedSize(1, 1)
                temp_video.hide()
                temp_player.setVideoOutput(temp_video)

            duration_ms = [0]

            def on_duration_changed(dur):
                if dur > 0:
                    duration_ms[0] = dur

            temp_player.durationChanged.connect(on_duration_changed)
            temp_player.setSource(QUrl.fromLocalFile(self.media_path))

            timeout = 10 if is_video else 5
            start = time.time()
            while duration_ms[0] == 0 and (time.time() - start) < timeout:
                QApplication.processEvents()
                time.sleep(0.05)

            if duration_ms[0] > 0:
                return duration_ms[0]
        except Exception as e:
            print(f"Erreur duree : {e}")

        return 180000  # 3 minutes par defaut

    def setup_audio_player(self):
        """Configure le player audio/video pour preview (pas pour images/pauses)"""
        self.preview_player = QMediaPlayer()
        self.preview_audio = QAudioOutput()
        self.preview_player.setAudioOutput(self.preview_audio)

        is_image = self.media_path and media_icon(self.media_path) == "image"

        # Pour les fichiers video, ajouter un output video pour que QMediaPlayer
        # puisse traiter correctement le fichier (lecture audio + tracking position)
        self.is_video_file = self.media_path and media_icon(self.media_path) == "video"
        if self.is_video_file:
            self.preview_video_widget = QVideoWidget(self)
            self.preview_video_widget.setFixedSize(1, 1)
            self.preview_video_widget.hide()
            self.preview_player.setVideoOutput(self.preview_video_widget)

        # Ne pas charger les images ni les pauses dans le player
        if self.media_path and not is_image and not self.is_tempo:
            self.preview_player.setSource(QUrl.fromLocalFile(self.media_path))

    def toggle_play_pause(self):
        """Toggle play/pause avec timer - synchro preview et player principal"""
        main_playing = self.main_window.player.playbackState() == QMediaPlayer.PlayingState
        preview_playing = self.preview_player.playbackState() == QMediaPlayer.PlayingState

        if preview_playing or main_playing:
            # Arreter les deux
            self.preview_player.pause()
            self.main_window.player.pause()
            self.play_pause_btn.setText("▶")
            self.playback_timer.stop()
        else:
            # Lancer le preview a la position actuelle du curseur
            self.preview_player.setPosition(int(self.playback_position))
            self.preview_player.play()
            self.play_pause_btn.setText("⏸")
            self.playback_timer.start(40)

    def seek_relative(self, delta_ms):
        """Seek relatif (+/- 10s)"""
        current = self.preview_player.position()
        new_pos = max(0, min(current + delta_ms, self.media_duration))
        self.preview_player.setPosition(int(new_pos))

    def zoom_in(self):
        """Zoom avant centre sur le curseur rouge"""
        self.apply_zoom(1.3)

    def zoom_out(self):
        """Zoom arriere centre sur le curseur rouge"""
        self.apply_zoom(1.0 / 1.3)

    def apply_zoom(self, factor):
        """Applique le zoom en gardant le curseur rouge au meme endroit dans la vue"""
        old_zoom = self.current_zoom
        self.current_zoom = max(0.02, min(10.0, self.current_zoom * factor))

        scrollbar = self.tracks_scroll.horizontalScrollBar()
        viewport_width = self.tracks_scroll.viewport().width()

        # Calculer ou est le curseur dans le viewport AVANT le zoom
        old_pixels_per_ms = 0.05 * old_zoom
        cursor_abs_x = 145 + self.playback_position * old_pixels_per_ms
        cursor_viewport_x = cursor_abs_x - scrollbar.value()

        # Appliquer le nouveau zoom aux pistes
        new_pixels_per_ms = 0.05 * self.current_zoom
        for track in self.tracks:
            track.update_zoom(new_pixels_per_ms)
        self.track_waveform.update_zoom(new_pixels_per_ms)

        # Mettre a jour le label
        self.zoom_label.setText(f"{int(self.current_zoom * 100)}%")

        # Calculer la nouvelle position absolue du curseur
        new_cursor_abs_x = 145 + self.playback_position * new_pixels_per_ms

        # Ajuster le scroll pour que le curseur reste au meme endroit dans le viewport
        new_scroll = new_cursor_abs_x - cursor_viewport_x
        scrollbar.setValue(max(0, int(new_scroll)))

        # Forcer le rafraichissement
        self.ruler.update()
        self.tracks_scroll.viewport().update()

    def ruler_mouse_press(self, event):
        """Clic sur ruler pour deplacer le curseur"""
        self.ruler_dragging = True
        self.update_cursor_from_ruler(event)

    def ruler_mouse_move(self, event):
        """Drag sur ruler"""
        if hasattr(self, 'ruler_dragging') and self.ruler_dragging:
            self.update_cursor_from_ruler(event)

    def ruler_mouse_release(self, event):
        """Release sur ruler"""
        self.ruler_dragging = False

    def on_scroll_changed(self, value):
        """Met a jour le ruler quand on scroll"""
        self.ruler.update()

    def update_cursor_from_ruler(self, event):
        """Met a jour curseur depuis position souris (avec auto-scroll aux bords)"""
        x = event.position().x()
        viewport_width = self.ruler.width()
        scrollbar = self.tracks_scroll.horizontalScrollBar()

        # Auto-scroll si pres des bords (zone de 80px)
        edge_zone = 80
        scroll_speed = 30

        if x < edge_zone:
            # Scroll vers la gauche
            new_scroll = max(0, scrollbar.value() - scroll_speed)
            scrollbar.setValue(new_scroll)
        elif x > viewport_width - edge_zone:
            # Scroll vers la droite
            new_scroll = scrollbar.value() + scroll_speed
            scrollbar.setValue(new_scroll)

        # Calculer la position temporelle en tenant compte du scroll actuel
        scroll_offset = scrollbar.value()
        x_in_content = x + scroll_offset

        pixels_per_ms = 0.05 * self.current_zoom
        time_ms = (x_in_content - 145) / pixels_per_ms
        time_ms = max(0, min(time_ms, self.media_duration))

        self.playback_position = time_ms
        self.preview_player.setPosition(int(time_ms))

        # Mettre a jour le compteur
        pos_sec = int(time_ms / 1000)
        self.position_label.setText(f"⏱ {pos_sec // 60}:{pos_sec % 60:02d} / {self.total_time_str}")

        # Rafraichir l'affichage
        self.ruler.update()
        for track in self.tracks:
            track.update()
        self.track_waveform.update()

    def ensure_playhead_visible(self):
        """S'assure que le curseur de lecture est visible - auto-scroll pendant lecture"""
        scrollbar = self.tracks_scroll.horizontalScrollBar()
        viewport_width = self.tracks_scroll.viewport().width()
        scroll_pos = scrollbar.value()

        pixels_per_ms = 0.05 * self.current_zoom
        cursor_abs_x = 145 + int(self.playback_position * pixels_per_ms)

        # Zone visible: de scroll_pos a scroll_pos + viewport_width
        visible_start = scroll_pos
        visible_end = scroll_pos + viewport_width

        # Marge pour anticiper le scroll (150px avant le bord)
        margin = 150

        if cursor_abs_x > visible_end - margin:
            # Le curseur approche du bord droit - scroll pour le garder visible
            new_scroll = cursor_abs_x - viewport_width + margin
            scrollbar.setValue(int(new_scroll))
            self.ruler.update()
        elif cursor_abs_x < visible_start + 50:
            # Le curseur est trop a gauche
            new_scroll = max(0, cursor_abs_x - 50)
            scrollbar.setValue(int(new_scroll))
            self.ruler.update()

    def paint_ruler(self, event):
        """Dessine la regle temporelle avec curseur rouge (synchronise avec scroll)"""
        painter = QPainter(self.ruler)
        painter.fillRect(0, 0, self.ruler.width(), self.ruler.height(), QColor("#1a1a1a"))

        # Recuperer le scroll horizontal pour synchroniser
        scroll_offset = self.tracks_scroll.horizontalScrollBar().value()

        painter.setPen(QColor("#888"))
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)

        pixels_per_ms = 0.05 * self.current_zoom

        if self.current_zoom < 0.5:
            step = 5
        elif self.current_zoom < 1.0:
            step = 2
        else:
            step = 1

        for sec in range(0, int(self.media_duration / 1000) + 1, step):
            x = 145 + int(sec * 1000 * pixels_per_ms) - scroll_offset
            if -50 < x < self.ruler.width() + 50:
                painter.drawLine(x, 25, x, 35)

                if sec >= 60:
                    minutes = sec // 60
                    seconds = sec % 60
                    time_str = f"{minutes}:{seconds:02d}"
                else:
                    time_str = f"{sec}s"

                painter.drawText(x - 18, 18, time_str)

        # Curseur de lecture (rouge) - aussi decale par le scroll
        cursor_x = 145 + int(self.playback_position * pixels_per_ms) - scroll_offset
        if -10 < cursor_x < self.ruler.width() + 10:
            painter.setPen(QPen(QColor("#ff0000"), 3))
            painter.drawLine(cursor_x, 0, cursor_x, self.ruler.height())

            painter.setBrush(QColor("#ff0000"))
            painter.setPen(Qt.NoPen)
            triangle = QPolygon([
                QPoint(cursor_x - 6, 0),
                QPoint(cursor_x + 6, 0),
                QPoint(cursor_x, 10)
            ])
            painter.drawPolygon(triangle)

    def update_playhead(self):
        """Met a jour la position du curseur pendant lecture (preview ou player principal)"""
        playing = False

        if self.preview_player.playbackState() == QMediaPlayer.PlayingState:
            self.playback_position = self.preview_player.position()
            playing = True
        elif self.main_window.player.playbackState() == QMediaPlayer.PlayingState:
            self.playback_position = self.main_window.player.position()
            playing = True

        if playing:
            # Auto-scroll pour suivre le curseur pendant la lecture
            self.ensure_playhead_visible()

            # Mettre a jour le compteur de position
            pos_sec = int(self.playback_position / 1000)
            self.position_label.setText(f"⏱ {pos_sec // 60}:{pos_sec % 60:02d} / {self.total_time_str}")

            self.ruler.update()
            for track in self.tracks:
                track.update()
            self.track_waveform.update()

    def load_existing_sequence(self):
        """Charge la sequence existante si elle existe"""
        if self.media_row in self.main_window.seq.sequences:
            seq = self.main_window.seq.sequences[self.media_row]
            clips_data = seq.get('clips', [])

            track_map = {
                'Face': self.track_face,
                'Douche 1': self.track_douche1,
                'Douche 2': self.track_douche2,
                'Douche 3': self.track_douche3,
                'Contres': self.track_contre,
            }

            for clip_data in clips_data:
                track_name = clip_data.get('track')
                track = track_map.get(track_name)

                if track:
                    color = QColor(clip_data.get('color', '#ffffff'))
                    clip = track.add_clip(
                        clip_data.get('start', 0),
                        clip_data.get('duration', 1000),
                        color,
                        clip_data.get('intensity', 80)
                    )

                    clip.fade_in_duration = clip_data.get('fade_in', 0)
                    clip.fade_out_duration = clip_data.get('fade_out', 0)
                    clip.effect = clip_data.get('effect')
                    clip.effect_speed = clip_data.get('effect_speed', 50)

                    if clip_data.get('color2'):
                        clip.color2 = QColor(clip_data['color2'])

            # Charger la forme d'onde depuis les donnees de sequence
            waveform = seq.get('waveform')
            if waveform:
                self.track_waveform.waveform_data = waveform
                for track in self.tracks:
                    track.waveform_data = waveform

            # Rafraichir toutes les pistes
            for track in self.tracks:
                track.update()

        # Sauvegarder l'etat initial pour undo
        self.save_state()

    def save_sequence(self):
        """Sauvegarde la sequence au format .tui avec effets et bicolore"""
        all_clips = []
        for track in self.tracks:
            for clip in track.clips:
                clip_data = {
                    'track': track.name,
                    'start': clip.start_time,
                    'duration': clip.duration,
                    'color': clip.color.name(),
                    'intensity': clip.intensity,
                    'fade_in': getattr(clip, 'fade_in_duration', 0),
                    'fade_out': getattr(clip, 'fade_out_duration', 0),
                    'effect': getattr(clip, 'effect', None),
                    'effect_speed': getattr(clip, 'effect_speed', 50)
                }

                if hasattr(clip, 'color2') and clip.color2:
                    clip_data['color2'] = clip.color2.name()

                all_clips.append(clip_data)

        self.main_window.seq.sequences[self.media_row] = {
            'clips': all_clips,
            'duration': self.media_duration,
            'waveform': [round(x, 3) for x in self.track_waveform.waveform_data] if self.track_waveform.waveform_data else None
        }

        self.main_window.seq.is_dirty = True

        combo = self.main_window.seq._get_dmx_combo(self.media_row)
        if combo:
            if combo.findText("Play Lumiere") == -1:
                combo.addItem("Play Lumiere")
            combo.blockSignals(True)
            combo.setCurrentText("Play Lumiere")
            combo.blockSignals(False)
            self.main_window.seq.on_dmx_changed(self.media_row, "Play Lumiere")

        QMessageBox.information(self, "Sauvegarde",
            f"Sequence sauvegardee avec succes !\n\n{len(all_clips)} clips")

        self.close_editor()

    def clear_all_clips(self):
        """Efface tous les clips"""
        reply = QMessageBox.question(self, "Tout effacer",
            "Voulez-vous vraiment effacer tous les clips ?",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            for track in self.tracks:
                track.clips.clear()
                track.update()

    def generate_ai_sequence(self):
        """Genere une sequence avec IA"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Generation IA")
        dialog.setFixedSize(550, 450)
        dialog.setStyleSheet("background: #1a1a1a;")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QLabel("Choisissez la dominante de couleur")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        color_combo = QComboBox()
        color_combo.setStyleSheet("""
            QComboBox {
                background: #2a2a2a;
                color: white;
                border: 1px solid #3a3a3a;
                padding: 10px;
                border-radius: 6px;
                font-size: 14px;
            }
        """)

        colors = [
            ("Rouge energique", "#ff0000"),
            ("Vert apaisant", "#00ff00"),
            ("Bleu froid", "#0000ff"),
            ("Jaune chaleureux", "#c8c800"),
            ("Violet mystique", "#ff00ff"),
            ("Orange dynamique", "#ff8800"),
            ("Blanc pur", "#ffffff"),
            ("Arc-en-ciel (mix)", "rainbow"),
            ("Bicolore Rouge+Bleu", "rb"),
            ("Bicolore Vert+Jaune", "gy"),
        ]

        for name, _ in colors:
            color_combo.addItem(name)

        layout.addWidget(color_combo)

        # Checkboxes pistes
        tracks_label = QLabel("Pistes a generer :")
        tracks_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(tracks_label)

        tracks_checks = {}
        for track in self.tracks:
            clip_count = len(track.clips)
            checkbox = QCheckBox(f"{track.name} {'(' + str(clip_count) + ' clips)' if clip_count > 0 else ''}")
            checkbox.setChecked(True)
            checkbox.setStyleSheet("""
                QCheckBox { color: white; font-size: 13px; spacing: 10px; }
                QCheckBox::indicator { width: 20px; height: 20px; }
            """)
            tracks_checks[track] = checkbox
            layout.addWidget(checkbox)

        # Progress
        progress = QProgressBar()
        progress.setVisible(False)
        progress.setStyleSheet("""
            QProgressBar {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                text-align: center;
                color: white;
                height: 30px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8B00FF, stop:1 #FF00FF);
                border-radius: 6px;
            }
        """)
        layout.addWidget(progress)

        status_label = QLabel("")
        status_label.setStyleSheet("color: #888; font-size: 12px;")
        status_label.setVisible(False)
        layout.addWidget(status_label)

        layout.addStretch()

        # Boutons
        btn_layout = QHBoxLayout()

        cancel_btn = QPushButton("❌ Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        cancel_btn.setFixedHeight(40)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 20px;
                font-size: 14px;
            }
            QPushButton:hover { background: #4a4a4a; }
        """)
        btn_layout.addWidget(cancel_btn)

        generate_btn = QPushButton("✨ Generer")
        generate_btn.setFixedHeight(40)
        generate_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8B00FF, stop:1 #FF00FF);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 30px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #9B10FF, stop:1 #FF10FF);
            }
        """)

        def start_generation():
            generate_btn.setEnabled(False)
            color_combo.setEnabled(False)
            progress.setVisible(True)
            status_label.setVisible(True)

            selected_idx = color_combo.currentIndex()
            _, color_code = colors[selected_idx]

            selected_tracks = [track for track, checkbox in tracks_checks.items() if checkbox.isChecked()]
            self.perform_ai_generation(color_code, selected_tracks, progress, status_label, dialog)

        generate_btn.clicked.connect(start_generation)
        btn_layout.addWidget(generate_btn)

        layout.addLayout(btn_layout)
        dialog.exec()

    def perform_ai_generation(self, color_code, selected_tracks, progress, status_label, dialog):
        """Genere les clips avec progression"""
        # Effacer clips sur pistes selectionnees
        for track in selected_tracks:
            track.clips.clear()

        progress.setValue(10)
        status_label.setText("Analyse du rythme...")
        QApplication.processEvents()

        # Parametres selon couleur
        if color_code == "rainbow":
            main_colors = [QColor("#ff0000"), QColor("#00ff00"), QColor("#0000ff"),
                          QColor("#c8c800"), QColor("#ff00ff"), QColor("#00ffff")]
            secondary_colors = [QColor("#ff8800"), QColor("#00ff88"), QColor("#8800ff")]
        elif color_code == "rb":
            main_colors = [QColor("#ff0000"), QColor("#0000ff")]
            secondary_colors = [QColor("#ff00ff"), QColor("#ff8800")]
        elif color_code == "gy":
            main_colors = [QColor("#00ff00"), QColor("#c8c800")]
            secondary_colors = [QColor("#88ff00"), QColor("#ffff88")]
        else:
            main_colors = [QColor(color_code)]
            base = QColor(color_code)
            secondary_colors = [
                QColor(min(255, base.red() + 30), base.green(), base.blue()),
                QColor(base.red(), min(255, base.green() + 30), base.blue()),
            ]

        progress.setValue(30)
        status_label.setText("Creation des variations...")
        QApplication.processEvents()

        beat_duration = 500
        duration_ms = self.media_duration
        current_time = 0
        clip_count = 0

        has_face = self.track_face in selected_tracks
        has_douche1 = self.track_douche1 in selected_tracks
        has_douche2 = self.track_douche2 in selected_tracks
        has_douche3 = self.track_douche3 in selected_tracks
        has_contre = self.track_contre in selected_tracks

        while current_time < duration_ms:
            beats = random.choice([2, 4, 8])
            clip_duration = beat_duration * beats

            if has_face:
                self.track_face.add_clip(current_time, clip_duration, QColor("#ffffff"), random.randint(85, 100))
                clip_count += 1

            selected_douches = []
            if has_douche1:
                selected_douches.append(self.track_douche1)
            if has_douche2:
                selected_douches.append(self.track_douche2)
            if has_douche3:
                selected_douches.append(self.track_douche3)

            for douche in selected_douches:
                color = random.choice(main_colors)
                if random.random() < 0.2 and secondary_colors:
                    clip = douche.add_clip(current_time, clip_duration, color, random.randint(75, 95))
                    clip.color2 = random.choice(secondary_colors)
                else:
                    douche.add_clip(current_time, clip_duration, color, random.randint(75, 95))
                clip_count += 1

            if has_contre:
                contre_color = random.choice(main_colors) if random.random() < 0.6 else random.choice(secondary_colors)
                self.track_contre.add_clip(current_time, clip_duration, contre_color, random.randint(70, 90))
                clip_count += 1

            current_time += clip_duration

            progress.setValue(30 + int((current_time / duration_ms) * 60))
            QApplication.processEvents()

        progress.setValue(100)
        status_label.setText(f"{clip_count} clips crees !")
        QApplication.processEvents()

        QTimer.singleShot(1000, dialog.accept)

    def wheelEvent(self, event):
        """Scroll souris = Zoom/Dezoom centre sur la barre rouge"""
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()

    def keyPressEvent(self, event):
        """Raccourcis clavier"""
        if event.key() == Qt.Key_Space:
            self.toggle_play_pause()
            event.accept()
            return
        elif event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            self.undo()
            event.accept()
            return
        elif event.key() == Qt.Key_Y and event.modifiers() & Qt.ControlModifier:
            self.redo()
            event.accept()
            return
        elif event.key() == Qt.Key_Delete:
            self.delete_selected_clips()
            event.accept()
            return
        elif event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            self.select_all_clips()
            event.accept()
            return
        elif event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self.copy_selected_clips()
            event.accept()
            return
        elif event.key() == Qt.Key_X and event.modifiers() & Qt.ControlModifier:
            self.cut_selected_clips()
            event.accept()
            return
        elif event.key() == Qt.Key_V and event.modifiers() & Qt.ControlModifier:
            self.paste_clips()
            event.accept()
            return
        elif event.key() == Qt.Key_C:
            # Touche C seule = Mode CUT
            self.cut_btn.setChecked(not self.cut_btn.isChecked())
            self.toggle_cut_mode()
            event.accept()
            return
        elif event.key() == Qt.Key_Escape:
            # Echap = Desactiver mode cut et deselectionner
            if self.cut_mode:
                self.cut_btn.setChecked(False)
                self.toggle_cut_mode()
            self.clear_all_selections()
            event.accept()
            return
        else:
            super().keyPressEvent(event)

    def select_all_clips(self):
        """Selectionne tous les clips de toutes les pistes"""
        for track in self.tracks:
            track.selected_clips = track.clips[:]
            track.update()

    def delete_selected_clips(self):
        """Supprime tous les clips selectionnes"""
        if not any(track.selected_clips for track in self.tracks):
            return

        total_deleted = 0
        for track in self.tracks:
            if track.selected_clips:
                count = len(track.selected_clips)
                for clip in track.selected_clips[:]:
                    track.clips.remove(clip)
                track.selected_clips.clear()
                track.update()
                total_deleted += count

        self.save_state()
        print(f"🗑️ {total_deleted} clip(s) supprime(s)")

    def copy_selected_clips(self):
        """Copie les clips selectionnes dans le clipboard"""
        self.clipboard = []
        min_start = None
        for track in self.tracks:
            for clip in track.selected_clips:
                if min_start is None or clip.start_time < min_start:
                    min_start = clip.start_time
                self.clipboard.append({
                    'track': track.name,
                    'start': clip.start_time,
                    'duration': clip.duration,
                    'color': clip.color.name(),
                    'color2': clip.color2.name() if clip.color2 else None,
                    'intensity': clip.intensity,
                    'fade_in': clip.fade_in_duration,
                    'fade_out': clip.fade_out_duration,
                    'effect': clip.effect,
                    'effect_speed': clip.effect_speed,
                })
        # Stocker les offsets relatifs au premier clip
        if min_start is not None:
            for item in self.clipboard:
                item['offset'] = item['start'] - min_start
        if self.clipboard:
            print(f"📋 {len(self.clipboard)} clip(s) copie(s)")

    def cut_selected_clips(self):
        """Coupe les clips selectionnes (copie + suppression)"""
        self.copy_selected_clips()
        if self.clipboard:
            self.delete_selected_clips()
            print(f"✂️ {len(self.clipboard)} clip(s) coupe(s)")

    def paste_clips(self):
        """Colle les clips du clipboard a la position du curseur"""
        if not self.clipboard:
            return

        paste_time = self.playback_position
        track_map = {t.name: t for t in self.tracks}

        self.clear_all_selections()
        count = 0
        for item in self.clipboard:
            track = track_map.get(item['track'])
            if not track:
                continue
            start = paste_time + item.get('offset', 0)
            clip = track.add_clip(start, item['duration'], QColor(item['color']), item['intensity'])
            if item.get('color2'):
                clip.color2 = QColor(item['color2'])
            clip.fade_in_duration = item.get('fade_in', 0)
            clip.fade_out_duration = item.get('fade_out', 0)
            clip.effect = item.get('effect')
            clip.effect_speed = item.get('effect_speed', 50)
            track.selected_clips.append(clip)
            count += 1

        for track in self.tracks:
            track.update()
        self.save_state()
        print(f"📌 {count} clip(s) colle(s) a {paste_time/1000:.1f}s")

    def save_state(self):
        """Sauvegarde l'etat actuel pour undo"""
        state = []
        for track in self.tracks:
            for clip in track.clips:
                clip_data = {
                    'track': track.name,
                    'start': clip.start_time,
                    'duration': clip.duration,
                    'color': clip.color.name(),
                    'color2': clip.color2.name() if clip.color2 else None,
                    'intensity': clip.intensity,
                    'fade_in': clip.fade_in_duration,
                    'fade_out': clip.fade_out_duration,
                    'effect': clip.effect,
                    'effect_speed': clip.effect_speed,
                }
                state.append(clip_data)

        # Tronquer l'historique si on a fait undo puis nouvelle action
        self.history = self.history[:self.history_index + 1]
        self.history.append(state)
        self.history_index += 1

        # Limiter la taille de l'historique
        if len(self.history) > 50:
            self.history.pop(0)
            self.history_index -= 1

        print(f"💾 Etat sauvegarde: {len(state)} clips, history_index={self.history_index}")

    def _restore_state(self, state):
        """Restaure un etat depuis l'historique"""
        for track in self.tracks:
            track.clips.clear()
            track.selected_clips.clear()

        track_map = {
            'Face': self.track_face,
            'Douche 1': self.track_douche1,
            'Douche 2': self.track_douche2,
            'Douche 3': self.track_douche3,
            'Contres': self.track_contre,
        }

        for clip_data in state:
            track = track_map.get(clip_data.get('track'))
            if track:
                color = QColor(clip_data.get('color', '#ffffff'))
                clip = track.add_clip_direct(
                    clip_data.get('start', 0),
                    clip_data.get('duration', 1000),
                    color,
                    clip_data.get('intensity', 80)
                )
                if clip_data.get('color2'):
                    clip.color2 = QColor(clip_data['color2'])
                clip.fade_in_duration = clip_data.get('fade_in', 0)
                clip.fade_out_duration = clip_data.get('fade_out', 0)
                clip.effect = clip_data.get('effect')
                clip.effect_speed = clip_data.get('effect_speed', 50)

        for track in self.tracks:
            track.update()

    def undo(self):
        """Annuler la derniere action"""
        if len(self.history) == 0 or self.history_index <= 0:
            return

        self.history_index -= 1
        self._restore_state(self.history[self.history_index])
        print(f"↶ Undo effectue (index={self.history_index})")

    def redo(self):
        """Retablir la derniere action annulee"""
        if self.history_index >= len(self.history) - 1:
            return

        self.history_index += 1
        self._restore_state(self.history[self.history_index])
        print(f"↷ Redo effectue (index={self.history_index})")

    def toggle_cut_mode_from_menu(self):
        """Active/desactive le mode CUT depuis le menu"""
        self.cut_btn.setChecked(not self.cut_btn.isChecked())
        self.toggle_cut_mode()

    def apply_effect_to_selection(self, effect):
        """Applique un effet aux clips selectionnes"""
        selected = []
        for track in self.tracks:
            selected.extend(track.selected_clips)

        if not selected:
            QMessageBox.warning(self, "Aucune selection",
                "Selectionnez un ou plusieurs blocs d'abord.")
            return

        for clip in selected:
            clip.effect = effect
        for track in self.tracks:
            track.update()
        self.save_state()

    def apply_fade_in_to_selection(self):
        """Applique un fade in aux clips selectionnes"""
        selected = []
        for track in self.tracks:
            selected.extend(track.selected_clips)

        if not selected:
            QMessageBox.warning(self, "Aucune selection",
                "Selectionnez un ou plusieurs blocs d'abord.")
            return

        for clip in selected:
            clip.fade_in_duration = 1000
        for track in self.tracks:
            track.update()
        self.save_state()

    def apply_fade_out_to_selection(self):
        """Applique un fade out aux clips selectionnes"""
        selected = []
        for track in self.tracks:
            selected.extend(track.selected_clips)

        if not selected:
            QMessageBox.warning(self, "Aucune selection",
                "Selectionnez un ou plusieurs blocs d'abord.")
            return

        for clip in selected:
            clip.fade_out_duration = 1000
        for track in self.tracks:
            track.update()
        self.save_state()

    def remove_fades_from_selection(self):
        """Supprime les fades des clips selectionnes"""
        selected = []
        for track in self.tracks:
            selected.extend(track.selected_clips)

        if not selected:
            QMessageBox.warning(self, "Aucune selection",
                "Selectionnez un ou plusieurs blocs d'abord.")
            return

        for clip in selected:
            clip.fade_in_duration = 0
            clip.fade_out_duration = 0
        for track in self.tracks:
            track.update()
        self.save_state()

    def toggle_cut_mode(self):
        """Active/desactive le mode CUT avec curseur visuel"""
        self.cut_mode = not self.cut_mode

        if self.cut_mode:
            # Curseur ciseaux sur toute la fenetre et les pistes
            self.setCursor(Qt.SplitHCursor)
            for track in self.tracks:
                track.setCursor(Qt.SplitHCursor)
            self.track_waveform.setCursor(Qt.SplitHCursor)
            print("✂️ Mode CUT active - Cliquez sur un clip pour le couper")
        else:
            # Restaurer curseur normal
            self.setCursor(Qt.ArrowCursor)
            for track in self.tracks:
                track.setCursor(Qt.ArrowCursor)
            self.track_waveform.setCursor(Qt.ArrowCursor)

    def clear_all_selections(self):
        """Deselectionne tous les clips sur toutes les pistes"""
        for track in self.tracks:
            track.selected_clips.clear()
            track.update()

    def start_rubber_band(self, pos, origin_track):
        """Demarre la selection rectangulaire multi-pistes"""
        self.rubber_band_active = True
        self.rubber_band_start = pos
        self.rubber_band_origin_track = origin_track
        self.rubber_band_rect = None
        self.clear_all_selections()

        # Afficher et redimensionner l'overlay
        self.rubber_band_overlay.setGeometry(self.tracks_scroll.viewport().rect())
        self.rubber_band_overlay.show()
        self.rubber_band_overlay.raise_()

    def update_rubber_band(self, current_pos):
        """Met a jour le rectangle de selection avec overlay visible"""
        if not self.rubber_band_active or not self.rubber_band_start:
            return

        # Calculer le rectangle dans les coordonnees du viewport
        viewport = self.tracks_scroll.viewport()
        start_in_viewport = viewport.mapFrom(self, self.rubber_band_start)
        current_in_viewport = viewport.mapFrom(self, current_pos)

        x1 = min(start_in_viewport.x(), current_in_viewport.x())
        y1 = min(start_in_viewport.y(), current_in_viewport.y())
        x2 = max(start_in_viewport.x(), current_in_viewport.x())
        y2 = max(start_in_viewport.y(), current_in_viewport.y())

        self.rubber_band_rect = QRect(x1, y1, x2 - x1, y2 - y1)

        # Mettre a jour l'overlay
        self.rubber_band_overlay.set_rect(self.rubber_band_rect)

        # Selectionner les clips dans le rectangle sur TOUTES les pistes
        scroll_offset = self.tracks_scroll.horizontalScrollBar().value()
        v_scroll_offset = self.tracks_scroll.verticalScrollBar().value()
        pixels_per_ms = 0.05 * self.current_zoom

        for track in self.tracks:
            # Position Y de la piste dans le conteneur
            track_y_in_container = track.mapTo(self.tracks_container, QPoint(0, 0)).y()
            # Position Y dans le viewport (avec scroll)
            track_y_in_viewport = track_y_in_container - v_scroll_offset

            track.selected_clips.clear()

            for clip in track.clips:
                clip_x = 145 + int(clip.start_time * pixels_per_ms) - scroll_offset
                clip_width = int(clip.duration * pixels_per_ms)

                # Rectangle du clip dans le viewport
                clip_rect = QRect(clip_x, track_y_in_viewport + 10, clip_width, 40)

                if self.rubber_band_rect.intersects(clip_rect):
                    track.selected_clips.append(clip)

            track.update()

    def end_rubber_band(self):
        """Termine la selection rectangulaire"""
        self.rubber_band_active = False
        self.rubber_band_start = None
        self.rubber_band_rect = None
        self.rubber_band_origin_track = None

        # Cacher l'overlay
        self.rubber_band_overlay.clear()
        self.rubber_band_overlay.hide()

        # Compter les clips selectionnes
        total = sum(len(track.selected_clips) for track in self.tracks)
        if total > 0:
            print(f"📦 {total} clip(s) selectionne(s) sur plusieurs pistes")

    def mousePressEvent(self, event):
        """Gere le clic pour demarrer le rubber band si dans la zone des pistes"""
        # Verifier si le clic est dans la zone des pistes (viewport du scroll)
        viewport = self.tracks_scroll.viewport()
        pos_in_viewport = viewport.mapFrom(self, event.pos())

        if viewport.rect().contains(pos_in_viewport):
            # Verifier qu'on est dans la zone timeline (pas sur les labels)
            if pos_in_viewport.x() > 145:
                self.rubber_band_active = True
                self.rubber_band_start = event.pos()
                self.clear_all_selections()

                # Preparer l'overlay
                self.rubber_band_overlay.setGeometry(viewport.rect())
                self.rubber_band_overlay.show()
                self.rubber_band_overlay.raise_()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Gere le deplacement pour le rubber band"""
        if self.rubber_band_active and self.rubber_band_start:
            self.update_rubber_band(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Termine le rubber band"""
        if self.rubber_band_active:
            self.end_rubber_band()
        super().mouseReleaseEvent(event)

    def close_editor(self):
        """Ferme l'editeur"""
        self.preview_player.stop()
        self.reject()
