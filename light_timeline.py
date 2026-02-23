"""
Composants de timeline lumiere : LightClip, ColorPalette, LightTrack
Version complete avec toutes les fonctionnalites:
- Bicolores draggables
- Anti-collision (pas de chevauchement)
- Fades etirables
- Forme d'onde audio style Virtual DJ PRO
- Curseur rouge sur toutes les pistes
- Mode cut (coupe ou on clique)
- Selection multiple multi-pistes avec drag groupe
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMenu, QComboBox, QDialog, QMessageBox, QInputDialog, QSlider, QApplication
)
from PySide6.QtCore import Qt, QPoint, QSize, QRect, QMimeData
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QPolygon, QCursor,
    QPixmap, QIcon, QLinearGradient, QDrag, QPainterPath
)

import wave
import array
import random
import math
import struct
import time

try:
    import miniaudio
    HAS_MINIAUDIO = True
except ImportError:
    HAS_MINIAUDIO = False

try:
    from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
    from PySide6.QtCore import QUrl, QCoreApplication, QEventLoop
    HAS_QAUDIO_DECODER = True
except ImportError:
    HAS_QAUDIO_DECODER = False


class LightClip:
    """Un clip de lumiere sur la timeline avec effets et bicolore"""

    def __init__(self, start_time, duration, color, intensity, parent_track):
        self.start_time = start_time  # ms
        self.duration = duration  # ms
        self.color = color  # QColor
        self.color2 = None  # QColor pour bicolore
        self.intensity = intensity  # 0-100
        self.parent_track = parent_track

        # Effets
        self.effect = None
        self.effect_speed = 50

        # Fades
        self.fade_in_duration = 0
        self.fade_out_duration = 0

        # Position stockee pour interactions souris
        self.x_pos = 0
        self.width_val = 0


class ColorPalette(QWidget):
    """Palette de couleurs draggable avec VRAIES couleurs + BICOLORES"""

    def __init__(self, parent_editor):
        super().__init__()
        self.parent_editor = parent_editor
        self.setFixedHeight(70)
        self.setStyleSheet("background: #1a1a1a; border-top: 2px solid #3a3a3a;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)

        # Couleurs disponibles
        self.colors = [
            ("Rouge", QColor(255, 0, 0)),
            ("Vert", QColor(0, 200, 0)),
            ("Bleu", QColor(0, 0, 255)),
            ("Jaune", QColor(255, 255, 0)),
            ("Magenta", QColor(255, 0, 255)),
            ("Cyan", QColor(0, 255, 255)),
            ("Blanc", QColor(255, 255, 255)),
            ("Orange", QColor(255, 128, 0)),
            ("Violet", QColor(128, 0, 255)),
        ]

        # Couleurs simples
        for name, color in self.colors:
            btn = QPushButton("")
            btn.setFixedSize(50, 50)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color.name()};
                    border: 3px solid #3a3a3a;
                    border-radius: 8px;
                }}
                QPushButton:hover {{
                    border: 3px solid white;
                }}
            """)
            btn.setProperty("color", color)
            btn.setProperty("color_name", name)
            btn.mousePressEvent = lambda e, c=color: self.start_drag(e, c)
            layout.addWidget(btn)

        layout.addSpacing(20)

        # === DOUBLES COULEURS ===
        self.bicolors = [
            ("R+V", QColor(255, 0, 0), QColor(0, 200, 0)),
            ("R+O", QColor(255, 0, 0), QColor(255, 128, 0)),
            ("R+Rose", QColor(255, 0, 0), QColor(255, 105, 180)),
            ("B+C", QColor(0, 0, 255), QColor(0, 255, 255)),
            ("V+J", QColor(0, 200, 0), QColor(255, 255, 0)),
            ("B+V", QColor(0, 0, 255), QColor(128, 0, 255)),
            ("O+J", QColor(255, 128, 0), QColor(255, 255, 0)),
            ("C+V", QColor(0, 255, 255), QColor(128, 0, 255)),
        ]

        for name, col1, col2 in self.bicolors:
            btn = QPushButton("")
            btn.setFixedSize(50, 50)

            pixmap = QPixmap(50, 50)
            pixmap.fill(Qt.transparent)
            painter_btn = QPainter(pixmap)
            painter_btn.setRenderHint(QPainter.Antialiasing)

            path = QPainterPath()
            path.addRoundedRect(0, 0, 50, 50, 8, 8)
            painter_btn.setClipPath(path)

            painter_btn.fillRect(0, 0, 25, 50, col1)
            painter_btn.fillRect(25, 0, 25, 50, col2)
            painter_btn.end()

            btn.setIcon(QIcon(pixmap))
            btn.setIconSize(QSize(50, 50))
            btn.setStyleSheet("""
                QPushButton {
                    border: 3px solid #3a3a3a;
                    border-radius: 8px;
                }
                QPushButton:hover {
                    border: 3px solid white;
                }
            """)
            btn.setProperty("color1", col1)
            btn.setProperty("color2", col2)
            btn.mousePressEvent = lambda e, c1=col1, c2=col2: self.start_bicolor_drag(e, c1, c2)
            layout.addWidget(btn)

        layout.addStretch()

    def start_drag(self, event, color):
        """Demarre un drag&drop de couleur"""
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(color.name())
        drag.setMimeData(mime_data)

        pixmap = QPixmap(50, 50)
        pixmap.fill(color)
        drag.setPixmap(pixmap)

        drag.exec(Qt.CopyAction)

    def start_bicolor_drag(self, event, color1, color2):
        """Demarre un drag&drop de bicolore"""
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"{color1.name()}#{color2.name()}")
        drag.setMimeData(mime_data)

        pixmap = QPixmap(50, 50)
        painter = QPainter(pixmap)
        painter.fillRect(0, 0, 25, 50, color1)
        painter.fillRect(25, 0, 25, 50, color2)
        painter.end()
        drag.setPixmap(pixmap)

        drag.exec(Qt.CopyAction)


class LightTrack(QWidget):
    """Une piste de lumiere (une ligne dans la timeline)"""

    def __init__(self, name, total_duration, parent_editor):
        super().__init__()
        self.name = name
        self.total_duration = total_duration
        self.parent_editor = parent_editor
        self.clips = []
        self.pixels_per_ms = 0.05

        self.setMinimumHeight(100 if name == "Audio" else 60)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QWidget {
                background: #0a0a0a;
                border-bottom: 1px solid #2a2a2a;
            }
        """)

        self.label = QLabel(name, self)
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                background: #2a2a2a;
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid #3a3a3a;
            }
        """)
        self.label.setFixedWidth(130)
        self.label.move(5, 12)

        # Variables pour interaction souris
        self.dragging_clip = None
        self.drag_offset = 0
        self.drag_start_positions = {}  # Pour drag multi-clips
        self.resizing_clip = None
        self.resize_edge = None
        self.selected_clips = []
        self.saved_positions = {}

        # Position du clic droit pour "Couper ici"
        self.last_context_click_x = 0

        # Forme d'onde audio
        self.waveform_data = None

        self.setMouseTracking(True)

    def generate_waveform(self, audio_path, max_samples=5000, progress_callback=None, cancel_check=None):
        """Genere des donnees de forme d'onde a partir d'un fichier audio ou video"""
        print(f"🎵 Generation forme d'onde: {audio_path}")

        # Detecter les fichiers video -> extraction audio via ffmpeg
        ext = ''
        if '.' in audio_path:
            ext = audio_path.rsplit('.', 1)[-1].lower()
        video_extensions = ['mp4', 'mov', 'avi', 'mkv', 'wmv', 'flv', 'webm', 'm4v', 'mpg', 'mpeg']

        if ext in video_extensions:
            print(f"   Fichier video detecte (.{ext}), tentative extraction audio...")
            # Essai 1: ffmpeg
            result = self._extract_waveform_ffmpeg(audio_path, max_samples, cancel_check=cancel_check)
            if result:
                return result
            if cancel_check and cancel_check():
                return None
            # Essai 2: QAudioDecoder (natif Qt, pas de dependance externe)
            result = self._extract_waveform_qt(audio_path, max_samples, progress_callback=progress_callback)
            if result:
                return result
            print("   Aucune methode disponible pour extraire l'audio de la video")
            return None

        # Essayer WAV natif d'abord (rapide)
        try:
            with wave.open(audio_path, 'rb') as wav_file:
                n_channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                n_frames = wav_file.getnframes()

                print(f"   WAV detecte: {n_channels}ch, {sampwidth*8}bit, {framerate}Hz")

                frames = wav_file.readframes(n_frames)

                if sampwidth == 1:
                    dtype = 'B'
                    audio_data = array.array(dtype, frames)
                    audio_data = [x - 128 for x in audio_data]
                elif sampwidth == 2:
                    dtype = 'h'
                    audio_data = array.array(dtype, frames)
                else:
                    return None

                if n_channels == 2:
                    audio_data = [abs(audio_data[i] + audio_data[i+1]) // 2 for i in range(0, len(audio_data), 2)]
                else:
                    audio_data = [abs(x) for x in audio_data]

                return self._downsample_waveform(audio_data, max_samples)

        except wave.Error:
            print(f"   Pas un fichier WAV, decodage via miniaudio...")
            result = self._decode_with_miniaudio(audio_path, max_samples, cancel_check=cancel_check)
            if result:
                return result
            if cancel_check and cancel_check():
                return None
            # Fallback QAudioDecoder pour les formats non supportes par miniaudio
            return self._extract_waveform_qt(audio_path, max_samples, progress_callback=progress_callback)

        except Exception as e:
            print(f"❌ Erreur generation forme d'onde: {e}")
            return None

    def _decode_with_miniaudio(self, audio_path, max_samples, cancel_check=None):
        """Decode un fichier audio (MP3/FLAC/OGG/AAC...) via miniaudio ou subprocess"""
        # Essai 1 : miniaudio en direct (si installe sur ce Python)
        if HAS_MINIAUDIO:
            try:
                decoded = miniaudio.decode_file(
                    audio_path,
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=1,
                    sample_rate=22050
                )
                samples = array.array('h', decoded.samples)
                audio_data = [abs(s) for s in samples]
                print(f"   miniaudio direct: {len(audio_data)} samples")
                return self._downsample_waveform(audio_data, max_samples)
            except Exception as e:
                print(f"   ⚠️ miniaudio direct echoue: {e}")

        # Essai 2 : subprocess vers Python 3.12 qui a miniaudio
        return self._decode_via_subprocess(audio_path, max_samples, cancel_check=cancel_check)

    def _decode_via_subprocess(self, audio_path, max_samples, cancel_check=None):
        """Decode via subprocess Python 3.12 (qui a miniaudio installe)"""
        import subprocess
        import json
        import os
        import threading

        # Chercher Python 3.12
        py312 = r"C:\Users\nikop\AppData\Local\Programs\Python\Python312\python.exe"
        if not os.path.exists(py312):
            for p in [r"C:\Python312\python.exe", r"C:\Python\python.exe"]:
                if os.path.exists(p):
                    py312 = p
                    break
            else:
                print(f"   ⚠️ Python 3.12 introuvable pour miniaudio")
                return None

        # Script inline qui decode et renvoie les amplitudes en JSON
        script = f'''
import miniaudio, array, json, sys
decoded = miniaudio.decode_file(
    r"{audio_path}",
    output_format=miniaudio.SampleFormat.SIGNED16,
    nchannels=1,
    sample_rate=22050
)
samples = array.array("h", decoded.samples)
step = max(1, len(samples) // {max_samples})
waveform = []
for i in range(0, len(samples), step):
    chunk = [abs(samples[j]) for j in range(i, min(i+step, len(samples)))]
    waveform.append(max(chunk))
max_val = max(waveform) if waveform else 1
waveform = [x / max_val for x in waveform] if max_val > 0 else waveform
print(json.dumps(waveform))
'''
        # Utiliser un thread pour eviter le deadlock de pipe (stdout peut depasser le buffer)
        proc_ref = [None]
        result_holder = [None]
        error_holder = [None]

        def run_proc():
            try:
                proc = subprocess.Popen(
                    [py312, "-c", script],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                proc_ref[0] = proc
                # communicate() gere correctement le buffering
                stdout, stderr = proc.communicate(timeout=30)
                result_holder[0] = (proc.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                if proc_ref[0]:
                    proc_ref[0].kill()
                    proc_ref[0].communicate()
                print("   ⚠️ Subprocess timeout (30s)")
            except Exception as e:
                error_holder[0] = e

        thread = threading.Thread(target=run_proc, daemon=True)
        thread.start()

        start_t = time.time()
        while thread.is_alive():
            if cancel_check and cancel_check():
                if proc_ref[0]:
                    proc_ref[0].kill()
                return None
            QApplication.processEvents()
            time.sleep(0.05)
            if time.time() - start_t > 35:
                if proc_ref[0]:
                    proc_ref[0].kill()
                return None

        if error_holder[0] or result_holder[0] is None:
            if error_holder[0]:
                print(f"   ❌ Erreur subprocess: {error_holder[0]}")
            return None

        returncode, stdout, stderr = result_holder[0]
        if returncode != 0:
            print(f"   ⚠️ Subprocess erreur: {stderr[:200]}")
            return None

        try:
            waveform = json.loads(stdout.strip())
            print(f"   ✅ subprocess Python3.12 miniaudio: {len(waveform)} points")
            self.waveform_data = waveform
            return waveform
        except Exception as e:
            print(f"   ❌ Erreur parsing JSON: {e}")
            return None

    def _extract_waveform_ffmpeg(self, media_path, max_samples, cancel_check=None):
        """Extrait la forme d'onde d'un fichier video via ffmpeg"""
        import subprocess
        import tempfile
        import os

        temp_wav = None
        try:
            temp_wav = tempfile.mktemp(suffix='.wav')

            # ffmpeg: extraire l'audio en WAV mono 22050Hz 16-bit
            cmd = [
                'ffmpeg', '-i', media_path, '-vn', '-ac', '1', '-ar', '22050',
                '-acodec', 'pcm_s16le', '-y', temp_wav
            ]

            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            start_t = time.time()
            while proc.poll() is None:
                if cancel_check and cancel_check():
                    proc.kill()
                    proc.communicate()
                    return None
                QApplication.processEvents()
                time.sleep(0.1)
                if time.time() - start_t > 120:
                    proc.kill()
                    proc.communicate()
                    print("   ⚠️ ffmpeg timeout (120s)")
                    return None

            _, stderr_bytes = proc.communicate()
            if proc.returncode != 0:
                stderr_short = stderr_bytes.decode(errors='replace')[:200]
                print(f"   ⚠️ ffmpeg extraction echouee: {stderr_short}")
                return None

            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 100:
                print("   ⚠️ Fichier WAV extrait vide ou inexistant")
                return None

            # Lire le WAV extrait
            with wave.open(temp_wav, 'rb') as wav_file:
                n_frames = wav_file.getnframes()
                sampwidth = wav_file.getsampwidth()

                if sampwidth != 2 or n_frames == 0:
                    print(f"   ⚠️ Format WAV inattendu: {sampwidth}bytes, {n_frames} frames")
                    return None

                frames = wav_file.readframes(n_frames)
                audio_data = array.array('h', frames)
                audio_data = [abs(x) for x in audio_data]
                print(f"   ✅ ffmpeg extraction: {len(audio_data)} samples")
                return self._downsample_waveform(audio_data, max_samples)

        except FileNotFoundError:
            print("   ⚠️ ffmpeg non trouve dans le PATH")
            return None
        except Exception as e:
            print(f"   ❌ Erreur ffmpeg: {e}")
            return None
        finally:
            if temp_wav:
                try:
                    os.unlink(temp_wav)
                except:
                    pass

    def _extract_waveform_qt(self, media_path, max_samples, progress_callback=None):
        """Extrait la forme d'onde via QAudioDecoder (natif Qt, fonctionne pour audio ET video)"""
        if not HAS_QAUDIO_DECODER:
            print("   QAudioDecoder non disponible")
            return None

        import time

        print(f"   Tentative QAudioDecoder pour: {media_path}")

        try:
            decoder = QAudioDecoder()

            # Format basse resolution pour vitesse : mono, 16-bit, 8000Hz
            fmt = QAudioFormat()
            fmt.setSampleRate(8000)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.Int16)
            decoder.setAudioFormat(fmt)

            decoder.setSource(QUrl.fromLocalFile(media_path))

            # Accumuler directement les pics par blocs (pas tous les samples)
            chunk_peaks = []
            samples_per_chunk = max(1, (8000 * 120) // max_samples)  # ~120s couvert
            current_chunk = []
            finished = [False]
            error_msg = [None]
            total_duration_ms = [0]

            def on_buffer_ready():
                nonlocal current_chunk
                buf = decoder.read()
                if buf.isValid():
                    raw = bytes(buf.data())
                    n = len(raw) // 2
                    if n == 0:
                        return
                    samples = array.array('h', raw)
                    for v in samples:
                        current_chunk.append(abs(v))
                        if len(current_chunk) >= samples_per_chunk:
                            chunk_peaks.append(max(current_chunk))
                            current_chunk = []

            def on_finished():
                finished[0] = True

            def on_error(error):
                error_msg[0] = str(decoder.errorString())
                finished[0] = True

            def on_duration_changed(dur):
                if dur > 0:
                    total_duration_ms[0] = dur

            decoder.bufferReady.connect(on_buffer_ready)
            decoder.finished.connect(on_finished)
            decoder.error.connect(on_error)
            decoder.durationChanged.connect(on_duration_changed)

            decoder.start()

            # Attendre la fin du decodage (max 120s)
            start_time = time.time()
            last_progress_pct = [0]
            while not finished[0] and (time.time() - start_time) < 120:
                QCoreApplication.processEvents()
                time.sleep(0.005)

                # Rapporter la progression
                if progress_callback and total_duration_ms[0] > 0:
                    pos = decoder.position()
                    if pos > 0:
                        pct = min(99, int(pos * 100 / total_duration_ms[0]))
                        if pct > last_progress_pct[0]:
                            last_progress_pct[0] = pct
                            progress_callback(pct)

            decoder.stop()

            # Ajouter le dernier chunk partiel
            if current_chunk:
                chunk_peaks.append(max(current_chunk))

            if error_msg[0]:
                print(f"   QAudioDecoder erreur: {error_msg[0]}")
                # Meme en cas d'erreur, on peut avoir des donnees partielles
                if not chunk_peaks:
                    return None

            if not chunk_peaks:
                print("   QAudioDecoder: aucun sample decode")
                return None

            # Normaliser 0.0-1.0
            max_val = max(chunk_peaks) if chunk_peaks else 1
            if max_val > 0:
                waveform = [p / max_val for p in chunk_peaks]
            else:
                waveform = chunk_peaks

            if progress_callback:
                progress_callback(100)

            elapsed = time.time() - start_time
            print(f"   QAudioDecoder: {len(waveform)} points en {elapsed:.1f}s")
            return waveform

        except Exception as e:
            print(f"   QAudioDecoder exception: {e}")
            return None

    def _downsample_waveform(self, audio_data, max_samples):
        """Reduit les donnees audio en max_samples points normalises 0.0-1.0"""
        step = max(1, len(audio_data) // max_samples)
        waveform = []
        for i in range(0, len(audio_data), step):
            chunk = audio_data[i:i+step]
            if chunk:
                waveform.append(max(chunk))

        if waveform:
            max_val = max(waveform)
            if max_val > 0:
                waveform = [x / max_val for x in waveform]

        print(f"✅ Forme d'onde generee: {len(waveform)} points")
        self.waveform_data = waveform
        return waveform

    def get_clip_at_pos(self, x, y):
        """Trouve le clip sous la position de la souris"""
        if y < 10 or y > 50:
            return None

        for clip in self.clips:
            clip_x = 145 + int(clip.start_time * self.pixels_per_ms)
            clip_width = int(clip.duration * self.pixels_per_ms)
            if clip_x <= x <= clip_x + clip_width:
                return clip, clip_x, clip_width
        return None

    def find_free_position(self, start_time, duration):
        """Trouve une position libre sur la timeline (pas de collision)"""
        sorted_clips = sorted(self.clips, key=lambda c: c.start_time)

        for clip in sorted_clips:
            clip_end = clip.start_time + clip.duration
            new_end = start_time + duration

            if start_time < clip_end and new_end > clip.start_time:
                start_time = clip_end

        return start_time

    def mousePressEvent(self, event):
        """Gere clic souris pour drag/resize/fade/menu + CUT MODE"""
        x = event.position().x()
        y = event.position().y()

        # === MODE CUT ACTIVE ===
        if hasattr(self.parent_editor, 'cut_mode') and self.parent_editor.cut_mode:
            result = self.get_clip_at_pos(x, y)
            if result:
                clip, clip_x, clip_width = result
                click_time_in_clip = (x - clip_x) / self.pixels_per_ms
                self.cut_clip_at_position(clip, click_time_in_clip)
                self.parent_editor.cut_mode = False
                self.parent_editor.cut_btn.setChecked(False)
                self.parent_editor.setCursor(Qt.ArrowCursor)
                for track in self.parent_editor.tracks:
                    track.setCursor(Qt.ArrowCursor)
            return

        result = self.get_clip_at_pos(x, y)

        if result:
            clip, clip_x, clip_width = result
            modifiers = event.modifiers()

            if modifiers & Qt.ControlModifier:
                if clip in self.selected_clips:
                    self.selected_clips.remove(clip)
                else:
                    self.selected_clips.append(clip)
                self.update()
                return
            elif modifiers & Qt.ShiftModifier:
                if self.selected_clips:
                    last_selected = self.selected_clips[-1]
                    if last_selected in self.clips:
                        start_idx = self.clips.index(last_selected)
                        end_idx = self.clips.index(clip)
                        if start_idx > end_idx:
                            start_idx, end_idx = end_idx, start_idx
                        for i in range(start_idx, end_idx + 1):
                            if self.clips[i] not in self.selected_clips:
                                self.selected_clips.append(self.clips[i])
                else:
                    self.selected_clips = [clip]
                self.update()
                return
            else:
                # Clic simple - verifier si le clip est deja selectionne (multi-pistes)
                all_selected = self.get_all_selected_clips()
                if clip not in all_selected:
                    if hasattr(self.parent_editor, 'clear_all_selections'):
                        self.parent_editor.clear_all_selections()
                    self.selected_clips = [clip]

            # Calculer positions des fades
            fade_in_px = int(clip.fade_in_duration * self.pixels_per_ms) if clip.fade_in_duration > 0 else 0
            fade_out_px = int(clip.fade_out_duration * self.pixels_per_ms) if clip.fade_out_duration > 0 else 0

            if fade_in_px > 0 and x < clip_x + fade_in_px and y >= 10 and y <= 50:
                self.resizing_clip = clip
                self.resize_edge = 'fade_in'
                self.saved_positions = {clip: (clip.start_time, clip.duration)}
            elif fade_out_px > 0 and x > clip_x + clip_width - fade_out_px and y >= 10 and y <= 50:
                self.resizing_clip = clip
                self.resize_edge = 'fade_out'
                self.saved_positions = {clip: (clip.start_time, clip.duration)}
            elif x < clip_x + 5:
                self.resizing_clip = clip
                self.resize_edge = 'left'
                self.saved_positions = {clip: (clip.start_time, clip.duration)}
            elif x > clip_x + clip_width - 5:
                self.resizing_clip = clip
                self.resize_edge = 'right'
                self.saved_positions = {clip: (clip.start_time, clip.duration)}
            else:
                # Drag - sauvegarder positions de TOUS les clips selectionnes (multi-pistes)
                self.dragging_clip = clip
                self.drag_offset = x - clip_x

                # Sauvegarder les positions de depart de tous les clips selectionnes
                self.drag_start_positions = {}
                for track in self.parent_editor.tracks:
                    for sel_clip in track.selected_clips:
                        self.drag_start_positions[sel_clip] = sel_clip.start_time

                # Ajouter le clip actuel si pas deja selectionne
                if clip not in self.drag_start_positions:
                    self.drag_start_positions[clip] = clip.start_time

                # Sauvegarder pour undo
                if hasattr(self.parent_editor, 'save_state'):
                    self.parent_editor.save_state()

            # Clip trouve -> accepter l'event, ne PAS propager au parent (evite rubber band)
            event.accept()
            return

        # Zone vide -> laisser le parent gerer (rubber band selection)
        super().mousePressEvent(event)

    def get_all_selected_clips(self):
        """Retourne tous les clips selectionnes sur toutes les pistes"""
        all_clips = []
        if hasattr(self.parent_editor, 'tracks'):
            for track in self.parent_editor.tracks:
                all_clips.extend(track.selected_clips)
        return all_clips

    def mouseMoveEvent(self, event):
        """Gere drag et resize + ANTI-COLLISION + DRAG MULTI-CLIPS"""
        x = event.position().x()

        # Si mode cut actif
        if hasattr(self.parent_editor, 'cut_mode') and self.parent_editor.cut_mode:
            result = self.get_clip_at_pos(x, event.position().y())
            if result:
                self.setCursor(Qt.SplitHCursor)
            else:
                self.setCursor(Qt.ForbiddenCursor)
            return

        if self.dragging_clip:
            # Calculer le delta de deplacement
            new_x = max(145, x - self.drag_offset)
            new_start = (new_x - 145) / self.pixels_per_ms
            delta = new_start - self.drag_start_positions.get(self.dragging_clip, self.dragging_clip.start_time)

            # Deplacer TOUS les clips selectionnes sur TOUTES les pistes
            # Clamper le delta pour eviter de sauter par-dessus des clips
            clamped_delta = delta

            for track in self.parent_editor.tracks:
                for sel_clip in track.selected_clips:
                    if sel_clip not in self.drag_start_positions:
                        continue

                    original_start = self.drag_start_positions[sel_clip]

                    # Limiter pour ne pas aller sous 0
                    if original_start + clamped_delta < 0:
                        clamped_delta = -original_start

                    # Verifier collision avec les autres clips de cette piste
                    for other_clip in track.clips:
                        if other_clip in track.selected_clips:
                            continue
                        other_end = other_clip.start_time + other_clip.duration

                        sel_clip_end_orig = original_start + sel_clip.duration

                        if clamped_delta > 0:
                            # Drag vers la droite: bloquer avant le prochain clip
                            # Le clip bloqueur doit etre devant nous (son debut >= notre fin originale - marge)
                            if other_clip.start_time >= sel_clip_end_orig - 1:
                                max_delta = other_clip.start_time - sel_clip_end_orig
                                if max_delta < clamped_delta:
                                    clamped_delta = max(0, max_delta)
                        else:
                            # Drag vers la gauche: bloquer apres le clip precedent
                            # Le clip bloqueur doit etre derriere nous (sa fin <= notre debut original + marge)
                            if other_end <= original_start + 1:
                                max_delta = -(original_start - other_end)
                                if max_delta > clamped_delta:
                                    clamped_delta = min(0, max_delta)

            # Appliquer le deplacement avec le delta clampe
            if abs(clamped_delta) > 0.1:
                for track in self.parent_editor.tracks:
                    for sel_clip in track.selected_clips:
                        if sel_clip in self.drag_start_positions:
                            sel_clip.start_time = max(0, self.drag_start_positions[sel_clip] + clamped_delta)
                    track.update()

        elif self.resizing_clip:
            clip_x = 145 + int(self.resizing_clip.start_time * self.pixels_per_ms)

            if self.resize_edge == 'fade_in':
                new_fade = max(0, (x - clip_x) / self.pixels_per_ms)
                max_fade_in = self.resizing_clip.duration - self.resizing_clip.fade_out_duration
                self.resizing_clip.fade_in_duration = min(new_fade, max_fade_in)
            elif self.resize_edge == 'fade_out':
                clip_end = clip_x + int(self.resizing_clip.duration * self.pixels_per_ms)
                new_fade = max(0, (clip_end - x) / self.pixels_per_ms)
                max_fade_out = self.resizing_clip.duration - self.resizing_clip.fade_in_duration
                self.resizing_clip.fade_out_duration = min(new_fade, max_fade_out)
            elif self.resize_edge == 'left':
                new_start_ms = max(0, (x - 145) / self.pixels_per_ms)
                old_end_ms = self.resizing_clip.start_time + self.resizing_clip.duration

                for clip in self.clips:
                    if clip == self.resizing_clip:
                        continue
                    if clip.start_time < self.resizing_clip.start_time:
                        clip_end_ms = clip.start_time + clip.duration
                        if new_start_ms < clip_end_ms:
                            new_start_ms = clip_end_ms

                if new_start_ms < old_end_ms - 500:
                    self.resizing_clip.start_time = new_start_ms
                    self.resizing_clip.duration = old_end_ms - new_start_ms
            else:  # right
                new_duration_sec = (x - clip_x) / self.pixels_per_ms / 1000
                new_end = self.resizing_clip.start_time + new_duration_sec

                for clip in self.clips:
                    if clip == self.resizing_clip:
                        continue
                    if clip.start_time > self.resizing_clip.start_time:
                        if new_end > clip.start_time:
                            new_duration_sec = clip.start_time - self.resizing_clip.start_time
                            break

                self.resizing_clip.duration = max(500, new_duration_sec * 1000)

            self.update()

        else:
            result = self.get_clip_at_pos(x, event.position().y())
            if result:
                clip, clip_x, clip_width = result
                if x < clip_x + 5 or x > clip_x + clip_width - 5:
                    self.setCursor(Qt.SizeHorCursor)
                else:
                    self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Fin drag/resize"""
        self.dragging_clip = None
        self.drag_start_positions = {}
        self.resizing_clip = None
        self.resize_edge = None

        if not (hasattr(self.parent_editor, 'cut_mode') and self.parent_editor.cut_mode):
            self.setCursor(Qt.ArrowCursor)

        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Menu contextuel sur clip OU zone vide"""
        if hasattr(self.parent_editor, 'cut_mode') and self.parent_editor.cut_mode:
            return

        # Sauvegarder la position du clic pour "Couper ici"
        self.last_context_click_x = event.pos().x()

        result = self.get_clip_at_pos(event.pos().x(), event.pos().y())

        if result:
            clip, clip_x, _ = result
            # Calculer la position relative dans le clip
            click_pos_in_clip = (event.pos().x() - clip_x) / self.pixels_per_ms
            self.show_clip_menu(clip, event.globalPos(), click_pos_in_clip)
        else:
            self.show_empty_menu(event.pos(), event.globalPos())

        super().contextMenuEvent(event)

    def show_empty_menu(self, local_pos, global_pos):
        """Menu sur zone vide"""
        menu = QMenu(self)
        menu.setStyleSheet("""
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
        """)

        colors = [
            ("Rouge", QColor(255, 0, 0)),
            ("Vert", QColor(0, 255, 0)),
            ("Bleu", QColor(0, 0, 255)),
            ("Jaune", QColor(200, 200, 0)),
            ("Magenta", QColor(255, 0, 255)),
            ("Cyan", QColor(0, 255, 255)),
            ("Blanc", QColor(255, 255, 255)),
            ("Orange", QColor(255, 128, 0)),
        ]

        bicolors = [
            ("Rouge/Bleu", QColor(255, 0, 0), QColor(0, 0, 255)),
            ("Vert/Magenta", QColor(0, 255, 0), QColor(255, 0, 255)),
            ("Jaune/Cyan", QColor(200, 200, 0), QColor(0, 255, 255)),
            ("Rouge/Blanc", QColor(255, 0, 0), QColor(255, 255, 255)),
            ("Bleu/Blanc", QColor(0, 0, 255), QColor(255, 255, 255)),
        ]

        fill_gap_menu = menu.addMenu("🔧 Combler vide")

        for name, col in colors:
            action = fill_gap_menu.addAction(f"■ {name}")
            action.triggered.connect(lambda checked=False, c=col, p=local_pos: self.fill_gap_at_pos(c, p))

        fill_gap_menu.addSeparator()

        for name, col1, col2 in bicolors:
            action = fill_gap_menu.addAction(f"■■ {name}")
            action.triggered.connect(lambda checked=False, c1=col1, c2=col2, p=local_pos: self.fill_gap_bicolor_at_pos(c1, c2, p))

        menu.exec(global_pos)

    def fill_gap_at_pos(self, color, pos):
        """Comble le vide a la position cliquee"""
        drop_x = pos.x() - 145
        click_time = max(0, drop_x / self.pixels_per_ms)

        sorted_clips = sorted(self.clips, key=lambda c: c.start_time)

        gap_start = 0
        gap_end = self.total_duration

        for clip in sorted_clips:
            clip_end = clip.start_time + clip.duration

            if clip_end <= click_time:
                gap_start = clip_end
            elif clip.start_time >= click_time:
                gap_end = clip.start_time
                break

        gap_duration = gap_end - gap_start

        if gap_duration > 100:
            self.add_clip(gap_start, gap_duration, color, 100)
            if hasattr(self.parent_editor, 'save_state'):
                self.parent_editor.save_state()

    def fill_gap_bicolor_at_pos(self, color1, color2, pos):
        """Comble le vide avec un bicolore"""
        drop_x = pos.x() - 145
        click_time = max(0, drop_x / self.pixels_per_ms)

        sorted_clips = sorted(self.clips, key=lambda c: c.start_time)

        gap_start = 0
        gap_end = self.total_duration

        for clip in sorted_clips:
            clip_end = clip.start_time + clip.duration

            if clip_end <= click_time:
                gap_start = clip_end
            elif clip.start_time >= click_time:
                gap_end = clip.start_time
                break

        gap_duration = gap_end - gap_start

        if gap_duration > 100:
            clip = self.add_clip(gap_start, gap_duration, color1, 100)
            clip.color2 = color2
            self.update()
            if hasattr(self.parent_editor, 'save_state'):
                self.parent_editor.save_state()

    def show_clip_menu(self, clip, global_pos, click_pos_in_clip=None):
        """Affiche le menu contextuel d'un clip"""
        menu = QMenu(self)
        menu.setStyleSheet("""
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
        """)

        # === INTENSITE ===
        intensity_menu = menu.addMenu("📊 Intensité")
        for val in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            action = intensity_menu.addAction(f"{val}%")
            action.triggered.connect(lambda checked=False, v=val, cl=clip: self.set_clip_intensity(cl, v))
        intensity_menu.addSeparator()
        custom_action = intensity_menu.addAction("✏️ Personnalisé...")
        custom_action.triggered.connect(lambda: self.edit_clip_intensity(clip))

        # === COULEUR ===
        color_menu = menu.addMenu("🎨 Couleur")
        colors = [
            ("Rouge", QColor(255, 0, 0)),
            ("Vert", QColor(0, 255, 0)),
            ("Bleu", QColor(0, 0, 255)),
            ("Jaune", QColor(200, 200, 0)),
            ("Magenta", QColor(255, 0, 255)),
            ("Cyan", QColor(0, 255, 255)),
            ("Blanc", QColor(255, 255, 255)),
        ]
        for name, col in colors:
            pixmap = QPixmap(16, 16)
            pixmap.fill(col)
            icon = QIcon(pixmap)
            action = color_menu.addAction(icon, name)
            action.triggered.connect(lambda checked=False, c=col, cl=clip: self.set_clip_color(cl, c))

        # Bicolores
        color_menu.addSeparator()
        bicolors = [
            ("Rouge/Vert", QColor(255, 0, 0), QColor(0, 200, 0)),
            ("Rouge/Bleu", QColor(255, 0, 0), QColor(0, 0, 255)),
            ("Rouge/Orange", QColor(255, 0, 0), QColor(255, 128, 0)),
            ("Rouge/Rose", QColor(255, 0, 0), QColor(255, 105, 180)),
            ("Bleu/Cyan", QColor(0, 0, 255), QColor(0, 255, 255)),
            ("Vert/Jaune", QColor(0, 200, 0), QColor(255, 255, 0)),
            ("Bleu/Violet", QColor(0, 0, 255), QColor(128, 0, 255)),
            ("Orange/Jaune", QColor(255, 128, 0), QColor(255, 255, 0)),
            ("Cyan/Violet", QColor(0, 255, 255), QColor(128, 0, 255)),
        ]
        for name, col1, col2 in bicolors:
            pixmap = QPixmap(16, 16)
            p = QPainter(pixmap)
            p.fillRect(0, 0, 8, 16, col1)
            p.fillRect(8, 0, 8, 16, col2)
            p.end()
            icon = QIcon(pixmap)
            action = color_menu.addAction(icon, name)
            action.triggered.connect(lambda checked=False, c1=col1, c2=col2, cl=clip: self.set_clip_bicolor(cl, c1, c2))

        # === EFFETS ===
        menu.addSeparator()
        effects_menu = menu.addMenu("✨ Effets")
        no_effect = effects_menu.addAction("⭕ Aucun")
        no_effect.triggered.connect(lambda: self.set_clip_effect(clip, None))
        effects_menu.addSeparator()
        effect_emojis = {
            "Strobe": "⚡", "Flash": "💥", "Pulse": "💜",
            "Wave": "🌊", "Random": "🎲", "Rainbow": "🌈",
            "Sparkle": "✨", "Fire": "🔥",
        }
        for eff in ["Strobe", "Flash", "Pulse", "Wave", "Random", "Rainbow", "Sparkle", "Fire"]:
            emoji = effect_emojis.get(eff, "⚡")
            action = effects_menu.addAction(f"{emoji} {eff}")
            action.triggered.connect(lambda checked=False, e=eff, cl=clip: self.set_clip_effect(cl, e))

        effects_menu.addSeparator()
        speed_lbl = f"Lent" if clip.effect_speed < 33 else ("Rapide" if clip.effect_speed > 66 else "Moyen")
        speed_action = effects_menu.addAction(f"🎚 Vitesse : {clip.effect_speed}% ({speed_lbl})...")
        speed_action.triggered.connect(lambda: self.edit_clip_effect_speed(clip))

        # === FADES ===
        menu.addSeparator()
        fade_in_action = menu.addAction("🎬 Fade In...")
        fade_in_action.triggered.connect(lambda: self.add_clip_fade_in(clip))
        fade_out_action = menu.addAction("🎬 Fade Out...")
        fade_out_action.triggered.connect(lambda: self.add_clip_fade_out(clip))

        if clip.fade_in_duration > 0 or clip.fade_out_duration > 0:
            clear_fades = menu.addAction("❌ Supprimer fades")
            clear_fades.triggered.connect(lambda: self.clear_clip_fades(clip))

        # === COPIER VERS ===
        menu.addSeparator()
        if hasattr(self.parent_editor, 'tracks'):
            copy_menu = menu.addMenu("📋 Copier vers...")
            for track in self.parent_editor.tracks:
                if track != self:
                    action = copy_menu.addAction(track.name)
                    action.triggered.connect(lambda checked=False, cl=clip, t=track: self.copy_clip_to_track(cl, t))

        # === COUPER ICI ===
        menu.addSeparator()
        if click_pos_in_clip is not None and click_pos_in_clip > 200 and click_pos_in_clip < clip.duration - 200:
            cut_here_action = menu.addAction("✂️ Couper ici")
            cut_here_action.triggered.connect(lambda: self.cut_clip_at_position(clip, click_pos_in_clip))
        else:
            cut_action = menu.addAction("✂️ Couper en 2")
            cut_action.triggered.connect(lambda: self.cut_clip_in_two(clip))

        # === SUPPRIMER ===
        delete_action = menu.addAction("🗑️ Supprimer")
        delete_action.triggered.connect(lambda: self.delete_clip(clip))

        menu.exec(global_pos)

    def set_clip_intensity(self, clip, value):
        clip.intensity = value
        self.update()
        if hasattr(self.parent_editor, 'save_state'):
            self.parent_editor.save_state()

    def edit_clip_intensity(self, clip):
        """Edite intensite avec dialog style"""
        dialog = QDialog(self)
        dialog.setWindowTitle("💡 Intensité")
        dialog.setFixedSize(350, 200)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: white; }
            QPushButton {
                background: #cccccc;
                color: black;
                border: 1px solid #999999;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background: #00d4ff; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)

        value_label = QLabel(f"{clip.intensity}%")
        value_label.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(clip.intensity)
        slider.valueChanged.connect(lambda v: value_label.setText(f"{v}%"))
        layout.addWidget(slider)

        btn_layout = QHBoxLayout()
        cancel = QPushButton("❌ Annuler")
        cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel)
        ok = QPushButton("✅ OK")
        ok.clicked.connect(dialog.accept)
        ok.setStyleSheet("background: #00d4ff; color: black; font-weight: bold;")
        btn_layout.addWidget(ok)
        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.Accepted:
            clip.intensity = slider.value()
            self.update()
            if hasattr(self.parent_editor, 'save_state'):
                self.parent_editor.save_state()

    def set_clip_color(self, clip, color):
        clip.color = color
        clip.color2 = None
        self.update()
        if hasattr(self.parent_editor, 'save_state'):
            self.parent_editor.save_state()

    def set_clip_bicolor(self, clip, color1, color2):
        """Remplace la couleur du clip par une bicolore"""
        clip.color = color1
        clip.color2 = color2
        self.update()
        if hasattr(self.parent_editor, 'save_state'):
            self.parent_editor.save_state()

    def set_clip_effect(self, clip, effect):
        clip.effect = effect
        self.update()

    def edit_clip_effect_speed(self, clip):
        """Dialog pour regler la vitesse de l'effet (0=lent, 100=rapide)"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Vitesse de l'effet")
        dialog.setFixedSize(360, 210)
        dialog.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: white; border: none; }
            QPushButton {
                background: #cccccc; color: black;
                border: 1px solid #999; border-radius: 6px;
                padding: 10px 20px; font-weight: bold;
            }
            QPushButton:hover { background: #00d4ff; }
            QSlider::groove:horizontal { background: #3a3a3a; height: 8px; border-radius: 4px; }
            QSlider::handle:horizontal {
                background: #00d4ff; width: 18px; height: 18px;
                margin: -5px 0; border-radius: 9px;
            }
            QSlider::sub-page:horizontal { background: #00d4ff; border-radius: 4px; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 25, 30, 20)
        layout.setSpacing(12)

        value_label = QLabel(f"Vitesse : {clip.effect_speed}%")
        value_label.setStyleSheet("color: white; font-size: 26px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)

        lbl_row = QHBoxLayout()
        lbl_slow = QLabel("Lent")
        lbl_slow.setStyleSheet("color: #888; font-size: 11px;")
        lbl_fast = QLabel("Rapide")
        lbl_fast.setStyleSheet("color: #888; font-size: 11px;")
        lbl_row.addWidget(lbl_slow)
        lbl_row.addStretch()
        lbl_row.addWidget(lbl_fast)
        layout.addLayout(lbl_row)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(clip.effect_speed)
        slider.valueChanged.connect(lambda v: value_label.setText(f"Vitesse : {v}%"))
        layout.addWidget(slider)

        btn_layout = QHBoxLayout()
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel)
        ok = QPushButton("OK")
        ok.clicked.connect(dialog.accept)
        ok.setStyleSheet("background: #00d4ff; color: black; font-weight: bold; padding: 10px 20px; border-radius: 6px;")
        btn_layout.addWidget(ok)
        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.Accepted:
            clip.effect_speed = slider.value()
            self.update()
            if hasattr(self.parent_editor, 'save_state'):
                self.parent_editor.save_state()

    def delete_clip(self, clip):
        """Supprime le(s) clip(s)"""
        clips_to_delete = self.selected_clips if len(self.selected_clips) > 1 else [clip]

        for c in clips_to_delete:
            if c in self.clips:
                self.clips.remove(c)

        self.selected_clips.clear()
        self.update()

        # Sauvegarder APRES suppression
        if hasattr(self.parent_editor, 'save_state'):
            self.parent_editor.save_state()

    def cut_clip_in_two(self, clip):
        """Coupe un clip en deux parties egales"""
        if clip not in self.clips:
            return
        self.cut_clip_at_position(clip, clip.duration / 2)

    def cut_clip_at_position(self, clip, position_in_clip):
        """Coupe un clip a une position precise"""
        if clip not in self.clips:
            return

        min_duration = 200
        if position_in_clip < min_duration or position_in_clip > clip.duration - min_duration:
            print(f"⚠️ Position de coupe invalide: {position_in_clip:.0f}ms")
            return

        cut_point = clip.start_time + position_in_clip
        first_duration = position_in_clip
        second_duration = clip.duration - position_in_clip

        print(f"✂️ CUT: Clip {clip.start_time/1000:.2f}s → coupe a {cut_point/1000:.2f}s")

        clip.duration = first_duration

        new_clip = self.add_clip_direct(cut_point, second_duration, clip.color, clip.intensity)

        if clip.color2:
            new_clip.color2 = clip.color2
        new_clip.effect = clip.effect
        new_clip.effect_speed = clip.effect_speed
        new_clip.fade_out_duration = clip.fade_out_duration
        clip.fade_out_duration = 0

        self.update()
        print(f"   ✅ Clip coupe en 2 parties")

        # Sauvegarder APRES la coupe
        if hasattr(self.parent_editor, 'save_state'):
            self.parent_editor.save_state()

    def copy_clip_to_track(self, clip, target_track):
        """Copie le(s) clip(s) vers une autre piste"""
        clips_to_copy = self.selected_clips if len(self.selected_clips) > 1 else [clip]

        for source_clip in clips_to_copy:
            new_clip = target_track.add_clip(
                source_clip.start_time,
                source_clip.duration,
                source_clip.color,
                source_clip.intensity
            )

            if source_clip.color2:
                new_clip.color2 = source_clip.color2
            new_clip.fade_in_duration = source_clip.fade_in_duration
            new_clip.fade_out_duration = source_clip.fade_out_duration
            new_clip.effect = source_clip.effect
            new_clip.effect_speed = source_clip.effect_speed

        target_track.update()

    def add_clip_fade_in(self, clip):
        clip.fade_in_duration = 1000
        self.update()

    def add_clip_fade_out(self, clip):
        clip.fade_out_duration = 1000
        self.update()

    def clear_clip_fades(self, clip):
        clip.fade_in_duration = 0
        clip.fade_out_duration = 0
        self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Drop d'une couleur sur la piste"""
        color_data = event.mimeData().text()

        drop_x = event.position().x() - 145
        start_time = max(0, drop_x / self.pixels_per_ms)
        clip_duration = 5000

        start_time = self.find_free_position(start_time, clip_duration)

        if '#' in color_data and color_data.count('#') >= 2:
            parts = color_data.split('#')
            parts = [p for p in parts if p]

            if len(parts) >= 2:
                color1 = QColor('#' + parts[0])
                color2 = QColor('#' + parts[1])

                if color1.isValid() and color2.isValid():
                    clip = self.add_clip(start_time, clip_duration, color1, 100)
                    clip.color2 = color2
                    self.update()
        else:
            color = QColor(color_data)
            self.add_clip(start_time, 5000, color, 100)

        if hasattr(self.parent_editor, 'save_state'):
            self.parent_editor.save_state()

        event.acceptProposedAction()

    def add_clip(self, start_time, duration, color, intensity):
        """Ajoute un clip avec anti-collision"""
        free_start = self.find_free_position(start_time, duration)
        clip = LightClip(free_start, duration, color, intensity, self)
        self.clips.append(clip)
        self.update()
        return clip

    def add_clip_direct(self, start_time, duration, color, intensity):
        """Ajoute un clip SANS anti-collision"""
        clip = LightClip(start_time, duration, color, intensity, self)
        self.clips.append(clip)
        self.update()
        return clip

    def update_clips(self):
        """Met a jour la position/taille de tous les clips"""
        for clip in self.clips:
            x = 145 + int(clip.start_time * self.pixels_per_ms)
            width = int(clip.duration * self.pixels_per_ms)
            clip.x_pos = x
            clip.width_val = max(20, width)
        self.update()

    def update_zoom(self, pixels_per_ms):
        """Met a jour le zoom"""
        self.pixels_per_ms = pixels_per_ms
        total_width = 145 + int(self.total_duration * pixels_per_ms) + 50
        self.setMinimumWidth(total_width)
        self.update_clips()
        self.update()

    def set_zoom(self, pixels_per_ms):
        """Change le niveau de zoom"""
        self.pixels_per_ms = pixels_per_ms
        self.update_clips()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)

        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        painter.drawLine(0, 0, self.width(), 0)

        # === FORME D'ONDE STYLE VIRTUAL DJ PRO ===
        if self.waveform_data:
            timeline_width_px = int(self.total_duration * self.pixels_per_ms)
            pixels_per_sample = timeline_width_px / len(self.waveform_data) if self.waveform_data else 1
            y_center = self.height() // 2

            if self.name == "Audio":
                # Piste Audio - Waveform miroir courbes lisses bleu/cyan
                try:
                    painter.setOpacity(1.0)
                    painter.setRenderHint(QPainter.Antialiasing, True)
                    max_height = (self.height() // 2) - 4

                    # Sous-echantillonner pour les pixels visibles
                    visible_start = max(0, int((0 - 145) / pixels_per_sample))
                    visible_end = min(len(self.waveform_data), int((self.width() + 10 - 145) / pixels_per_sample) + 1)

                    if not hasattr(self, '_waveform_logged'):
                        self._waveform_logged = True
                        print(f"🎨 WAVEFORM PAINT: name={self.name}, height={self.height()}, width={self.width()}")
                        print(f"   y_center={y_center}, max_height={max_height}")
                        print(f"   pixels_per_sample={pixels_per_sample:.4f}, timeline_width_px={timeline_width_px}")
                        print(f"   visible_start={visible_start}, visible_end={visible_end}")
                        print(f"   waveform_data len={len(self.waveform_data)}, first5={self.waveform_data[:5]}")

                    # Construire les points
                    points_top = []
                    points_bot = []

                    for i in range(visible_start, visible_end):
                        x = 145 + i * pixels_per_sample
                        amp = self.waveform_data[i]

                        if amp > 0.7:
                            h = amp * max_height * 1.15
                        else:
                            h = amp * max_height
                        h = max(0.5, min(h, max_height))

                        points_top.append((x, y_center - h))
                        points_bot.append((x, y_center + h))

                    if len(points_top) >= 2:
                        # Sous-echantillonner pour perf
                        step = max(1, len(points_top) // 2000)
                        sampled_top = points_top[::step]
                        if sampled_top[-1] != points_top[-1]:
                            sampled_top.append(points_top[-1])
                        sampled_bot = points_bot[::step]
                        if sampled_bot[-1] != points_bot[-1]:
                            sampled_bot.append(points_bot[-1])

                        # Path superieur
                        path_top = QPainterPath()
                        path_top.moveTo(sampled_top[0][0], y_center)
                        for pt in sampled_top:
                            path_top.lineTo(pt[0], pt[1])
                        path_top.lineTo(sampled_top[-1][0], y_center)
                        path_top.closeSubpath()

                        # Path inferieur (miroir)
                        path_bot = QPainterPath()
                        path_bot.moveTo(sampled_bot[0][0], y_center)
                        for pt in sampled_bot:
                            path_bot.lineTo(pt[0], pt[1])
                        path_bot.lineTo(sampled_bot[-1][0], y_center)
                        path_bot.closeSubpath()

                        # Gradient vertical bleu/cyan
                        grad_top = QLinearGradient(0, y_center, 0, y_center - max_height)
                        grad_top.setColorAt(0, QColor("#77ddff"))
                        grad_top.setColorAt(0.25, QColor("#44bbee"))
                        grad_top.setColorAt(0.55, QColor("#2288bb"))
                        grad_top.setColorAt(0.8, QColor("#115577"))
                        grad_top.setColorAt(1, QColor("#082a44"))

                        grad_bot = QLinearGradient(0, y_center, 0, y_center + max_height)
                        grad_bot.setColorAt(0, QColor("#77ddff"))
                        grad_bot.setColorAt(0.25, QColor("#44bbee"))
                        grad_bot.setColorAt(0.55, QColor("#2288bb"))
                        grad_bot.setColorAt(0.8, QColor("#115577"))
                        grad_bot.setColorAt(1, QColor("#082a44"))

                        # Remplir
                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QBrush(grad_top))
                        painter.drawPath(path_top)
                        painter.setBrush(QBrush(grad_bot))
                        painter.drawPath(path_bot)

                        # Contour fin
                        painter.setBrush(Qt.NoBrush)
                        painter.setPen(QPen(QColor("#99eeff"), 0.8))
                        painter.setOpacity(0.5)
                        contour = QPainterPath()
                        contour.moveTo(sampled_top[0][0], sampled_top[0][1])
                        for pt in sampled_top[1:]:
                            contour.lineTo(pt[0], pt[1])
                        painter.drawPath(contour)
                        contour_bot = QPainterPath()
                        contour_bot.moveTo(sampled_bot[0][0], sampled_bot[0][1])
                        for pt in sampled_bot[1:]:
                            contour_bot.lineTo(pt[0], pt[1])
                        painter.drawPath(contour_bot)
                        painter.setOpacity(1.0)

                except Exception as e:
                    print(f"❌ ERREUR paintEvent Audio: {e}")
                    import traceback
                    traceback.print_exc()

            else:
                # Autres pistes: forme d'onde tres discrete
                painter.setOpacity(0.08)
                max_height = 15

                for i, amplitude in enumerate(self.waveform_data):
                    x = 145 + int(i * pixels_per_sample)

                    if x < 140 or x > self.width() + 10:
                        continue

                    height = int(amplitude * max_height)
                    painter.setPen(QPen(QColor("#00d4ff"), 1))
                    painter.drawLine(x, y_center - height, x, y_center + height)

                painter.setOpacity(1.0)

        # Grille temporelle
        painter.setPen(QPen(QColor("#2a2a2a"), 1, Qt.SolidLine))
        for sec in range(0, int(self.total_duration / 1000) + 1):
            x = 145 + int(sec * 1000 * self.pixels_per_ms)
            if x < self.width():
                painter.drawLine(x, 0, x, self.height())

        # === DESSINER LES CLIPS ===
        painter.setRenderHint(QPainter.Antialiasing)
        for clip in self.clips:
            x = 145 + int(clip.start_time * self.pixels_per_ms)
            width = int(clip.duration * self.pixels_per_ms)
            y = 10
            height = 40

            clip_rect = QRect(x, y, max(20, width), height)

            if clip.color2:
                path = QPainterPath()
                path.addRoundedRect(clip_rect.x(), clip_rect.y(), clip_rect.width(), clip_rect.height(), 4, 4)
                painter.setClipPath(path)

                mid = clip_rect.left() + clip_rect.width() // 2
                painter.fillRect(QRect(clip_rect.left(), clip_rect.top(), clip_rect.width() // 2, clip_rect.height()), clip.color)
                painter.fillRect(QRect(mid, clip_rect.top(), clip_rect.width() - clip_rect.width() // 2, clip_rect.height()), clip.color2)

                painter.setClipRect(self.rect())
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#2a2a2a"), 2))
                painter.drawRoundedRect(clip_rect, 4, 4)
            else:
                painter.fillRect(clip_rect, clip.color)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#2a2a2a"), 2))
                painter.drawRoundedRect(clip_rect, 4, 4)

            if width > 40:
                luminance = (clip.color.red() * 0.299 + clip.color.green() * 0.587 + clip.color.blue() * 0.114)
                painter.setPen(QColor(0, 0, 0) if luminance > 128 else QColor(255, 255, 255))

                font = painter.font()
                font.setBold(True)
                font.setPixelSize(14)
                painter.setFont(font)
                text = f"{clip.intensity}%"
                if clip.effect:
                    text += f" • {clip.effect}"
                painter.drawText(clip_rect, Qt.AlignCenter, text)

            # Fades - couleur adaptee selon luminance du clip
            fade_in_px = int(clip.fade_in_duration * self.pixels_per_ms) if clip.fade_in_duration > 0 else 0
            fade_out_px = int(clip.fade_out_duration * self.pixels_per_ms) if clip.fade_out_duration > 0 else 0

            clip_lum = clip.color.red() * 0.299 + clip.color.green() * 0.587 + clip.color.blue() * 0.114
            is_bright = clip_lum > 180
            fade_fill = QColor(0, 0, 0, 120) if is_bright else QColor(255, 255, 255, 100)
            fade_line = QColor(0, 0, 0) if is_bright else QColor(255, 255, 255)
            fade_handle = QColor(80, 80, 80) if is_bright else QColor(0, 0, 0)

            if fade_in_px > 5:
                painter.setBrush(fade_fill)
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(QPolygon([
                    QPoint(clip_rect.left(), clip_rect.top()),
                    QPoint(clip_rect.left() + fade_in_px, clip_rect.top()),
                    QPoint(clip_rect.left(), clip_rect.bottom())
                ]))
                painter.setPen(QPen(fade_line, 3))
                painter.drawLine(clip_rect.left() + fade_in_px, clip_rect.top(), clip_rect.left(), clip_rect.bottom())
                painter.setPen(QPen(fade_handle, 5))
                painter.drawLine(clip_rect.left() + fade_in_px, clip_rect.top() + 5, clip_rect.left() + fade_in_px, clip_rect.bottom() - 5)

            if fade_out_px > 5:
                painter.setBrush(fade_fill)
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(QPolygon([
                    QPoint(clip_rect.right() - fade_out_px, clip_rect.top()),
                    QPoint(clip_rect.right(), clip_rect.top()),
                    QPoint(clip_rect.right(), clip_rect.bottom())
                ]))
                painter.setPen(QPen(fade_line, 3))
                painter.drawLine(clip_rect.right() - fade_out_px, clip_rect.top(), clip_rect.right(), clip_rect.bottom())
                painter.setPen(QPen(fade_handle, 5))
                painter.drawLine(clip_rect.right() - fade_out_px, clip_rect.top() + 5, clip_rect.right() - fade_out_px, clip_rect.bottom() - 5)

            # Selection
            if clip in self.selected_clips:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#00d4ff"), 3))
                painter.drawRoundedRect(clip_rect, 6, 6)

        # Curseur de lecture
        if hasattr(self.parent_editor, 'playback_position'):
            cursor_x = 145 + int(self.parent_editor.playback_position * self.pixels_per_ms)
            if 145 <= cursor_x < self.width():
                painter.setPen(QPen(QColor("#ff0000"), 3))
                painter.drawLine(cursor_x, 0, cursor_x, self.height())

        painter.end()

    def get_clips_data(self):
        """Retourne les donnees des clips pour sauvegarde"""
        return [
            {
                'start': clip.start_time,
                'duration': clip.duration,
                'color': clip.color.name(),
                'color2': clip.color2.name() if clip.color2 else None,
                'intensity': clip.intensity,
                'fade_in': clip.fade_in_duration,
                'fade_out': clip.fade_out_duration,
                'effect': clip.effect,
                'effect_speed': clip.effect_speed,
                'track': self.name
            }
            for clip in self.clips
        ]
