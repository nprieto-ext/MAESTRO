import sys
import os
import json
import random
import socket
import struct
import wave
import array
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QLabel, QFrame, QPushButton, QToolButton,
    QFileDialog, QTableWidget, QTableWidgetItem, QAbstractItemView, 
    QSplitter, QSlider, QScrollArea, QStyle, QMenu, QWidgetAction, QMessageBox, QHeaderView, QComboBox, QDialog, QTabWidget
)
from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QPoint, QRect, QObject, Signal
from PySide6.QtGui import QColor, QPainter, QBrush, QIcon, QPixmap, QCloseEvent, QFont, QPen, QPolygon, QCursor, QPalette, QLinearGradient
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

# Import MIDI (optionnel - fonctionne sans pour utiliser le simulateur uniquement)
MIDI_AVAILABLE = False
midi_lib = None

# Essayer rtmidi en premier
try:
    import rtmidi
    MIDI_AVAILABLE = True
    midi_lib = "rtmidi"
    print("✅ Support MIDI activé (python-rtmidi) - AKAI physique disponible")
except ImportError:
    # Essayer rtmidi2 en alternative
    try:
        import rtmidi2 as rtmidi
        MIDI_AVAILABLE = True
        midi_lib = "rtmidi2"
        print("✅ Support MIDI activé (rtmidi2) - AKAI physique disponible")
    except ImportError:
        MIDI_AVAILABLE = False
        print("ℹ️  Mode SIMULATEUR uniquement (MIDI non disponible)")
        print("   Le logiciel fonctionne parfaitement avec le simulateur AKAI virtuel !")
        print("   Pour connecter un AKAI physique : py -m pip install rtmidi2")
        print()

APP_NAME = "Maestro.py"
VERSION = "2.5.0"  # Version actuelle

"""
SUPPORT AKAI APC mini PHYSIQUE:
Pour connecter un vrai AKAI APC mini:
- pip install python-rtmidi
L'interface visuelle servira de retour visuel de l'état du contrôleur physique
"""

# Mapping des couleurs RGB vers les vélocités AKAI APC mini
AKAI_COLOR_MAP = {
    # Blanc/Jaune (pas de vrai blanc sur AKAI)
    "white": 5,      # Jaune vif (le plus proche du blanc)
    # Rouge
    "red": 3,        # Rouge vif
    # Orange
    "orange": 9,     # Orange vif
    # Jaune
    "yellow": 13,    # Jaune-vert vif
    # Vert
    "green": 25,     # Vert lime vif
    # Cyan/Bleu
    "cyan": 37,      # Cyan
    "blue": 45,      # Bleu
    # Violet/Magenta
    "violet": 53,    # Violet vif
    "magenta": 49,   # Rose/Magenta vif
}

def rgb_to_akai_velocity(qcolor):
    """Convertit une QColor RGB en vélocité AKAI (approximation)"""
    r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()
    
    # Détection par couleur HTML (plus précis)
    hex_color = qcolor.name().lower()
    
    # Mapping exact des couleurs du simulateur
    color_map = {
        "#ffffff": 3,   # Blanc → Rouge vif (interverti avec ligne 2)
        "#ff0000": 5,   # Rouge → Jaune (interverti avec ligne 1)
        "#ff8800": 9,   # Orange → Orange vif (9)
        "#ffdd00": 13,  # Jaune → Jaune vif (13)
        "#00ff00": 21,  # Vert → Vert vif (21)
        "#00dddd": 37,  # Cyan → Cyan (37)
        "#0000ff": 45,  # Bleu → Bleu (45)
        "#ff00ff": 53,  # Magenta/Violet → Violet (53)
    }
    
    # Chercher la couleur exacte
    if hex_color in color_map:
        return color_map[hex_color]
    
    # Sinon, approximation par dominante
    # Blanc (toutes composantes élevées)
    if r > 200 and g > 200 and b > 200:
        return 5  # Jaune vif (proche du blanc)
    
    # Rouge dominant
    if r > 150 and g < 150 and b < 150:
        return 3  # Rouge pur
    
    # Orange (rouge + vert moyen)
    if r > 200 and g > 100 and g < 200 and b < 100:
        return 9  # Orange
    
    # Jaune (rouge + vert)
    if r > 200 and g > 200 and b < 100:
        return 13  # Jaune
    
    # Vert dominant
    if g > 150 and r < 150 and b < 150:
        return 21  # Vert
    
    # Cyan (vert + bleu)
    if g > 150 and b > 150 and r < 100:
        return 37  # Cyan
    
    # Bleu dominant
    if b > 150 and r < 150 and g < 150:
        return 45  # Bleu
    
    # Magenta (rouge + bleu)
    if r > 150 and b > 150 and g < 100:
        return 53  # Violet/Magenta
    
    # Par défaut
    return 5

# --- MIDI HANDLER ---

class MIDIHandler(QObject):
    """Gestionnaire MIDI pour l'AKAI APC mini"""
    fader_changed = Signal(int, int)  # (fader_index, value)
    pad_pressed = Signal(int, int)    # (row, col)
    
    def __init__(self):
        super().__init__()
        self.midi_in = None
        self.midi_out = None
        self.running = False
        self.connection_check_timer = None
        self.owner_window = None  # Référence à la MainWindow
        
        if MIDI_AVAILABLE:
            self.connect_akai()
            if self.midi_in:
                # Timer pour lire les messages MIDI
                self.midi_timer = QTimer()
                self.midi_timer.timeout.connect(self.poll_midi)
                self.midi_timer.start(10)  # Poll toutes les 10ms
            
            # Timer pour vérifier la connexion toutes les 2 secondes
            self.connection_check_timer = QTimer()
            self.connection_check_timer.timeout.connect(self.check_connection)
            self.connection_check_timer.start(2000)  # Toutes les 2 secondes
    
    def check_connection(self):
        """Vérifie si l'AKAI est toujours connecté (DÉSACTIVÉ pour éviter spam console)"""
        return  # Désactivé - l'utilisateur peut reconnecter manuellement via le menu
    
    def connect_akai(self):
        """Connexion à l'AKAI APC mini"""
        try:
            # Fermer les anciennes connexions si elles existent
            if self.midi_in:
                try:
                    self.midi_in.close_port()
                except:
                    pass
            if self.midi_out:
                try:
                    self.midi_out.close_port()
                except:
                    pass
            
            # Créer les objets MIDI
            self.midi_in = rtmidi.MidiIn()
            self.midi_out = rtmidi.MidiOut()
            
            # Lister les ports disponibles
            in_ports = self.midi_in.get_ports()
            out_ports = self.midi_out.get_ports()
            
            # Chercher l'AKAI APC mini
            akai_in_idx = None
            akai_out_idx = None
            
            for idx, name in enumerate(in_ports):
                if 'APC' in name.upper() or 'MINI' in name.upper():
                    akai_in_idx = idx
                    break
            
            for idx, name in enumerate(out_ports):
                if 'APC' in name.upper() or 'MINI' in name.upper():
                    akai_out_idx = idx
                    break
            
            if akai_in_idx is not None:
                self.midi_in.open_port(akai_in_idx)
                print(f"✅ AKAI connecté (input): {in_ports[akai_in_idx]}")
            else:
                print("⚠️  AKAI non détecté (input)")
                self.midi_in = None
            
            if akai_out_idx is not None:
                self.midi_out.open_port(akai_out_idx)
                print(f"✅ AKAI connecté (output): {out_ports[akai_out_idx]}")
                self.initialize_leds()
            else:
                print("⚠️  AKAI non détecté (output)")
                self.midi_out = None
                
        except Exception as e:
            print(f"❌ Erreur connexion AKAI: {e}")
            self.midi_in = None
            self.midi_out = None
    
    def poll_midi(self):
        """Lit les messages MIDI en attente"""
        if not self.midi_in:
            return
        
        try:
            message = self.midi_in.get_message()
            if message:
                self.handle_midi_message(message[0])
        except Exception as e:
            print(f"Erreur lecture MIDI: {e}")
    
    def handle_midi_message(self, message):
        """Traite les messages MIDI de l'AKAI"""
        try:
            if len(message) < 2:
                return
            
            status = message[0]
            data1 = message[1]
            data2 = message[2] if len(message) > 2 else 0
            
            # Mode debug: afficher tous les messages
            if hasattr(self, 'debug_mode') and self.debug_mode:
                msg_type = "???"
                if status == 0xB0:
                    msg_type = "Control Change (Fader)"
                elif status == 0x90:
                    msg_type = "Note On (Pad/Bouton)"
                elif status == 0x80:
                    msg_type = "Note Off"
                
                print(f"🔍 MIDI DEBUG: Type={msg_type}, Status={hex(status)}, Data1={data1}, Data2={data2}")
            
            # Control Change (faders)
            if status == 0xB0:  # CC sur canal 1
                # Faders: CC 48-56 (colonnes 0-8)
                if 48 <= data1 <= 56:
                    fader_idx = data1 - 48
                    self.fader_changed.emit(fader_idx, data2)
            
            # Note On (pads et boutons)
            elif status == 0x90 and data2 > 0:  # Note On avec vélocité > 0
                note = data1
                
                if hasattr(self, 'debug_mode') and self.debug_mode:
                    print(f"   → Analyse note {note}:")
                
                # Carrés rouges de droite (colonne 8 - EFFETS): Notes 112-119
                if 112 <= note <= 119:
                    row = note - 112
                    col = 8
                    if hasattr(self, 'debug_mode') and self.debug_mode:
                        print(f"   ✅ Carré rouge EFFET {row+1} (note {note}) détecté")
                    self.pad_pressed.emit(row, col)
                
                # Carrés du bas (au-dessus des faders - MUTE): Notes 100-107
                # Note 100 = carré au-dessus du fader 1 (index 0)
                # Note 101 = carré au-dessus du fader 2 (index 1)
                # etc.
                elif 100 <= note <= 107:
                    # Mapping direct: note 100 = fader 1 (index 0)
                    fader_idx = note - 100
                    if hasattr(self, 'debug_mode') and self.debug_mode:
                        print(f"   ✅ Carré MUTE fader {fader_idx+1} (note {note}) détecté")
                    # Émettre un signal de mute
                    if hasattr(self, 'owner_window'):
                        self.owner_window.toggle_fader_mute_from_midi(fader_idx)
                
                # Bouton 9 (note 122 - BLACKOUT)
                elif note == 122:
                    if hasattr(self, 'debug_mode') and self.debug_mode:
                        print(f"   ✅ Bouton BLACKOUT (note {note}) détecté")
                    if hasattr(self, 'owner_window'):
                        self.owner_window.toggle_blackout_from_midi()
                
                # Pads de la grille 8x8: Notes 0-63
                elif 0 <= note <= 63:
                    # L'AKAI a les lignes inversées
                    row = 7 - (note // 8)
                    col = note % 8
                    
                    if hasattr(self, 'debug_mode') and self.debug_mode:
                        print(f"   ✅ Pad grille L{row} C{col} (note {note}) détecté")
                    
                    self.pad_pressed.emit(row, col)
                
                else:
                    if hasattr(self, 'debug_mode') and self.debug_mode:
                        print(f"   ⚠️  Note {note} non mappée")
        
        except Exception as e:
            print(f"Erreur traitement MIDI: {e}")
    
    def initialize_leds(self):
        """Initialise les LEDs de l'AKAI"""
        if not self.midi_out:
            return
        
        try:
            # Éteindre tous les pads
            for note in range(64):
                self.midi_out.send_message([0x90, note, 0])  # Note Off
        except Exception as e:
            print(f"Erreur init LEDs: {e}")
    
    def set_pad_led(self, row, col, color_velocity, brightness_percent=100):
        """
        Allume un pad avec une couleur
        color_velocity: vélocité AKAI (couleur)
        brightness_percent: 20 (dim) ou 100 (full)
        """
        if not self.midi_out:
            return
        
        try:
            # IMPORTANT: Sur l'AKAI APC mini mk2:
            # - Pads 8x8 RGB: Canal contrôle la luminosité (0x90=20%, 0x96=100%)
            # - Carrés rouges monochromes: Toujours canal 1 (0x90) avec vélocité 0/1/3
            
            # Colonne 8 = carrés rouges de droite (EFFETS - notes 112-119)
            # Ce sont des LEDs MONOCHROMES ROUGES
            if col == 8:
                note = 112 + row
                velocity = 3 if color_velocity > 0 else 0
                # TOUJOURS canal 1 pour les carrés rouges monochromes
                self.midi_out.send_message([0x90, note, velocity])
            else:
                # Grille 8x8 normale RGB (notes 0-63)
                # Le canal MIDI contrôle la luminosité pour les pads RGB
                if brightness_percent >= 80:
                    midi_channel = 0x96  # Canal 7 = 100% luminosité
                else:
                    midi_channel = 0x90  # Canal 1 = 10-20% luminosité
                
                # Inverser la ligne pour correspondre à l'AKAI physique
                physical_row = 7 - row
                note = physical_row * 8 + col
                self.midi_out.send_message([midi_channel, note, color_velocity])
        except Exception as e:
            print(f"Erreur set LED: {e}")
    
    def close(self):
        """Ferme les ports MIDI"""
        if hasattr(self, 'midi_timer'):
            self.midi_timer.stop()
        if hasattr(self, 'connection_check_timer') and self.connection_check_timer:
            self.connection_check_timer.stop()
        if self.midi_in:
            try:
                self.midi_in.close_port()
            except:
                pass
        if self.midi_out:
            try:
                self.midi_out.close_port()
            except:
                pass

def fmt_time(ms):
    if ms <= 0: return "00:00"
    s = ms // 1000
    return f"{s//60:02d}:{s%60:02d}"

def media_icon(path):
    ext = Path(path).suffix.lower()
    if ext in [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".aiff"]: return "🎵"
    if ext in [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"]: return "🎬"
    if ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".tiff"]: return "🖼"
    return "📄"

def create_icon(icon_type, color="#ffffff"):
    """Crée des icônes élégantes type console pro"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    if icon_type == "play":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        points = [QPoint(18, 12), QPoint(18, 52), QPoint(52, 32)]
        painter.drawPolygon(QPolygon(points))
    elif icon_type == "pause":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(18, 12, 10, 40, 2, 2)
        painter.drawRoundedRect(36, 12, 10, 40, 2, 2)
    elif icon_type == "prev":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(16, 18, 4, 28, 2, 2)
        points = [QPoint(48, 18), QPoint(48, 46), QPoint(22, 32)]
        painter.drawPolygon(QPolygon(points))
    elif icon_type == "next":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(44, 18, 4, 28, 2, 2)
        points = [QPoint(16, 18), QPoint(16, 46), QPoint(42, 32)]
        painter.drawPolygon(QPolygon(points))
    
    painter.end()
    return QIcon(pixmap)

# --- LOGIQUE ---

class Projector:
    def __init__(self, group):
        self.group = group
        self.level = 0
        self.base_color = QColor("white")
        self.color = QColor("black")
        self.dmx_mode = "Manuel"
        self.muted = False

# --- ART-NET / DMX ---

class ArtNetDMX:
    """Gestion de l'envoi DMX via Art-Net vers le Node 2"""
    def __init__(self):
        self.target_ip = "2.0.0.15"  # IP du Node 2 selon documentation Electroconcept
        self.target_port = 6454  # Port Art-Net standard
        self.universe = 0  # Univers 0 par défaut
        self.sequence = 0
        self.dmx_data = [0] * 512  # 512 canaux DMX
        self.socket = None
        self.connected = False
        
        # Mapping des projecteurs vers les canaux DMX
        # Format: {"face": [1, 2, 3, 4, 5], "douche1": [11, 12, 13, 14, 15], ...}
        self.projector_channels = {}
        
        # Modes des projecteurs (5CH, 4CH, 3CH)
        self.projector_modes = {}
        
    def connect(self):
        """Initialise la connexion UDP Art-Net"""
        try:
            if self.socket:
                self.socket.close()
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.connected = True
            return True
        except Exception as e:
            print(f"❌ Erreur connexion Art-Net: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Ferme la connexion"""
        if self.socket:
            self.socket.close()
            self.socket = None
        self.connected = False
    
    def set_channel(self, channel, value):
        """Définit la valeur d'un canal DMX (1-512)"""
        if 1 <= channel <= 512:
            self.dmx_data[channel - 1] = max(0, min(255, value))
    
    def set_rgb(self, start_channel, r, g, b):
        """Définit RGB sur 3 canaux consécutifs"""
        self.set_channel(start_channel, r)
        self.set_channel(start_channel + 1, g)
        self.set_channel(start_channel + 2, b)
    
    def send_dmx(self):
        """Envoie les données DMX via Art-Net"""
        if not self.connected or not self.socket:
            return False
        
        try:
            # En-tête Art-Net
            packet = bytearray()
            packet.extend(b'Art-Net\x00')  # ID (8 bytes)
            packet.extend(struct.pack('<H', 0x5000))  # OpCode ArtDMX (little-endian)
            packet.extend(struct.pack('>H', 14))  # Protocol version (big-endian)
            packet.append(self.sequence)  # Sequence
            packet.append(0)  # Physical
            packet.extend(struct.pack('<H', self.universe))  # Universe (little-endian)
            packet.extend(struct.pack('>H', 512))  # Length (big-endian)
            packet.extend(self.dmx_data)  # DMX data (512 bytes)
            
            self.socket.sendto(packet, (self.target_ip, self.target_port))
            
            # Incrémenter la séquence
            self.sequence = (self.sequence + 1) % 256
            return True
        except Exception as e:
            print(f"❌ Erreur envoi DMX: {e}")
            return False
    
    def update_from_projectors(self, projectors, effect_speed=0):
        """Met à jour les canaux DMX depuis la liste des projecteurs en utilisant le patch"""
        for i, proj in enumerate(projectors):
            # Créer la clé unique du projecteur
            proj_key = f"{proj.group}_{i}"
            
            # Vérifier si ce projecteur est patché
            if proj_key not in self.projector_channels:
                continue  # Projecteur non patché, on passe
            
            channels = self.projector_channels[proj_key]
            
            # Si le projecteur est muté, envoyer des 0
            if hasattr(proj, 'muted') and proj.muted:
                self.set_channel(channels[0], 0)  # Rouge
                self.set_channel(channels[1], 0)  # Vert
                self.set_channel(channels[2], 0)  # Bleu
                if len(channels) >= 4:
                    self.set_channel(channels[3], 0)  # Dimmer
                if len(channels) >= 5:
                    self.set_channel(channels[4], 0)  # Strobe
                continue
            
            # Récupérer RGB depuis proj.color
            r = proj.color.red() if hasattr(proj, 'color') else 0
            g = proj.color.green() if hasattr(proj, 'color') else 0
            b = proj.color.blue() if hasattr(proj, 'color') else 0
            
            # Dimmer : convertir de 0-100 vers 0-255
            level = proj.level if hasattr(proj, 'level') else 0
            dimmer = int((level / 100.0) * 255)
            
            # Vérifier si on a un dimmer virtuel (canal = -1)
            has_virtual_dimmer = len(channels) >= 4 and channels[3] == -1
            
            # Si dimmer virtuel, appliquer le dimmer directement sur RGB
            if has_virtual_dimmer:
                # Appliquer le dimmer virtuel sur les couleurs RGB
                dimmer_factor = level / 100.0
                r = int(r * dimmer_factor)
                g = int(g * dimmer_factor)
                b = int(b * dimmer_factor)
            
            # Vérifier si on a un strobe virtuel (canal = -1)
            has_virtual_strobe = len(channels) >= 5 and channels[4] == -1
            
            # Si strobe virtuel ET effet strobe actif, créer un strobe logiciel
            if has_virtual_strobe and hasattr(proj, 'dmx_mode') and proj.dmx_mode == "Strobe":
                # Strobe virtuel : alterner entre RGB et noir
                import time
                # Utiliser le temps pour créer un effet clignotant
                if int(time.time() * 10) % 2 == 0:  # Clignote 5 fois par seconde
                    r, g, b = 0, 0, 0  # Noir
            
            # DEBUG : Afficher les valeurs pour les premiers projecteurs
            if i < 4 and (r > 0 or g > 0 or b > 0 or dimmer > 0):
                virtual_info = ""
                if has_virtual_dimmer:
                    virtual_info += " [Dim virtuel]"
                if has_virtual_strobe:
                    virtual_info += " [Strobe virtuel]"
                print(f"DEBUG DMX [{proj_key}]: Ch{channels[0]}={r}, Ch{channels[1]}={g}, Ch{channels[2]}={b}{virtual_info}")
            
            # Envoyer aux canaux patchés
            self.set_channel(channels[0], r)      # Rouge
            self.set_channel(channels[1], g)      # Vert
            self.set_channel(channels[2], b)      # Bleu
            
            # Canal Dimmer
            if len(channels) >= 4:
                if channels[3] != -1:
                    # Dimmer hardware
                    self.set_channel(channels[3], dimmer)
                else:
                    # Dimmer virtuel : forcer canal 4 à zéro
                    dmx_addr = (i * 10) + 1
                    self.set_channel(dmx_addr + 3, 0)  # Canal 4 = 0
            
            # Canal Strobe
            if len(channels) >= 5:
                if channels[4] != -1:
                    # Strobe hardware
                    strobe_value = 0
                    if hasattr(proj, 'dmx_mode') and proj.dmx_mode == "Strobe":
                        if effect_speed > 0:
                            strobe_value = int(16 + (effect_speed / 100.0) * (250 - 16))
                        else:
                            strobe_value = 100
                    self.set_channel(channels[4], strobe_value)
                else:
                    # Strobe virtuel : forcer canal 5 à zéro
                    dmx_addr = (i * 10) + 1
                    self.set_channel(dmx_addr + 4, 0)  # Canal 5 = 0
            
            # En mode 6CH, forcer aussi canal 6 à zéro
            mode = self.projector_modes.get(proj_key, "5CH")
            if mode == "6CH":
                dmx_addr = (i * 10) + 1
                self.set_channel(dmx_addr + 5, 0)  # Canal 6 = 0

# --- AUDIO AI ---

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

# --- UI COMPONENTS ---

class DualColorButton(QPushButton):
    """Bouton avec deux couleurs en diagonale"""
    def __init__(self, color1, color2):
        super().__init__()
        self.color1 = color1
        self.color2 = color2
        self.setFixedSize(28, 28)
        self.active = False
        self.brightness = 0.3  # 30% par défaut
        
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

class EffectButton(QPushButton):
    """Bouton d'effet carré rouge avec menu d'effets"""
    def __init__(self, index):
        super().__init__()
        self.index = index
        self.setFixedSize(16, 16)  # Réduit de 26 à 16
        self.active = False
        self.current_effect = None  # Effet actuel
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_effects_menu)
        self.update_style()
    
    def show_effects_menu(self, pos):
        """Affiche le menu des effets avec prévisualisation"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                border: 1px solid #3a3a3a;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 15px;
                border-radius: 4px;
                color: white;
            }
            QMenu::item:selected {
                background: #3a3a3a;
            }
        """)
        
        # Effets disponibles avec emoji + prévisualisation couleur
        effects = [
            ("⭕ Aucun", None, "#2a2a2a"),
            ("⚡ Strobe", "Strobe", "#ffffff"),
            ("💥 Flash", "Flash", "#ffff00"),
            ("💫 Pulse", "Pulse", "#ff00ff"),
            ("🌊 Vague", "Wave", "#00ffff"),
            ("🎲 Random", "Random", "#ff8800"),
            ("🌀 Rotation", "Rotate", "#00ff00"),
            ("✨ Scintillement", "Sparkle", "#ffccff"),
            ("🔥 Feu", "Fire", "#ff4400"),
        ]
        
        for name, effect, color in effects:
            action = QWidgetAction(menu)
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(5, 2, 5, 2)
            
            # Carré de couleur prévisualisation
            preview = QLabel()
            preview.setFixedSize(20, 20)
            preview.setStyleSheet(f"background: {color}; border-radius: 3px; border: 1px solid #555;")
            layout.addWidget(preview)
            
            # Nom effet
            label = QLabel(name)
            label.setStyleSheet("color: white; font-size: 13px;")
            layout.addWidget(label)
            layout.addStretch()
            
            # Marque si c'est l'effet actuel
            if effect == self.current_effect:
                check = QLabel("✓")
                check.setStyleSheet("color: #00ff00; font-weight: bold;")
                layout.addWidget(check)
            
            action.setDefaultWidget(widget)
            action.triggered.connect(lambda checked=False, e=effect: self.set_effect(e))
            menu.addAction(action)
        
        menu.exec(self.mapToGlobal(pos))
    
    def set_effect(self, effect):
        """Définit l'effet actuel"""
        self.current_effect = effect
        if effect:
            self.active = True
        else:
            self.active = False
        self.update_style()
        print(f"🎭 Effet {self.index}: {effect}")
        
    def update_style(self):
        if self.active:
            self.setStyleSheet("""
                QPushButton {
                    background: #ff3333;
                    border: 2px solid #ffffff;
                    border-radius: 3px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: #661111;
                    border: 1px solid #441111;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background: #881111;
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
    def __init__(self, index, callback, vertical=True):
        super().__init__()
        self.index = index
        self.callback = callback
        self.value = 0
        self.vertical = vertical
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

    def mousePressEvent(self, e): self.update_value(e.position())
    def mouseMoveEvent(self, e): self.update_value(e.position())

    def update_value(self, pos):
        limit = self.height() - (45 if self.vertical else 25)
        offset = 30 if self.vertical else 15
        y = max(10, min(self.height() - 10, int(pos.y())))
        self.value = int((self.height() - offset - y) / limit * 100)
        self.value = max(0, min(100, self.value))
        self.callback(self.index, self.value)
        self.update()


class PlanDeFeu(QFrame):
    def __init__(self, projectors, main_window=None):
        super().__init__()
        self.projectors = projectors
        self.main_window = main_window
        self.lamps = []
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(10, 30, 10, 10)
        
        title = QLabel("💡 Plan de Feu")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(title)
        
        # Espacement après le titre
        layout.addSpacing(15)
        
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(9, 1)  # Colonnes stretch pour centrage
        
        # 6 projecteurs CONTRE (ligne 0) - Centrés
        contre_positions = [2, 3, 4, 5, 6, 7]  # Positions centrées
        for i, col in enumerate(contre_positions):
            l = QLabel()
            l.setFixedSize(24, 24)
            l.setStyleSheet("background:#0a0a0a; border-radius:12px; border: 2px solid #2a2a2a;")
            l.setContextMenuPolicy(Qt.CustomContextMenu)
            l.customContextMenuRequested.connect(lambda pos, lamp=l, group="contre", idx=i: self.show_color_menu(pos, lamp, group, idx))
            grid.addWidget(l, 0, col, alignment=Qt.AlignCenter)
            self.lamps.append(("contre", i, l))
        
        # Espacement après CONTRE
        grid.setRowMinimumHeight(1, 25)
        
        # 2 projecteurs LAT (côtés, ligne 2)
        lat_left = QLabel()
        lat_left.setFixedSize(24, 24)
        lat_left.setStyleSheet("background:#0a0a0a; border-radius:12px; border: 2px solid #2a2a2a;")
        lat_left.setContextMenuPolicy(Qt.CustomContextMenu)
        lat_left.customContextMenuRequested.connect(lambda pos, lamp=lat_left, group="lat", idx=0: self.show_color_menu(pos, lamp, group, idx))
        grid.addWidget(lat_left, 2, 1)
        self.lamps.append(("lat", 0, lat_left))
        
        lat_right = QLabel()
        lat_right.setFixedSize(24, 24)
        lat_right.setStyleSheet("background:#0a0a0a; border-radius:12px; border: 2px solid #2a2a2a;")
        lat_right.setContextMenuPolicy(Qt.CustomContextMenu)
        lat_right.customContextMenuRequested.connect(lambda pos, lamp=lat_right, group="lat", idx=1: self.show_color_menu(pos, lamp, group, idx))
        grid.addWidget(lat_right, 2, 8)
        self.lamps.append(("lat", 1, lat_right))
        
        # Espacement avant les douches
        grid.setRowMinimumHeight(3, 25)
        
        # 3 DOUCHES (ligne 4) - Bien centrées
        douche_positions = [3, 5, 7]  # Positions centrées et espacées
        for i, col in enumerate(douche_positions):
            l = QLabel()
            l.setFixedSize(24, 24)
            l.setStyleSheet("background:#0a0a0a; border-radius:12px; border: 2px solid #2a2a2a;")
            l.setContextMenuPolicy(Qt.CustomContextMenu)
            l.customContextMenuRequested.connect(lambda pos, lamp=l, group=f"douche{i+1}", idx=0: self.show_color_menu(pos, lamp, group, idx))
            grid.addWidget(l, 4, col, alignment=Qt.AlignCenter)
            self.lamps.append((f"douche{i+1}", 0, l))
        
        # Espacement avant les FACE
        grid.setRowMinimumHeight(5, 25)
        
        # 4 FACE (ligne 6) avec espacement identique (équidistants)
        face_positions = [2, 4, 6, 8]  # Espacés de 2 colonnes
        for i, col in enumerate(face_positions):
            l = QLabel()
            l.setFixedSize(24, 24)
            l.setStyleSheet("background:#0a0a0a; border-radius:12px; border: 2px solid #2a2a2a;")
            l.setContextMenuPolicy(Qt.CustomContextMenu)
            l.customContextMenuRequested.connect(lambda pos, lamp=l, group="face", idx=i: self.show_color_menu(pos, lamp, group, idx))
            grid.addWidget(l, 6, col, alignment=Qt.AlignCenter)
            self.lamps.append(("face", i, l))
        
        layout.addLayout(grid)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60)
    
    def show_color_menu(self, pos, lamp, group, idx):
        """Affiche le menu contextuel avec nom, adresse DMX, dimmer et couleur"""
        # Trouver le projecteur
        projs = [p for p in self.projectors if p.group == group]
        if idx >= len(projs):
            return
        
        proj = projs[idx]
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                border: 1px solid #2a2a2a;
                padding: 8px;
            }
            QMenu::item {
                padding: 10px 20px;
                border-radius: 4px;
                color: #ddd;
                font-size: 13px;
            }
            QMenu::item:selected {
                background: #2a4a5a;
            }
            QMenu::separator {
                height: 2px;
                background: #2a2a2a;
                margin: 5px 0;
            }
        """)
        
        # === INFOS PROJECTEUR ===
        # Construire le nom depuis group + idx
        proj_name = f"{group.capitalize()} {idx + 1}" if group != "face" else "Face"
        
        # Récupérer adresse DMX si disponible
        dmx_info = ""
        if self.main_window and hasattr(self.main_window, 'artnet'):
            key = f"{group}{idx}" if group != "face" else "face"
            if key in self.main_window.artnet.projector_channels:
                channels = self.main_window.artnet.projector_channels[key]
                if channels:
                    start = min(channels)
                    end = max(channels)
                    dmx_info = f"\n🔌 DMX {start}-{end}"
        
        info_label = QLabel(f"📡 {proj_name}{dmx_info}")
        info_label.setStyleSheet("color: #00d4ff; font-weight: bold; padding: 5px;")
        info_label.setAlignment(Qt.AlignCenter)
        info_action = QWidgetAction(menu)
        info_action.setDefaultWidget(info_label)
        menu.addAction(info_action)
        
        menu.addSeparator()
        
        # === DIMMER ===
        dimmer_menu = menu.addMenu("💡 Dimmer")
        current_dimmer = proj.level
        for val in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            action = dimmer_menu.addAction(f"{'✓ ' if abs(current_dimmer - val) < 5 else '  '}{val}%")
            action.triggered.connect(lambda checked=False, v=val, p=proj, m=menu: (self.set_projector_dimmer(p, v), m.show()))
        
        menu.addSeparator()
        
        # === COULEURS ===
        colors = [
            ("Blanc", QColor("white")),
            ("Rouge", QColor("#ff0000")),
            ("Orange", QColor("#ff8800")),
            ("Jaune", QColor("#ffdd00")),
            ("Vert", QColor("#00ff00")),
            ("Cyan", QColor("#00dddd")),
            ("Bleu", QColor("#0000ff")),
            ("Violet", QColor("#ff00ff")),
        ]
        
        current_color = proj.base_color
        
        for name, color in colors:
            # Créer un widget personnalisé pour chaque couleur
            action = QWidgetAction(menu)
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(5, 2, 5, 2)
            
            # Checkmark si couleur active
            is_active = abs(current_color.red() - color.red()) < 50 and \
                       abs(current_color.green() - color.green()) < 50 and \
                       abs(current_color.blue() - color.blue()) < 50
            
            if is_active:
                check_label = QLabel("✓")
                check_label.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 14px;")
                layout.addWidget(check_label)
            
            # Carré de couleur
            color_label = QLabel()
            color_label.setFixedSize(20, 20)
            color_label.setStyleSheet(f"background:{color.name()}; border-radius:3px; border: {'2px solid #00ff00' if is_active else '1px solid #666'};")
            layout.addWidget(color_label)
            
            # Nom de la couleur
            text_label = QLabel(name)
            text_label.setStyleSheet(f"color: {'#00ff00' if is_active else '#ddd'}; font-size: 13px; font-weight: {'bold' if is_active else 'normal'};")
            layout.addWidget(text_label)
            layout.addStretch()
            
            action.setDefaultWidget(widget)
            action.triggered.connect(lambda checked=False, c=color, g=group, i=idx: self.change_projector_color_only(g, i, c))
            menu.addAction(action)
        
        menu.exec(lamp.mapToGlobal(pos))
    
    def set_projector_dimmer(self, proj, level):
        """Change le dimmer d'un projecteur et met à jour plan de feu + DMX"""
        proj.level = level
        
        # Recalculer couleur avec nouveau niveau
        if level > 0:
            brightness = level / 100.0
            proj.color = QColor(
                int(proj.base_color.red() * brightness),
                int(proj.base_color.green() * brightness),
                int(proj.base_color.blue() * brightness)
            )
        else:
            proj.color = QColor(0, 0, 0)
        
        # Mettre à jour DMX via ArtNet
        if self.main_window and hasattr(self.main_window, 'artnet') and self.main_window.artnet:
            self.main_window.artnet.update_from_projectors(self.projectors)
        
        # Rafraîchir plan de feu
        self.refresh()
    
    def change_projector_color_only(self, group, idx, color):
        """Change UNIQUEMENT la couleur d'un projecteur spécifique, sans toucher au dimmer ni activer de pad"""
        # Trouver le projecteur
        projs = [p for p in self.projectors if p.group == group]
        if idx < len(projs):
            p = projs[idx]
            p.base_color = color
            
            # Recalculer la couleur avec le niveau actuel (SANS CHANGER le level)
            if p.level > 0:
                brightness = p.level / 100.0
                p.color = QColor(
                    int(color.red() * brightness),
                    int(color.green() * brightness),
                    int(color.blue() * brightness)
                )
            else:
                # Même si level = 0, mettre la base_color pour qu'elle soit prête
                p.color = QColor(0, 0, 0)
    
    def change_projector_color(self, group, idx, color, pad_row):
        """ANCIENNE VERSION - Change la couleur et active le PAD (gardée pour compatibilité)"""
        self.change_projector_color_only(group, idx, color)

    def refresh(self):
        for group, idx, lamp in self.lamps:
            projs = [p for p in self.projectors if p.group == group]
            if idx < len(projs):
                p = projs[idx]
                if p.level > 0 and not p.muted:
                    lamp.setStyleSheet(f"background:{p.color.name()}; border-radius:12px; border: 2px solid {p.color.lighter(150).name()};")
                else:
                    lamp.setStyleSheet("background:#0a0a0a; border-radius:12px; border: 2px solid #2a2a2a;")

class RecordingWaveform(QWidget):
    """Timeline éditable avec blocs colorés pour la lumière"""
    def __init__(self):
        super().__init__()
        self.blocks = []  # Blocs lumière {start_ms, end_ms, color, level}
        self.duration = 0
        self.current_position = 0
        self.dragging_block = None
        self.drag_edge = None
        self.setStyleSheet("background: #1a1a1a; border-radius: 4px;")
        self.setMouseTracking(True)
    
    def add_block(self, start_ms, end_ms, color, level):
        """Ajoute un bloc de couleur"""
        self.blocks.append({
            'start': start_ms,
            'end': end_ms,
            'color': color,
            'level': level
        })
        self.update()
    
    def add_keyframe(self, time_ms, faders, pad_color):
        """Convertit un keyframe en bloc"""
        if not pad_color:
            pad_color = QColor("#666666")
        self.add_block(time_ms, time_ms + 500, pad_color, faders[0] if faders else 0)
    
    def set_position(self, position_ms, duration_ms):
        """Met à jour la position actuelle"""
        self.current_position = position_ms
        self.duration = duration_ms
        self.update()
    
    def clear(self):
        """Efface la timeline"""
        self.blocks = []
        self.duration = 0
        self.current_position = 0
        self.update()
    
    def mousePressEvent(self, event):
        """Détecte les clics sur les blocs"""
        if self.duration == 0:
            return
        
        x = event.position().x()
        w = self.width()
        
        for block in self.blocks:
            start_x = (block['start'] / self.duration) * w
            end_x = (block['end'] / self.duration) * w
            
            if abs(x - start_x) < 5:
                self.dragging_block = block
                self.drag_edge = 'left'
                return
            
            if abs(x - end_x) < 5:
                self.dragging_block = block
                self.drag_edge = 'right'
                return
            
            if start_x < x < end_x:
                self.dragging_block = block
                self.drag_edge = 'middle'
                self.drag_start_x = x
                self.drag_start_time = block['start']
                return
    
    def mouseMoveEvent(self, event):
        """Gère le drag des blocs"""
        if not self.dragging_block or self.duration == 0:
            x = event.position().x()
            w = self.width()
            cursor_set = False
            
            for block in self.blocks:
                start_x = (block['start'] / self.duration) * w
                end_x = (block['end'] / self.duration) * w
                
                if abs(x - start_x) < 5 or abs(x - end_x) < 5:
                    self.setCursor(QCursor(Qt.SizeHorCursor))
                    cursor_set = True
                    break
                elif start_x < x < end_x:
                    self.setCursor(QCursor(Qt.OpenHandCursor))
                    cursor_set = True
                    break
            
            if not cursor_set:
                self.setCursor(QCursor(Qt.ArrowCursor))
            return
        
        x = event.position().x()
        w = self.width()
        time_at_x = (x / w) * self.duration
        
        if self.drag_edge == 'left':
            self.dragging_block['start'] = max(0, min(time_at_x, self.dragging_block['end'] - 100))
        elif self.drag_edge == 'right':
            self.dragging_block['end'] = max(self.dragging_block['start'] + 100, min(time_at_x, self.duration))
        elif self.drag_edge == 'middle':
            delta_x = x - self.drag_start_x
            delta_time = (delta_x / w) * self.duration
            new_start = self.drag_start_time + delta_time
            block_duration = self.dragging_block['end'] - self.dragging_block['start']
            
            if new_start < 0:
                new_start = 0
            if new_start + block_duration > self.duration:
                new_start = self.duration - block_duration
            
            self.dragging_block['start'] = new_start
            self.dragging_block['end'] = new_start + block_duration
        
        self.update()
    
    def mouseReleaseEvent(self, event):
        self.dragging_block = None
        self.drag_edge = None
        self.setCursor(QCursor(Qt.ArrowCursor))
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # Fond
        painter.fillRect(0, 0, w, h, QColor("#1a1a1a"))
        
        if self.duration == 0:
            painter.setPen(QColor("#666666"))
            painter.drawText(5, 15, "💡 Timeline Lumière")
            return
        
        # Grille temporelle
        painter.setPen(QPen(QColor("#2a2a2a"), 1))
        for sec in range(0, int(self.duration / 1000) + 1):
            x = (sec * 1000 / self.duration) * w
            painter.drawLine(int(x), 0, int(x), h)
        
        # Blocs
        painter.setPen(Qt.NoPen)
        for block in self.blocks:
            start_x = int((block['start'] / self.duration) * w)
            end_x = int((block['end'] / self.duration) * w)
            block_width = max(2, end_x - start_x)
            
            color = block['color']
            opacity = int(255 * (block['level'] / 100.0)) if block['level'] > 0 else 50
            color.setAlpha(opacity)
            
            painter.setBrush(color)
            painter.drawRect(start_x, 0, block_width, h)
            
            painter.setPen(QPen(color.lighter(150), 1))
            painter.drawRect(start_x, 0, block_width, h)
            painter.setPen(Qt.NoPen)
        
        # Curseur
        if self.current_position > 0:
            x = int((self.current_position / self.duration) * w)
            painter.setPen(QPen(QColor("#00d4ff"), 3))
            painter.drawLine(x, 0, x, h)
        
        # Label
        if len(self.blocks) > 0:
            painter.setPen(QColor("#00d4ff"))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(10)
            painter.setFont(font)
            painter.drawText(5, 12, f"💡 {len(self.blocks)} blocs")

class Sequencer(QFrame):
    def __init__(self, player_ui):
        super().__init__()
        self.player_ui = player_ui
        self.current_row = -1
        self.is_dirty = False
        
        # Système d'enregistrement de séquences
        self.sequences = {}  # {row: {"keyframes": [...], "duration": ms}}
        self.recording = False
        self.recording_row = -1
        self.recording_start_time = 0
        self.recording_timer = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        header = QHBoxLayout()
        title = QLabel("🎬 Séquenceur")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        header.addWidget(title)
        header.addStretch()
        
        btn_style = """
            QPushButton {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                color: #00d4ff;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: #3a3a3a;
                border: 1px solid #00d4ff;
            }
            QPushButton:pressed {
                background: #1a1a1a;
            }
        """
        
        self.up_btn = QPushButton("▲")
        self.up_btn.setFixedSize(40, 32)
        self.up_btn.setStyleSheet(btn_style)
        self.up_btn.clicked.connect(self.move_up)
        header.addWidget(self.up_btn)
        
        self.down_btn = QPushButton("▼")
        self.down_btn.setFixedSize(40, 32)
        self.down_btn.setStyleSheet(btn_style)
        self.down_btn.clicked.connect(self.move_down)
        header.addWidget(self.down_btn)
        
        self.del_btn = QPushButton("🗑")
        self.del_btn.setFixedSize(40, 32)
        self.del_btn.setStyleSheet(btn_style)
        self.del_btn.clicked.connect(self.delete_selected)
        header.addWidget(self.del_btn)
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(40, 32)
        self.add_btn.setStyleSheet(btn_style + "QPushButton { font-size: 18px; }")
        self.add_btn.clicked.connect(self.show_add_menu)
        header.addWidget(self.add_btn)
        
        layout.addLayout(header)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Titre", "Durée", "Vol %", "DMX"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_media_context_menu)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(55)  # Augmenté de 45 à 55
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(2, 90)  # Augmenté pour la durée
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 130)  # Augmenté pour le DMX
        self.table.setStyleSheet("""
            QTableWidget {
                background: #0a0a0a;
                border: 1px solid #2a2a2a;
                border-radius: 6px;
                gridline-color: #1a1a1a;
                outline: none;
            }
            QTableWidget::item {
                padding: 10px 8px;
                border-bottom: 1px solid #1a1a1a;
                font-size: 14px;
                color: #e0e0e0;
                outline: none;
            }
            QTableWidget::item:selected {
                background: #2a4a5a;
                border-left: 3px solid #4a8aaa;
                outline: none;
            }
            QTableWidget::item:focus {
                outline: none;
                border: none;
            }
            QHeaderView::section {
                background: #1a1a1a;
                color: #999;
                padding: 10px 8px;
                border: none;
                border-bottom: 2px solid #2a2a2a;
                font-weight: bold;
                font-size: 11px;
                text-transform: uppercase;
            }
        """)
        
        # Menu contextuel pour éditer les lignes
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_row_context_menu)
        
        layout.addWidget(self.table)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui_state)
        self.timer.start(200)

    def show_add_menu(self):
        """Menu contextuel pour ajouter média, pause ou tempo"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                border: 1px solid #2a2a2a;
                padding: 8px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
                color: #ddd;
            }
            QMenu::item:selected {
                background: #2a4a5a;
            }
        """)
        menu.addAction("📁 Ajouter un média", self.add_files_dialog)
        menu.addAction("⏸ Ajouter une pause", self.add_pause)
        menu.addAction("⏱ Ajouter une temporisation", self.add_tempo)
        menu.exec(QCursor.pos())

    def add_pause(self):
        """Ajoute une pause dans la séquence après l'élément sélectionné"""
        current = self.table.currentRow()
        if current >= 0:
            r = current + 1
        else:
            r = self.table.rowCount()
        
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(""))  # Pas d'émoji
        pause_item = QTableWidgetItem("PAUSE")
        pause_item.setData(Qt.UserRole, "PAUSE")
        self.table.setItem(r, 1, pause_item)
        self.table.setItem(r, 2, QTableWidgetItem("--:--"))
        self.table.setItem(r, 3, QTableWidgetItem("--"))
        
        # Ajouter un widget vide pour la colonne DMX
        empty_widget = QWidget()
        self.table.setCellWidget(r, 4, empty_widget)
        
        # Sélectionner la nouvelle ligne
        self.table.selectRow(r)
        
        self.is_dirty = True

    def move_up(self):
        row = self.table.currentRow()
        if row > 0:
            self.swap_rows(row, row - 1)
            self.table.selectRow(row - 1)
            self.is_dirty = True

    def move_down(self):
        row = self.table.currentRow()
        if 0 <= row < self.table.rowCount() - 1:
            self.swap_rows(row, row + 1)
            self.table.selectRow(row + 1)
            self.is_dirty = True

    def swap_rows(self, r1, r2):
        """Échange deux lignes en gérant correctement les items et widgets"""
        try:
            for col in range(self.table.columnCount()):
                if col == 4:  # Colonne DMX avec widget
                    w1 = self.table.cellWidget(r1, col)
                    w2 = self.table.cellWidget(r2, col)
                    
                    # Créer des copies temporaires pour éviter les problèmes
                    w1_data = None
                    w2_data = None
                    
                    if w1 and isinstance(w1, QComboBox):
                        w1_data = w1.currentText()
                    if w2 and isinstance(w2, QComboBox):
                        w2_data = w2.currentText()
                    
                    # Retirer les widgets
                    self.table.removeCellWidget(r1, col)
                    self.table.removeCellWidget(r2, col)
                    
                    # Recréer les widgets
                    if w2_data:
                        new_combo1 = QComboBox()
                        new_combo1.addItems(["Manuel", "IA Lumière"])
                        new_combo1.setCurrentText(w2_data)
                        new_combo1.setStyleSheet("""
                            QComboBox {
                                background: #1a1a1a;
                                border: 1px solid #2a2a2a;
                                border-radius: 3px;
                                padding: 8px 6px;
                                color: #ddd;
                                font-size: 12px;
                                font-weight: bold;
                            }
                        """)
                        new_combo1.currentTextChanged.connect(lambda text, row=r1: self.on_dmx_changed(row, text))
                        self.table.setCellWidget(r1, col, new_combo1)
                        self.on_dmx_changed(r1, w2_data)
                    elif w2:
                        # Widget vide (pause)
                        self.table.setCellWidget(r1, col, QWidget())
                    
                    if w1_data:
                        new_combo2 = QComboBox()
                        new_combo2.addItems(["Manuel", "IA Lumière"])
                        new_combo2.setCurrentText(w1_data)
                        new_combo2.setStyleSheet("""
                            QComboBox {
                                background: #1a1a1a;
                                border: 1px solid #2a2a2a;
                                border-radius: 3px;
                                padding: 8px 6px;
                                color: #ddd;
                                font-size: 12px;
                                font-weight: bold;
                            }
                        """)
                        new_combo2.currentTextChanged.connect(lambda text, row=r2: self.on_dmx_changed(row, text))
                        self.table.setCellWidget(r2, col, new_combo2)
                        self.on_dmx_changed(r2, w1_data)
                    elif w1:
                        # Widget vide (pause)
                        self.table.setCellWidget(r2, col, QWidget())
                else:
                    # Pour les items normaux
                    item1 = self.table.takeItem(r1, col)
                    item2 = self.table.takeItem(r2, col)
                    
                    if item2:
                        self.table.setItem(r1, col, item2)
                    if item1:
                        self.table.setItem(r2, col, item1)
            
            # Mettre à jour current_row
            if self.current_row == r1:
                self.current_row = r2
            elif self.current_row == r2:
                self.current_row = r1
        except Exception as e:
            print(f"Erreur swap_rows: {e}")

    def delete_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self.is_dirty = True
            if self.current_row == row:
                self.current_row = -1
            elif self.current_row > row:
                self.current_row -= 1

    def clear_sequence(self):
        self.table.setRowCount(0)
        self.current_row = -1
        self.is_dirty = False

    def set_volume(self, row, value):
        vol = int(value / 1.27)
        if self.table.item(row, 3):
            self.table.item(row, 3).setText(str(vol))
            self.is_dirty = True
    
    def add_tempo(self):
        """Ajoute une temporisation de 10s par défaut"""
        current = self.table.currentRow()
        if current >= 0:
            r = current + 1
        else:
            r = self.table.rowCount()
        
        self.table.insertRow(r)
        
        # Pas d'icône (colonne vide)
        self.table.setItem(r, 0, QTableWidgetItem(""))
        
        # Titre (affiche "Pause minutée")
        tempo_item = QTableWidgetItem("⏱ Pause minutée")
        tempo_item.setData(Qt.UserRole, "TEMPO:10")
        self.table.setItem(r, 1, tempo_item)
        
        # Durée
        dur_item = QTableWidgetItem("00:10")
        self.table.setItem(r, 2, dur_item)
        
        # Volume (toujours --)
        vol_item = QTableWidgetItem("--")
        self.table.setItem(r, 3, vol_item)
        
        # DMX (Manuel par défaut pour les tempos)
        dmx_combo = QComboBox()
        dmx_combo.addItems(["Manuel", "IA Lumière"])
        dmx_combo.setCurrentText("Manuel")
        dmx_combo.setStyleSheet("""
            QComboBox {
                background: #2a2a2a;
                color: white;
                border: 1px solid #3a3a3a;
                padding: 4px;
                border-radius: 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 6px;
            }
        """)
        self.table.setCellWidget(r, 4, dmx_combo)
        
        # Sélectionner la nouvelle ligne
        self.table.selectRow(r)
        
        self.is_dirty = True

    def show_row_context_menu(self, pos):
        """Menu contextuel sur une ligne du séquenceur"""
        item = self.table.itemAt(pos)
        if not item:
            return
        
        row = item.row()
        title_item = self.table.item(row, 1)
        if not title_item:
            return
        
        data = title_item.data(Qt.UserRole)
        
        # Menu spécial pour les TEMPO
        if data and str(data).startswith("TEMPO:"):
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background: #1a1a1a;
                    border: 1px solid #2a2a2a;
                    padding: 8px;
                }
                QMenu::item {
                    padding: 8px 20px;
                    border-radius: 4px;
                    color: #ddd;
                }
                QMenu::item:selected {
                    background: #2a4a5a;
                }
            """)
            
            edit_action = menu.addAction("⏱ Régler la durée")
            delete_action = menu.addAction("🗑️ Supprimer")
            
            action = menu.exec(self.table.viewport().mapToGlobal(pos))
            
            if action == edit_action:
                self.edit_tempo_duration_with_slider(row)
            elif action == delete_action:
                self.table.removeRow(row)
                self.is_dirty = True
    
    def edit_tempo_duration_with_slider(self, row):
        """Édite la durée d'un TEMPO avec un fader"""
        title_item = self.table.item(row, 1)
        if not title_item:
            return
            
        data = title_item.data(Qt.UserRole)
        if not data or not str(data).startswith("TEMPO:"):
            return
            
        current_seconds = int(str(data).split(":")[1])
        
        # Créer un dialog avec fader
        dialog = QDialog(self)
        dialog.setWindowTitle("⏱ Régler la temporisation")
        dialog.setMinimumWidth(350)
        
        layout = QVBoxLayout(dialog)
        
        # Label avec valeur
        value_label = QLabel(f"Durée: {current_seconds} secondes")
        value_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("color: #ffa500; padding: 10px;")
        layout.addWidget(value_label)
        
        # Fader horizontal
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(1)
        slider.setMaximum(600)  # 10 minutes max
        slider.setValue(current_seconds)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(60)  # Tick toutes les minutes
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #3a3a3a;
                height: 8px;
                background: #1a1a1a;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #ffa500;
                border: 2px solid #ffcc00;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffcc00;
            }
        """)
        
        def update_label(value):
            minutes = value // 60
            seconds = value % 60
            if minutes > 0:
                value_label.setText(f"Durée: {minutes}m {seconds}s ({value}s)")
            else:
                value_label.setText(f"Durée: {value} secondes")
        
        slider.valueChanged.connect(update_label)
        layout.addWidget(slider)
        
        # Boutons
        btn_layout = QHBoxLayout()
        
        ok_btn = QPushButton("✅ OK")
        ok_btn.clicked.connect(dialog.accept)
        ok_btn.setStyleSheet("""
            QPushButton {
                background: #2a4a5a;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3a5a6a;
            }
        """)
        btn_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("❌ Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #4a4a4a;
            }
        """)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        if dialog.exec() == QDialog.Accepted:
            value = slider.value()
            
            # Mettre à jour les données
            title_item.setData(Qt.UserRole, f"TEMPO:{value}")
            
            # Mettre à jour la durée affichée
            dur_item = self.table.item(row, 2)
            if dur_item:
                minutes = value // 60
                seconds = value % 60
                dur_item.setText(f"{minutes:02d}:{seconds:02d}")
            
            self.is_dirty = True

    def add_files_dialog(self):
        files = QFileDialog.getOpenFileNames(self, "Ajouter des médias", "", "Médias (*)")[0]
        if files: self.add_files(files)

    def add_files(self, files):
        for f in files:
            try:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(media_icon(f)))
                it = QTableWidgetItem(Path(f).name)
                it.setData(Qt.UserRole, f)
                self.table.setItem(r, 1, it)
                dur_item = QTableWidgetItem("--:--")
                self.table.setItem(r, 2, dur_item)
                self.table.setItem(r, 3, QTableWidgetItem("100"))
                
                dmx_combo = QComboBox()
                dmx_combo.addItems(["Manuel", "IA Lumière"])
                dmx_combo.setCurrentText("Manuel")
                dmx_combo.setStyleSheet("""
                    QComboBox {
                        background: #1a1a1a;
                        border: 1px solid #2a2a2a;
                        border-radius: 3px;
                        padding: 8px 6px;
                        color: #ddd;
                        font-size: 12px;
                        font-weight: bold;
                    }
                """)
                dmx_combo.currentTextChanged.connect(lambda text, row=r: self.on_dmx_changed(row, text))
                self.table.setCellWidget(r, 4, dmx_combo)
                
                # Charger la durée avec un QMediaPlayer temporaire
                temp_p = QMediaPlayer()
                
                def update_duration(duration, row_idx=r):
                    if duration > 0:
                        item = self.table.item(row_idx, 2)
                        if item:
                            item.setText(fmt_time(duration))
                
                temp_p.durationChanged.connect(update_duration)
                temp_p.setSource(QUrl.fromLocalFile(f))
                
            except Exception as e:
                print(f"Erreur ajout fichier: {e}")
                continue
        self.is_dirty = True

    def on_dmx_changed(self, row, text):
        """Gère le changement de mode DMX"""
        widget = self.table.cellWidget(row, 4)
        if not widget:
            return
        
        # Si widget est un container, récupérer le QComboBox
        if not isinstance(widget, QComboBox):
            for i in range(widget.layout().count() if hasattr(widget, 'layout') else 0):
                item = widget.layout().itemAt(i)
                if item and isinstance(item.widget(), QComboBox):
                    widget = item.widget()
                    break
        
        if not isinstance(widget, QComboBox):
            return
        
        # Appliquer le style selon le mode
        if text == "IA Lumière":
            widget.setStyleSheet("""
                QComboBox {
                    background: #1a2a4a;
                    border: none;
                    border-radius: 3px;
                    padding: 8px 6px;
                    color: #aaccff;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
        elif text == "Programme":
            widget.setStyleSheet("""
                QComboBox {
                    background: #1a4a1a;
                    border: none;
                    border-radius: 3px;
                    padding: 8px 6px;
                    color: #ccffcc;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
        elif text == "Play Lumière":
            widget.setStyleSheet("""
                QComboBox {
                    background: #4a1a4a;
                    border: none;
                    border-radius: 3px;
                    padding: 8px 6px;
                    color: #ffccff;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)
        else:
            # Mode Manuel
            widget.setStyleSheet("""
                QComboBox {
                    background: #1a1a1a;
                    border: none;
                    border-radius: 3px;
                    padding: 8px 6px;
                    color: #ddd;
                    font-size: 12px;
                    font-weight: bold;
                }
            """)

    def update_ui_state(self):
        for r in range(self.table.rowCount()):
            bg = "#0a0a0a"
            if r == self.current_row:
                dmx_widget = self.table.cellWidget(r, 4)
                if dmx_widget and isinstance(dmx_widget, QComboBox):
                    mode = dmx_widget.currentText()
                    if mode == "Manuel":
                        bg = "#1a3a5a"
                    elif mode == "IA Lumière":
                        bg = "#5a1a1a"
                    elif mode == "Programme":
                        bg = "#1a5a1a"
                elif not dmx_widget or isinstance(dmx_widget, QWidget):
                    # C'est une pause
                    bg = "#3a3a1a"
            
            for c in range(4):
                it = self.table.item(r, c)
                if it: 
                    it.setBackground(QBrush(QColor(bg)))
                    # Texte toujours en blanc
                    it.setForeground(QBrush(QColor("#ffffff")))

    def update_playing_indicator(self, playing_row):
        """Met à jour l'émoji de lecture : 🟢 pour la ligne en cours, vide pour les autres"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                if row == playing_row:
                    item.setText("🟢")
                else:
                    item.setText("")
    
    def play_row(self, row):
        if 0 <= row < self.table.rowCount():
            try:
                # Mettre à jour les émojis (enlever l'ancien, ajouter le nouveau)
                self.update_playing_indicator(row)
                
                item = self.table.item(row, 1)
                data = item.data(Qt.UserRole) if item else None
                
                # Vérifier si c'est un TEMPO
                if data and str(data).startswith("TEMPO:"):
                    seconds = int(str(data).split(":")[1])
                    self.current_row = row
                    self.table.selectRow(row)
                    print(f"⏱ Pause minutée: Attente de {seconds} secondes...")
                    
                    # ARRÊTER le player (couper le son)
                    self.player_ui.player.stop()
                    
                    # Créer un timer pour la timeline du TEMPO
                    self.tempo_elapsed = 0
                    self.tempo_duration = seconds * 1000  # en ms
                    
                    if not hasattr(self, 'tempo_timer'):
                        self.tempo_timer = QTimer()
                        self.tempo_timer.timeout.connect(self.update_tempo_timeline)
                    
                    self.tempo_timer.start(100)  # Update toutes les 100ms
                    
                    # Timer pour passer au suivant
                    QTimer.singleShot(seconds * 1000, lambda: self.continue_after_tempo_in_seq(row))
                    return
                
                # Vérifier si c'est une pause
                if data == "PAUSE":
                    print("⏸ PAUSE - Blackout complet (lumières + pads)")
                    
                    # Blackout complet
                    self.player_ui.full_blackout()
                    
                    # Charger le média suivant mais en pause
                    next_row = row + 1
                    if next_row < self.table.rowCount():
                        next_item = self.table.item(next_row, 1)
                        if next_item and next_item.data(Qt.UserRole) != "PAUSE":
                            vol_item = self.table.item(next_row, 3)
                            if vol_item:
                                path = next_item.data(Qt.UserRole)
                                vol = int(vol_item.text())
                                self.player_ui.audio.setVolume(vol / 100)
                                self.player_ui.player.setSource(QUrl.fromLocalFile(path))
                                # Mettre à jour current_row AVANT de trigger pause
                                self.current_row = next_row
                                self.player_ui.trigger_pause_mode()
                    return
                
                # Lecture normale d'un média
                self.current_row = row
                vol_item = self.table.item(row, 3)
                if item and vol_item:
                    path = item.data(Qt.UserRole)
                    vol = int(vol_item.text())
                    self.player_ui.audio.setVolume(vol / 100)
                    self.player_ui.player.setSource(QUrl.fromLocalFile(path))
                    self.player_ui.player.play()
                    
                    # Gérer la timeline selon le mode DMX
                    dmx_mode = self.get_dmx_mode(row)
                    
                    # Détecter changement de mode et faire blackout si nécessaire
                    if hasattr(self, 'last_dmx_mode'):
                        # Passage d'un mode automatique vers Manuel
                        if self.last_dmx_mode in ["IA Lumière", "Programme"] and dmx_mode == "Manuel":
                            print(f"🔲 Transition {self.last_dmx_mode} → Manuel : Blackout complet")
                            self.player_ui.full_blackout()
                    
                    self.last_dmx_mode = dmx_mode
                    
                    if dmx_mode == "Programme":
                        # Mode Programme : afficher timeline et jouer séquence ancienne
                        self.play_sequence(row)
                    elif dmx_mode == "Play Lumière":
                        # Mode Play Lumière : jouer timeline moderne
                        print(f"🎬 Mode Play Lumière activé")
                        self.play_sequence(row)  # Utilise play_timeline_sequence
                    else:
                        # Mode Manuel ou IA Lumière : cacher la timeline
                        self.player_ui.recording_waveform.hide()
                        print(f"🎬 Mode {dmx_mode} : Timeline masquée")
            except Exception as e:
                print(f"Erreur lecture: {e}")
                QMessageBox.critical(None, "Erreur", f"Impossible de lire: {e}")

    def update_tempo_timeline(self):
        """Met à jour la timeline pendant une Pause minutée"""
        self.tempo_elapsed += 100
        
        if self.tempo_elapsed >= self.tempo_duration:
            self.tempo_timer.stop()
            self.tempo_elapsed = 0
        
        # Mettre à jour la timeline
        progress = (self.tempo_elapsed / self.tempo_duration) * self.player_ui.timeline.maximum() if self.tempo_duration > 0 else 0
        self.player_ui.timeline.setValue(int(progress))
        
        # Mettre à jour le temps
        seconds = self.tempo_elapsed // 1000
        total_seconds = self.tempo_duration // 1000
        self.player_ui.time_label.setText(f"{seconds//60:02d}:{seconds%60:02d}")
        remaining_seconds = total_seconds - seconds
        self.player_ui.remaining_label.setText(f"-{remaining_seconds//60:02d}:{remaining_seconds%60:02d}")
    
    def continue_after_tempo_in_seq(self, tempo_row):
        """Continue la séquence après une Pause minutée depuis play_row"""
        if hasattr(self, 'tempo_timer'):
            self.tempo_timer.stop()
        
        next_row = tempo_row + 1
        if next_row < self.table.rowCount():
            self.play_row(next_row)
        else:
            print("✅ Fin de la séquence")

    def get_dmx_mode(self, row):
        """Récupère le mode DMX d'une ligne (supporte les containers avec REC)"""
        widget = self.table.cellWidget(row, 4)
        if widget:
            # Si c'est un container (mode Programme avec bouton REC)
            if isinstance(widget, QWidget) and not isinstance(widget, QComboBox):
                # Chercher le QComboBox dans le layout
                for i in range(widget.layout().count()):
                    item = widget.layout().itemAt(i)
                    if item and isinstance(item.widget(), QComboBox):
                        return item.widget().currentText()
            # Si c'est directement un QComboBox
            elif isinstance(widget, QComboBox):
                return widget.currentText()
        return "Manuel"
    
    def toggle_recording(self, row, checked):
        """Active/désactive l'enregistrement d'une séquence"""
        if checked:
            # Démarrer l'enregistrement
            self.recording = True
            self.recording_row = row
            self.recording_start_time = 0
            
            # Initialiser la séquence
            self.sequences[row] = {
                "keyframes": [],
                "duration": 0
            }
            
            # Timer pour enregistrer les keyframes toutes les 500ms
            if not self.recording_timer:
                self.recording_timer = QTimer()
                self.recording_timer.timeout.connect(self.record_keyframe)
            
            self.recording_timer.start(500)  # Enregistrer toutes les 500ms
            print(f"🔴 Enregistrement séquence ligne {row} démarré")
        
        else:
            # Arrêter l'enregistrement
            self.recording = False
            if self.recording_timer:
                self.recording_timer.stop()
            
            # Sauvegarder la durée totale
            if self.recording_row in self.sequences:
                self.sequences[self.recording_row]["duration"] = self.recording_start_time
                nb_keyframes = len(self.sequences[self.recording_row]["keyframes"])
                print(f"⏹ Enregistrement arrêté - {nb_keyframes} keyframes enregistrés ({self.recording_start_time/1000:.1f}s)")
            
            self.recording_row = -1
            self.recording_start_time = 0
            self.is_dirty = True
    
    def record_keyframe(self):
        """Enregistre un keyframe de l'état actuel AKAI"""
        if not self.recording or self.recording_row < 0:
            return
        
        # Capturer l'état actuel
        main_window = self.player_ui
        
        keyframe = {
            "time": self.recording_start_time,
            "faders": [],
            "active_pad": None,
            "active_effects": []
        }
        
        # Capturer les 9 faders (0-8)
        for i in range(9):
            if i in main_window.faders:
                keyframe["faders"].append(main_window.faders[i].value)
            else:
                keyframe["faders"].append(0)
        
        # Capturer le pad actif
        if main_window.active_pad:
            for (r, c), pad in main_window.pads.items():
                if pad == main_window.active_pad:
                    keyframe["active_pad"] = {
                        "row": r,
                        "col": c,
                        "color": pad.property("base_color").name()
                    }
                    break
        
        # Capturer les effets actifs
        for i, btn in enumerate(main_window.effect_buttons):
            keyframe["active_effects"].append(btn.active)
        
        # Ajouter le keyframe
        self.sequences[self.recording_row]["keyframes"].append(keyframe)
        
        # Mettre à jour la waveform avec la couleur
        pad_color = None
        if keyframe["active_pad"]:
            pad_color = QColor(keyframe["active_pad"]["color"])
        main_window.recording_waveform.add_keyframe(
            self.recording_start_time, 
            keyframe["faders"],
            pad_color
        )
        
        # Debug log
        print(f"📹 Keyframe {len(self.sequences[self.recording_row]['keyframes'])}: "
              f"Faders={keyframe['faders'][:4]}... "
              f"Pad={'✓' if keyframe['active_pad'] else '✗'} "
              f"Effets={sum(keyframe['active_effects'])}")
        
        # Incrémenter le temps
        self.recording_start_time += 500
    
    def play_sequence(self, row):
        """Joue une séquence - NOUVEAU système timeline ou ANCIEN keyframes"""
        if row not in self.sequences:
            return
        
        sequence = self.sequences[row]
        
        # Détecter nouveau format (clips) vs ancien (keyframes)
        if "clips" in sequence:
            # NOUVEAU: Timeline avec clips
            self.play_timeline_sequence(row)
        elif "keyframes" in sequence:
            # ANCIEN: Système keyframes
            self.play_keyframes_sequence(row)
    
    def play_timeline_sequence(self, row):
        """NOUVEAU: Joue séquence timeline avec clips"""
        sequence = self.sequences[row]
        clips_data = sequence.get("clips", [])
        
        if not clips_data:
            print("⚠️ Aucun clip dans la séquence")
            return
        
        print(f"▶️ Lecture timeline ligne {row} - {len(clips_data)} clips")
        
        # Organiser clips par piste
        tracks_clips = {
            'Face': [],
            'Douche 1': [],
            'Douche 2': [],
            'Douche 3': [],
            'Contres': []
        }
        
        for clip_data in clips_data:
            track_name = clip_data.get('track', 'Face')
            tracks_clips[track_name].append(clip_data)
        
        # Stocker pour playback
        self.timeline_playback_row = row
        self.timeline_tracks_data = tracks_clips
        self.timeline_last_update = 0
        
        # Timer playback
        if not hasattr(self, 'timeline_playback_timer'):
            self.timeline_playback_timer = QTimer()
            self.timeline_playback_timer.timeout.connect(self.update_timeline_playback)
        
        self.timeline_playback_timer.start(50)  # 20 FPS
        print(f"✅ Timeline playback démarré")
    
    def update_timeline_playback(self):
        """Met à jour DMX selon position timeline"""
        if not hasattr(self, 'timeline_playback_row'):
            print("⚠️ timeline_playback_row pas défini")
            return
        
        # Position actuelle (ms)
        current_time = self.player_ui.player.position()
        
        # Ne mettre à jour que si changement significatif (>30ms)
        if abs(current_time - self.timeline_last_update) < 30:
            return
        
        print(f"⏱️ Timeline update: position={current_time/1000:.2f}s")
        self.timeline_last_update = current_time
        
        # Pour chaque piste, trouver clip actif
        active_clips = {}
        
        for track_name, clips in self.timeline_tracks_data.items():
            for clip_data in clips:
                start = clip_data['start']
                end = start + clip_data['duration']
                
                # Clip actif à ce temps
                if start <= current_time <= end:
                    # Calculer intensité avec fades
                    intensity = self.calculate_clip_intensity(clip_data, current_time)
                    
                    active_clips[track_name] = {
                        'color': QColor(clip_data['color']),
                        'color2': QColor(clip_data['color2']) if 'color2' in clip_data else None,
                        'intensity': intensity
                    }
                    break  # Un seul clip actif par piste
        
        # Appliquer aux projecteurs
        self.apply_timeline_to_dmx(active_clips)
    
    def calculate_clip_intensity(self, clip_data, current_time):
        """Calcule intensité avec fades"""
        start = clip_data['start']
        duration = clip_data['duration']
        base_intensity = clip_data.get('intensity', 100)
        
        fade_in = clip_data.get('fade_in', 0)
        fade_out = clip_data.get('fade_out', 0)
        
        # Position relative dans le clip (0-1)
        relative_pos = (current_time - start) / duration
        
        intensity = base_intensity
        
        # Fade in
        if fade_in > 0:
            fade_in_ratio = fade_in / duration
            if relative_pos < fade_in_ratio:
                intensity *= (relative_pos / fade_in_ratio)
        
        # Fade out
        if fade_out > 0:
            fade_out_ratio = fade_out / duration
            if relative_pos > (1 - fade_out_ratio):
                intensity *= ((1 - relative_pos) / fade_out_ratio)
        
        return int(intensity)
    
    def apply_timeline_to_dmx(self, active_clips):
        """Applique les clips actifs aux projecteurs DMX"""
        # Mapping pistes → indices projecteurs
        # Projectors: 0-3=face, 4-6=douche1, 7-9=douche2, 10-12=douche3, 13-14=lat, 15-20=contre
        track_to_indices = {
            'Face': list(range(0, 4)),  # 4 projecteurs face
            'Douche 1': list(range(4, 7)),  # 3 projecteurs douche1
            'Douche 2': list(range(7, 10)),  # 3 projecteurs douche2
            'Douche 3': list(range(10, 13)),  # 3 projecteurs douche3
            'Contres': list(range(15, 21))  # 6 projecteurs contre
        }
        
        # Réinitialiser tous les projecteurs
        for proj in self.player_ui.projectors:
            proj.level = 0
            proj.base_color = QColor("black")
        
        # Appliquer clips actifs
        print(f"  📊 Clips actifs: {list(active_clips.keys())}")
        for track_name, clip_info in active_clips.items():
            indices = track_to_indices.get(track_name, [])
            color_str = clip_info['color'].name()
            if clip_info['color2']:
                color_str += f" + {clip_info['color2'].name()}"
            print(f"  🎨 {track_name}: {color_str} @ {clip_info['intensity']}% → Projos {indices}")
            
            for idx_position, idx in enumerate(indices):
                if idx >= len(self.player_ui.projectors):
                    print(f"    ⚠️ Index {idx} hors limites ({len(self.player_ui.projectors)} projos)")
                    continue
                
                proj = self.player_ui.projectors[idx]
                intensity = clip_info['intensity']
                
                # Si bicolore, alterner 1 sur 2 (AKAI style)
                if clip_info['color2']:
                    # Alterner: pair=color1, impair=color2
                    if idx_position % 2 == 0:
                        color = clip_info['color']
                    else:
                        color = clip_info['color2']
                    print(f"    🎨 Projo {idx} (pos {idx_position}): {color.name()}")
                else:
                    color = clip_info['color']
                
                # Appliquer intensité
                proj.level = intensity
                proj.base_color = color
                proj.color = QColor(
                    int(color.red() * intensity / 100),
                    int(color.green() * intensity / 100),
                    int(color.blue() * intensity / 100)
                )
                print(f"    ✅ Projo {idx}: level={intensity}, color={color.name()}")
        
        # Envoyer DMX via ArtNet
        if hasattr(self.player_ui, 'artnet') and self.player_ui.artnet:
            self.player_ui.artnet.update_from_projectors(self.player_ui.projectors)
            print("  ✅ DMX envoyé via ArtNet")
            
            # Forcer refresh du plan de feu
            if hasattr(self.player_ui, 'plan') and self.player_ui.plan:
                self.player_ui.plan.refresh()
                print("  🎭 Plan de feu rafraîchi")
        
        # === METTRE À JOUR LES PADS AKAI ===
        self.update_akai_pads_from_clips(active_clips)
    
    def update_akai_pads_from_clips(self, active_clips):
        """Met à jour la LUMINOSITÉ des pads AKAI selon les clips actifs (comme IA Lumière)"""
        # Mapping pistes → colonnes des pads
        track_to_col = {
            'Face': 0,
            'Douche 1': 1,
            'Douche 2': 2,
            'Douche 3': 3,
            'Contres': 4
        }
        
        # Convertir couleurs QColor en codes AKAI
        def qcolor_to_akai_velocity(qcolor):
            """Convertit QColor en velocity AKAI"""
            if not qcolor or qcolor == QColor("black"):
                return 0
            
            r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()
            
            if r > 200 and g < 100 and b < 100:
                return 3  # Rouge
            elif g > 200 and r < 100 and b < 100:
                return 1  # Vert
            elif r > 200 and g > 200 and b < 100:
                return 5  # Jaune
            elif r < 100 and g < 100 and b > 200:
                return 79  # Bleu
            elif r > 200 and g < 100 and b > 200:
                return 83  # Magenta
            elif r < 100 and g > 200 and b > 200:
                return 85  # Cyan
            elif r > 200 and g > 200 and b > 200:
                return 87  # Blanc
            else:
                return 1
        
        # === ÉTAPE 1: Mettre TOUS les pads à 20% luminosité ===
        if hasattr(self.player_ui, 'midi_handler'):
            midi_handler = self.player_ui.midi_handler
            
            if midi_handler and midi_handler.midi_out:
                try:
                    # Pour chaque colonne (Face, Douche1-3, Contres)
                    for col in range(5):  # Colonnes 0-4
                        # Pour chaque rangée de cette colonne
                        for row in range(8):
                            # Récupérer la couleur du pad virtuel
                            if hasattr(self.player_ui, 'akai') and hasattr(self.player_ui.akai, 'pads'):
                                pad = self.player_ui.akai.pads.get((row, col))
                                if pad:
                                    pad_color = pad.property("base_color")
                                    if pad_color:
                                        velocity = qcolor_to_akai_velocity(pad_color)
                                        # METTRE À 20% luminosité (brightness=20)
                                        midi_handler.set_pad_led(row, col, velocity, 20)
                    
                    print(f"  🔅 AKAI: Tous les pads mis à 20% luminosité")
                except Exception as e:
                    print(f"  ⚠️ Erreur reset pads: {e}")
        
        # === ÉTAPE 2: Mettre les pads ACTIFS à 100% luminosité ===
        for track_name, clip_info in active_clips.items():
            col = track_to_col.get(track_name)
            if col is None:
                continue
            
            color = clip_info['color']
            intensity = clip_info['intensity']
            velocity = qcolor_to_akai_velocity(color)
            
            print(f"  🎹 AKAI: Piste {track_name} (col {col}) → couleur {color.name()} @ {intensity}%")
            
            # Trouver le pad de cette couleur dans la colonne
            if hasattr(self.player_ui, 'akai') and hasattr(self.player_ui.akai, 'pads'):
                pad_row = 0  # Par défaut rangée 0
                
                # Chercher dans toutes les rangées pour trouver le pad de cette couleur
                for row in range(8):
                    pad = self.player_ui.akai.pads.get((row, col))
                    if pad:
                        pad_color = pad.property("base_color")
                        if pad_color and abs(pad_color.red() - color.red()) < 50 and \
                           abs(pad_color.green() - color.green()) < 50 and \
                           abs(pad_color.blue() - color.blue()) < 50:
                            pad_row = row
                            break
            
            # Mettre à jour AKAI physique
            if hasattr(self.player_ui, 'midi_handler'):
                midi_handler = self.player_ui.midi_handler
                
                if midi_handler and midi_handler.midi_out:
                    try:
                        # METTRE À 100% luminosité le pad actif
                        midi_handler.set_pad_led(pad_row, col, velocity, 100)
                        print(f"    💡 Pad ({pad_row},{col}) → 100% luminosité")
                        
                        # FADER/DIMMER
                        fader_cc = 48 + col
                        dimmer_value = int((intensity / 100) * 127)
                        midi_handler.midi_out.send_message([0xB0, fader_cc, dimmer_value])
                        print(f"    🎚️ Fader {col+1} CC{fader_cc}: {dimmer_value}/127 ({intensity}%)")
                    except Exception as e:
                        print(f"  ⚠️ Erreur MIDI: {e}")
    
    def play_keyframes_sequence(self, row):
        """ANCIEN: Joue séquence keyframes (compatibilité)"""
        sequence = self.sequences[row]
        keyframes = sequence["keyframes"]
        
        if not keyframes:
            return
        
        print(f"▶️ Lecture séquence ligne {row} - {len(keyframes)} keyframes")
        
        # Afficher la waveform et la peupler avec les keyframes enregistrés
        main_window = self.player_ui
        main_window.recording_waveform.clear()
        print(f"🎨 Construction timeline : {len(keyframes)} keyframes...")
        for kf in keyframes:
            pad_color = None
            if kf.get("active_pad"):
                pad_color = QColor(kf["active_pad"]["color"])
            main_window.recording_waveform.add_keyframe(
                kf["time"],
                kf["faders"],
                pad_color
            )
        main_window.recording_waveform.duration = sequence.get("duration", 0)
        main_window.recording_waveform.show()
        print(f"✅ Timeline affichée avec {len(main_window.recording_waveform.blocks)} blocs")
        
        # Timer pour lire les keyframes
        self.playback_row = row
        self.playback_index = 0
        
        if not hasattr(self, 'playback_timer'):
            self.playback_timer = QTimer()
            self.playback_timer.timeout.connect(self.update_sequence_playback)
        
        self.playback_timer.start(50)  # Vérifier toutes les 50ms
    
    def update_sequence_playback(self):
        """Met à jour la lecture de la séquence en fonction du temps du média"""
        if not hasattr(self, 'playback_row') or self.playback_row < 0:
            return
        
        # Temps actuel du média
        current_time = self.player_ui.player.position()
        
        sequence = self.sequences.get(self.playback_row)
        if not sequence:
            return
        
        keyframes = sequence["keyframes"]
        
        # Trouver le keyframe à appliquer
        for i, kf in enumerate(keyframes):
            if kf["time"] <= current_time < (kf["time"] + 500):
                if i != self.playback_index:
                    self.apply_keyframe(kf)
                    self.playback_index = i
                break
    
    def apply_keyframe(self, keyframe):
        """Applique un keyframe à l'état AKAI"""
        main_window = self.player_ui
        
        # Appliquer les faders
        for i, value in enumerate(keyframe["faders"]):
            if i in main_window.faders:
                main_window.faders[i].value = value
                main_window.set_proj_level(i, value)
                main_window.faders[i].update()
                
                # Mettre à jour l'AKAI physique
                if MIDI_AVAILABLE and main_window.midi_handler and main_window.midi_handler.midi_out:
                    midi_value = int((value / 100.0) * 127)
                    main_window.midi_handler.set_fader(i, midi_value)
        
        # Appliquer le pad actif
        if keyframe["active_pad"]:
            pad_info = keyframe["active_pad"]
            pad = main_window.pads.get((pad_info["row"], pad_info["col"]))
            if pad:
                main_window.activate_pad(pad, pad_info["col"])
                
                # LED AKAI
                if MIDI_AVAILABLE and main_window.midi_handler and main_window.midi_handler.midi_out:
                    velocity = rgb_to_akai_velocity(pad.property("base_color"))
                    main_window.midi_handler.set_pad_led(pad_info["row"], pad_info["col"], velocity, 100)
        
        # Appliquer les effets
        for i, active in enumerate(keyframe["active_effects"]):
            if i < len(main_window.effect_buttons):
                if active != main_window.effect_buttons[i].active:
                    main_window.toggle_effect(i)
    
    def show_media_context_menu(self, pos):
        """Menu contextuel sur média"""
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                color: white;
                border: 2px solid #4a4a4a;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 30px;
            }
            QMenu::item:selected {
                background: #4a8aaa;
            }
        """)
        
        # Volume (sans "...")
        volume_action = menu.addAction("🔊 Volume")
        volume_action.triggered.connect(lambda: self.edit_media_volume(row))
        
        # REC Lumière
        menu.addSeparator()
        rec_action = menu.addAction("🔴 REC Lumière")
        rec_action.triggered.connect(lambda: self.open_light_editor_for_row(row))
        
        # Supprimer
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Supprimer")
        delete_action.triggered.connect(lambda: self.delete_media_row(row))
        
        menu.exec(self.table.viewport().mapToGlobal(pos))
    
    def edit_media_volume(self, row):
        """Édite le volume d'un média avec slider stylé"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QSlider, QPushButton, QHBoxLayout
        
        vol_item = self.table.item(row, 3)
        if not vol_item:
            return
        
        current_vol = int(vol_item.text())
        
        dialog = QDialog(self)
        dialog.setWindowTitle("🔊 Volume")
        dialog.setFixedSize(350, 200)
        dialog.setStyleSheet("background: #1a1a1a;")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Label valeur
        value_label = QLabel(f"{current_vol}%")
        value_label.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)
        
        # Slider
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(current_vol)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #2a2a2a;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff;
                width: 20px;
                height: 20px;
                border-radius: 10px;
                margin: -6px 0;
            }
            QSlider::sub-page:horizontal {
                background: #00d4ff;
                border-radius: 4px;
            }
        """)
        slider.valueChanged.connect(lambda v: value_label.setText(f"{v}%"))
        layout.addWidget(slider)
        
        # Boutons
        btn_layout = QHBoxLayout()
        
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(dialog.reject)
        cancel.setFixedHeight(40)
        cancel.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 20px;
            }
            QPushButton:hover { background: #4a4a4a; }
        """)
        btn_layout.addWidget(cancel)
        
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(dialog.accept)
        ok.setFixedHeight(40)
        ok.setStyleSheet("""
            QPushButton {
                background: #00d4ff;
                color: black;
                border: none;
                border-radius: 6px;
                padding: 0 30px;
                font-weight: bold;
            }
            QPushButton:hover { background: #00e4ff; }
        """)
        btn_layout.addWidget(ok)
        
        layout.addLayout(btn_layout)
        
        if dialog.exec() == QDialog.Accepted:
            vol_item.setText(str(slider.value()))
            self.is_dirty = True
        
        # MASQUER LA FENÊTRE MYSTÈRE (recording_waveform)
        if hasattr(self, 'player_ui') and hasattr(self.player_ui, 'recording_waveform'):
            self.player_ui.recording_waveform.hide()
            print("🪟 recording_waveform masqué après Volume")
    
    def open_light_editor_for_row(self, row):
        """Ouvre l'éditeur de timeline pour ce média"""
        # MASQUER LA FENÊTRE MYSTÈRE avant d'ouvrir l'éditeur
        if hasattr(self, 'player_ui') and hasattr(self.player_ui, 'recording_waveform'):
            self.player_ui.recording_waveform.hide()
            print("🪟 recording_waveform masqué avant REC Lumière")
        
        self.player_ui.seq.current_row = row
        self.player_ui.open_light_editor()
    
    def delete_media_row(self, row):
        """Supprime une ligne du séquenceur"""
        from PySide6.QtWidgets import QMessageBox
        
        # Demander confirmation
        item = self.table.item(row, 1)
        media_name = item.text() if item else f"Ligne {row + 1}"
        
        reply = QMessageBox.question(
            self,
            "Supprimer média",
            f"Supprimer '{media_name}' du séquenceur ?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.table.removeRow(row)
            
            # Supprimer la séquence associée si elle existe
            if row in self.sequences:
                del self.sequences[row]
            
            # Réindexer les séquences (décaler tout ce qui est après)
            new_sequences = {}
            for old_row, seq in self.sequences.items():
                if old_row < row:
                    new_sequences[old_row] = seq
                elif old_row > row:
                    new_sequences[old_row - 1] = seq
            self.sequences = new_sequences
            
            self.is_dirty = True
            print(f"🗑️ Média '{media_name}' supprimé (row {row})")
    
    def stop_sequence_playback(self):
        """Arrête la lecture de la séquence (ancien ET nouveau système)"""
        # Ancien système (keyframes)
        if hasattr(self, 'playback_timer') and self.playback_timer:
            self.playback_timer.stop()
        self.playback_row = -1
        self.playback_index = 0
        
        # Nouveau système (timeline)
        if hasattr(self, 'timeline_playback_timer') and self.timeline_playback_timer:
            self.timeline_playback_timer.stop()
            print("⏹ Arrêt timeline playback")
        if hasattr(self, 'timeline_playback_row'):
            del self.timeline_playback_row

# --- MAIN WINDOW ---

# --- ÉDITEUR DE TIMELINE LUMIÈRE ---

class LightClip(QWidget):
    """Un clip de lumière sur la timeline avec effets et bicolore"""
    def __init__(self, start_time, duration, color, intensity, parent_track):
        super().__init__()
        self.start_time = start_time  # ms
        self.duration = duration  # ms
        self.color = color  # QColor (peut être None pour bicolore)
        self.color2 = None  # QColor pour bicolore
        self.intensity = intensity  # 0-100
        self.parent_track = parent_track
        self.dragging = False
        self.resizing = None
        
        # Effets
        self.effect = None  # "Strobe", "Flash", "Pulse", etc
        self.effect_speed = 50  # 0-100
        
        # Fades
        self.fade_in_duration = 0  # ms
        self.fade_out_duration = 0  # ms
        
        self.setMouseTracking(True)
        self.setMinimumHeight(50)
        # Forcer le widget à être opaque (pas transparent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        # Forcer au premier plan
        self.setAttribute(Qt.WA_StyledBackground, True)
        # NE PAS appeler update_visual ici - sera fait après setParent()
    
    def update_visual(self):
        """Force le redessin visuel"""
        # Juste déclencher un repaint - la couleur sera dessinée dans paintEvent
        self.update()
    
    def paintEvent(self, event):
        # NE PAS appeler super() - il efface notre dessin !
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Debug : afficher qu'on est appelé
        print(f"🎨 PAINT: color={self.color.name()} size={self.width()}x{self.height()} pos=({self.x()},{self.y()})")
        
        # FORCER fond noir d'abord pour voir le widget
        painter.fillRect(self.rect(), QColor("#000000"))
        
        # DESSINER LA COULEUR DE FOND (tout le rect)
        rect = self.rect()
        
        if hasattr(self, 'color2') and self.color2:
            # Bicolore : dégradé
            gradient = QLinearGradient(0, 0, self.width(), 0)
            gradient.setColorAt(0, self.color)
            gradient.setColorAt(1, self.color2)
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            painter.drawRect(rect)
        else:
            # Monocouleur - FORCER avec fillRect
            painter.fillRect(rect, self.color)
        
        # Bordure par dessus
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#2a2a2a"), 2))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
        
        # Fades (triangles noirs)
        if self.fade_in_duration > 0:
            fade_in_px = min(int(self.fade_in_duration * self.parent_track.pixels_per_ms), self.width() // 2)
            painter.setBrush(QColor(0, 0, 0, 140))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygon([
                QPoint(3, 3),
                QPoint(fade_in_px, 3),
                QPoint(3, self.height() - 3)
            ]))
        
        if self.fade_out_duration > 0:
            fade_out_px = min(int(self.fade_out_duration * self.parent_track.pixels_per_ms), self.width() // 2)
            painter.setBrush(QColor(0, 0, 0, 140))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygon([
                QPoint(self.width() - fade_out_px, 3),
                QPoint(self.width() - 3, 3),
                QPoint(self.width() - 3, self.height() - 3)
            ]))
        
        # Texte principal : Intensité + Effet
        if self.width() > 40:
            painter.setPen(QColor(0, 0, 0))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(14)
            painter.setFont(font)
            
            main_text = f"{int(self.intensity)}%"
            if self.effect:
                main_text += f" • {self.effect}"
            
            # Ombre
            painter.drawText(self.rect().adjusted(1, 1, 1, 1), Qt.AlignCenter, main_text)
            
            # Texte blanc
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(self.rect(), Qt.AlignCenter, main_text)
            
            # Vitesse effet en petit
            if self.effect:
                font.setPixelSize(9)
                painter.setFont(font)
                painter.setPen(QColor(255, 255, 0))
                painter.drawText(self.rect().adjusted(0, 20, 0, 0), 
                               Qt.AlignHCenter | Qt.AlignTop, 
                               f"⚡{self.effect_speed}%")
    
    def contextMenuEvent(self, event):
        """Menu clic droit COMPLET"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                color: white;
                border: 2px solid #4a4a4a;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 30px;
            }
            QMenu::item:selected {
                background: #4a8aaa;
            }
            QMenu::separator {
                background: #3a3a3a;
                height: 1px;
            }
        """)
        
        # === INTENSITÉ ===
        intensity_menu = menu.addMenu("📊 Intensité")
        for val in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            action = intensity_menu.addAction(f"{val}%")
            action.triggered.connect(lambda v=val: self.set_intensity(v))
        intensity_menu.addSeparator()
        custom_action = intensity_menu.addAction("✏️ Personnalisé...")
        custom_action.triggered.connect(self.edit_intensity)
        
        # === COULEUR ===
        color_menu = menu.addMenu("🎨 Couleur")
        colors = [
            ("Rouge", QColor(255, 0, 0)),
            ("Vert", QColor(0, 255, 0)),
            ("Bleu", QColor(0, 0, 255)),
            ("Jaune", QColor(255, 255, 0)),
            ("Magenta", QColor(255, 0, 255)),
            ("Cyan", QColor(0, 255, 255)),
            ("Blanc", QColor(255, 255, 255)),
        ]
        for name, col in colors:
            action = color_menu.addAction(f"■ {name}")
            action.triggered.connect(lambda c=col: self.set_color(c))
        
        color_menu.addSeparator()
        bicolor_action = color_menu.addAction("🎨 Bicolore...")
        bicolor_action.triggered.connect(self.set_bicolor)
        
        # === EFFETS ===
        menu.addSeparator()
        effects_menu = menu.addMenu("✨ Effets")
        
        no_effect = effects_menu.addAction("⭕ Aucun")
        no_effect.triggered.connect(lambda: self.set_effect(None))
        
        effects_menu.addSeparator()
        
        effect_list = ["Strobe", "Flash", "Pulse", "Wave", "Random"]
        for eff in effect_list:
            action = effects_menu.addAction(f"⚡ {eff}")
            action.triggered.connect(lambda e=eff: self.set_effect(e))
        
        if self.effect:
            effects_menu.addSeparator()
            speed_action = effects_menu.addAction(f"⚡ Vitesse ({self.effect_speed}%)...")
            speed_action.triggered.connect(self.edit_effect_speed)
        
        # === FADES ===
        menu.addSeparator()
        fade_in_action = menu.addAction("🎬 Fade In...")
        fade_in_action.triggered.connect(self.add_fade_in)
        
        fade_out_action = menu.addAction("🎬 Fade Out...")
        fade_out_action.triggered.connect(self.add_fade_out)
        
        # Transition
        next_clip = self.find_adjacent_clip('right')
        if next_clip:
            trans_action = menu.addAction("✨ Transition vers suivant...")
            trans_action.triggered.connect(lambda: self.add_transition(next_clip))
        
        if self.fade_in_duration > 0 or self.fade_out_duration > 0:
            clear_fades = menu.addAction("❌ Supprimer fades")
            clear_fades.triggered.connect(self.clear_fades)
        
        # === ACTIONS ===
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Supprimer")
        delete_action.triggered.connect(self.delete_clip)
        
        menu.exec(event.globalPos())
    
    def set_intensity(self, value):
        """Change l'intensité"""
        self.intensity = value
        self.update()
    
    def set_color(self, color):
        """Change la couleur (mono)"""
        self.color = color
        self.color2 = None
        self.update_visual()
    
    def set_bicolor(self):
        """Configure bicolore"""
        dialog = QDialog(self)
        dialog.setWindowTitle("🎨 Bicolore")
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel("Couleur 1:"))
        combo1 = QComboBox()
        combo1.addItem("Rouge", QColor(255, 0, 0))
        combo1.addItem("Vert", QColor(0, 255, 0))
        combo1.addItem("Bleu", QColor(0, 0, 255))
        combo1.addItem("Jaune", QColor(255, 255, 0))
        combo1.addItem("Magenta", QColor(255, 0, 255))
        combo1.addItem("Cyan", QColor(0, 255, 255))
        layout.addWidget(combo1)
        
        layout.addWidget(QLabel("Couleur 2:"))
        combo2 = QComboBox()
        combo2.addItem("Rouge", QColor(255, 0, 0))
        combo2.addItem("Vert", QColor(0, 255, 0))
        combo2.addItem("Bleu", QColor(0, 0, 255))
        combo2.addItem("Jaune", QColor(255, 255, 0))
        combo2.addItem("Magenta", QColor(255, 0, 255))
        combo2.addItem("Cyan", QColor(0, 255, 255))
        layout.addWidget(combo2)
        
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        if dialog.exec() == QDialog.Accepted:
            self.color = combo1.currentData()
            self.color2 = combo2.currentData()
            self.update_visual()
    
    def set_effect(self, effect_name):
        """Définit un effet"""
        self.effect = effect_name
        self.update()
    
    def edit_effect_speed(self):
        """Édite la vitesse d'effet"""
        from PySide6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getInt(
            self, "Vitesse effet", "Vitesse (0-100):",
            self.effect_speed, 0, 100, 1
        )
        if ok:
            self.effect_speed = value
            self.update()
    
    def edit_intensity(self):
        """Édite intensité avec dialog noir stylé"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QSlider, QPushButton, QHBoxLayout
        
        dialog = QDialog(None)
        dialog.setWindowTitle("💡 Intensité")
        dialog.setFixedSize(350, 200)
        dialog.setStyleSheet("background: #1a1a1a;")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Label valeur
        value_label = QLabel(f"{self.intensity}%")
        value_label.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)
        
        # Slider
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(self.intensity)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #2a2a2a;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff;
                width: 20px;
                height: 20px;
                border-radius: 10px;
                margin: -6px 0;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8B00FF, stop:1 #FF00FF);
                border-radius: 4px;
            }
        """)
        slider.valueChanged.connect(lambda v: value_label.setText(f"{v}%"))
        layout.addWidget(slider)
        
        # Boutons
        btn_layout = QHBoxLayout()
        
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(dialog.reject)
        cancel.setFixedHeight(40)
        cancel.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 20px;
            }
            QPushButton:hover { background: #4a4a4a; }
        """)
        btn_layout.addWidget(cancel)
        
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(dialog.accept)
        ok.setFixedHeight(40)
        ok.setStyleSheet("""
            QPushButton {
                background: #00d4ff;
                color: black;
                border: none;
                border-radius: 6px;
                padding: 0 30px;
                font-weight: bold;
            }
            QPushButton:hover { background: #00e4ff; }
        """)
        btn_layout.addWidget(ok)
        
        layout.addLayout(btn_layout)
        
        if dialog.exec() == QDialog.Accepted:
            self.set_intensity(slider.value())
            # Forcer update de la piste
            if hasattr(self, 'parent_track'):
                self.parent_track.update()
    
    def add_fade_in(self):
        from PySide6.QtWidgets import QInputDialog
        duration_s, ok = QInputDialog.getDouble(
            self, "Fade In", "Durée (secondes):",
            1.0, 0.1, 10.0, 1
        )
        if ok:
            self.fade_in_duration = int(duration_s * 1000)
            self.update()
    
    def add_fade_out(self):
        from PySide6.QtWidgets import QInputDialog
        duration_s, ok = QInputDialog.getDouble(
            self, "Fade Out", "Durée (secondes):",
            1.0, 0.1, 10.0, 1
        )
        if ok:
            self.fade_out_duration = int(duration_s * 1000)
            self.update()
    
    def add_transition(self, next_clip):
        gap = next_clip.start_time - (self.start_time + self.duration)
        if gap <= 100:
            from PySide6.QtWidgets import QInputDialog
            duration_s, ok = QInputDialog.getDouble(
                self, "Transition", "Durée (secondes):",
                1.0, 0.1, 5.0, 1
            )
            if ok:
                trans_ms = int(duration_s * 1000)
                self.fade_out_duration = trans_ms
                next_clip.fade_in_duration = trans_ms
                self.update()
                next_clip.update()
        else:
            QMessageBox.warning(self, "Impossible",
                "Les clips doivent se toucher")
    
    def find_adjacent_clip(self, direction):
        for clip in self.parent_track.clips:
            if clip == self:
                continue
            if direction == 'right':
                if abs(clip.start_time - (self.start_time + self.duration)) < 100:
                    return clip
        return None
    
    def clear_fades(self):
        self.fade_in_duration = 0
        self.fade_out_duration = 0
        self.update()
    
    def delete_clip(self):
        reply = QMessageBox.question(
            self, "Supprimer", "Supprimer ce clip ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.parent_track.clips.remove(self)
            self.deleteLater()
    
    def mousePressEvent(self, event):
        x = event.position().x()
        if x < 5:
            self.resizing = 'left'
        elif x > self.width() - 5:
            self.resizing = 'right'
        else:
            self.dragging = True
            self.drag_start_x = event.globalPosition().x()
            self.drag_start_time = self.start_time
    
    def mouseMoveEvent(self, event):
        x = event.position().x()
        
        if x < 5 or x > self.width() - 5:
            self.setCursor(QCursor(Qt.SizeHorCursor))
        else:
            self.setCursor(QCursor(Qt.OpenHandCursor))
        
        if self.dragging:
            delta_x = event.globalPosition().x() - self.drag_start_x
            delta_time = (delta_x / self.parent_track.pixels_per_ms)
            new_start = max(0, self.drag_start_time + delta_time)
            
            if new_start + self.duration <= self.parent_track.total_duration:
                self.start_time = new_start
                self.parent_track.update_clips()
        
        elif self.resizing == 'left':
            delta_x = event.globalPosition().x() - self.x()
            delta_time = delta_x / self.parent_track.pixels_per_ms
            new_start = max(0, self.start_time + delta_time)
            new_duration = self.duration - delta_time
            
            if new_duration >= 100:
                self.start_time = new_start
                self.duration = new_duration
                self.parent_track.update_clips()
        
        elif self.resizing == 'right':
            delta_x = event.globalPosition().x() - (self.x() + self.width())
            delta_time = delta_x / self.parent_track.pixels_per_ms
            new_duration = self.duration + delta_time
            
            if new_duration >= 100 and self.start_time + new_duration <= self.parent_track.total_duration:
                self.duration = new_duration
                self.parent_track.update_clips()
    
    def mouseReleaseEvent(self, event):
        self.dragging = False
        self.resizing = None
        self.setCursor(QCursor(Qt.ArrowCursor))
    
    def mouseDoubleClickEvent(self, event):
        self.edit_intensity()
    """Un clip de lumière sur la timeline (bloc coloré redimensionnable avec fades)"""
    def __init__(self, start_time, duration, color, intensity, parent_track):
        super().__init__()
        self.start_time = start_time  # ms
        self.duration = duration  # ms
        self.color = color  # QColor
        self.intensity = intensity  # 0-100
        self.parent_track = parent_track
        self.dragging = False
        self.resizing = None  # 'left', 'right', None
        
        # Fades
        self.fade_in_duration = 0  # ms
        self.fade_out_duration = 0  # ms
        
        self.setMouseTracking(True)
        self.setMinimumHeight(40)
        self.update_style()
    
    def update_style(self):
        """Met à jour l'apparence du clip - couleur SOLIDE"""
        # Couleur solide du clip
        self.setStyleSheet(f"""
            QWidget {{
                background: {self.color.name()};
                border: 2px solid {self.color.darker(120).name()};
                border-radius: 4px;
            }}
        """)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Dessiner les fades (triangles translucides)
        if self.fade_in_duration > 0:
            # Fade in = triangle noir gauche
            fade_in_pixels = int(self.fade_in_duration * self.parent_track.pixels_per_ms)
            fade_in_pixels = min(fade_in_pixels, self.width() // 2)
            
            painter.setBrush(QColor(0, 0, 0, 120))
            painter.setPen(Qt.NoPen)
            triangle = QPolygon([
                QPoint(2, 2),
                QPoint(fade_in_pixels, 2),
                QPoint(2, self.height() - 2)
            ])
            painter.drawPolygon(triangle)
        
        if self.fade_out_duration > 0:
            # Fade out = triangle noir droit
            fade_out_pixels = int(self.fade_out_duration * self.parent_track.pixels_per_ms)
            fade_out_pixels = min(fade_out_pixels, self.width() // 2)
            
            painter.setBrush(QColor(0, 0, 0, 120))
            painter.setPen(Qt.NoPen)
            triangle = QPolygon([
                QPoint(self.width() - fade_out_pixels, 2),
                QPoint(self.width() - 2, 2),
                QPoint(self.width() - 2, self.height() - 2)
            ])
            painter.drawPolygon(triangle)
        
        # Texte intensité au centre (GROS et VISIBLE)
        if self.width() > 30:
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(16)
            painter.setFont(font)
            
            # Ombre pour lisibilité
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(self.rect().adjusted(1, 1, 1, 1), 
                           Qt.AlignCenter, f"{int(self.intensity)}%")
            
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(self.rect(), Qt.AlignCenter, f"{int(self.intensity)}%")
    
    def contextMenuEvent(self, event):
        """Menu clic droit pour fades et transitions"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #2a2a2a;
                color: white;
                border: 1px solid #4a4a4a;
            }
            QMenu::item:selected {
                background: #4a8aaa;
            }
        """)
        
        # Fade In
        fade_in_action = menu.addAction("🎬 Fade In")
        fade_in_action.triggered.connect(self.add_fade_in)
        
        # Fade Out
        fade_out_action = menu.addAction("🎬 Fade Out")
        fade_out_action.triggered.connect(self.add_fade_out)
        
        menu.addSeparator()
        
        # Transition vers clip suivant
        next_clip = self.find_adjacent_clip('right')
        if next_clip:
            transition_action = menu.addAction("✨ Transition vers suivant")
            transition_action.triggered.connect(lambda: self.add_transition(next_clip))
        
        menu.addSeparator()
        
        # Supprimer fades
        if self.fade_in_duration > 0 or self.fade_out_duration > 0:
            clear_action = menu.addAction("❌ Supprimer fades")
            clear_action.triggered.connect(self.clear_fades)
        
        # Éditer intensité
        edit_action = menu.addAction("📊 Éditer intensité")
        edit_action.triggered.connect(self.edit_intensity)
        
        # Supprimer clip
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Supprimer clip")
        delete_action.triggered.connect(self.delete_clip)
        
        menu.exec(event.globalPos())
    
    def add_fade_in(self):
        """Ajoute un fade in"""
        from PySide6.QtWidgets import QInputDialog
        duration_s, ok = QInputDialog.getDouble(
            self, "Fade In", "Durée du fade (secondes):",
            1.0, 0.1, 10.0, 1
        )
        if ok:
            self.fade_in_duration = int(duration_s * 1000)
            self.update()
    
    def add_fade_out(self):
        """Ajoute un fade out"""
        from PySide6.QtWidgets import QInputDialog
        duration_s, ok = QInputDialog.getDouble(
            self, "Fade Out", "Durée du fade (secondes):",
            1.0, 0.1, 10.0, 1
        )
        if ok:
            self.fade_out_duration = int(duration_s * 1000)
            self.update()
    
    def add_transition(self, next_clip):
        """Ajoute une transition crossfade vers le clip suivant"""
        # Calculer durée overlap possible
        gap = next_clip.start_time - (self.start_time + self.duration)
        
        if gap < 0:
            # Clips se chevauchent déjà
            overlap = -gap
            from PySide6.QtWidgets import QInputDialog
            duration_s, ok = QInputDialog.getDouble(
                self, "Transition", "Durée de la transition (secondes):",
                min(2.0, overlap / 1000), 0.1, overlap / 1000, 1
            )
            if ok:
                transition_ms = int(duration_s * 1000)
                self.fade_out_duration = transition_ms
                next_clip.fade_in_duration = transition_ms
                self.update()
                next_clip.update()
        else:
            QMessageBox.warning(self, "Impossible",
                "Les clips doivent se toucher pour créer une transition")
    
    def find_adjacent_clip(self, direction):
        """Trouve le clip adjacent (gauche ou droite)"""
        for clip in self.parent_track.clips:
            if clip == self:
                continue
            
            if direction == 'right':
                # Clip juste après
                if abs(clip.start_time - (self.start_time + self.duration)) < 100:
                    return clip
            elif direction == 'left':
                # Clip juste avant
                if abs((clip.start_time + clip.duration) - self.start_time) < 100:
                    return clip
        return None
    
    def clear_fades(self):
        """Supprime tous les fades"""
        self.fade_in_duration = 0
        self.fade_out_duration = 0
        self.update()
    
    def edit_intensity(self):
        """Édite l'intensité"""
        from PySide6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getInt(
            self, "Intensité", "Intensité (0-100):", 
            self.intensity, 0, 100, 1
        )
        if ok:
            self.intensity = value
            self.update()
    
    def delete_clip(self):
        """Supprime le clip"""
        reply = QMessageBox.question(
            self, "Supprimer", "Supprimer ce clip ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.parent_track.clips.remove(self)
            self.deleteLater()
    
    def mousePressEvent(self, event):
        x = event.position().x()
        if x < 5:
            self.resizing = 'left'
        elif x > self.width() - 5:
            self.resizing = 'right'
        else:
            self.dragging = True
            self.drag_start_x = event.globalPosition().x()
            self.drag_start_time = self.start_time
    
    def mouseMoveEvent(self, event):
        x = event.position().x()
        
        if x < 5 or x > self.width() - 5:
            self.setCursor(QCursor(Qt.SizeHorCursor))
        else:
            self.setCursor(QCursor(Qt.OpenHandCursor))
        
        if self.dragging:
            delta_x = event.globalPosition().x() - self.drag_start_x
            delta_time = (delta_x / self.parent_track.pixels_per_ms)
            new_start = max(0, self.drag_start_time + delta_time)
            
            if new_start + self.duration <= self.parent_track.total_duration:
                self.start_time = new_start
                self.parent_track.update_clips()
        
        elif self.resizing == 'left':
            delta_x = event.globalPosition().x() - self.x()
            delta_time = delta_x / self.parent_track.pixels_per_ms
            new_start = max(0, self.start_time + delta_time)
            new_duration = self.duration - delta_time
            
            if new_duration >= 100:
                self.start_time = new_start
                self.duration = new_duration
                self.parent_track.update_clips()
        
        elif self.resizing == 'right':
            delta_x = event.globalPosition().x() - (self.x() + self.width())
            delta_time = delta_x / self.parent_track.pixels_per_ms
            new_duration = self.duration + delta_time
            
            if new_duration >= 100 and self.start_time + new_duration <= self.parent_track.total_duration:
                self.duration = new_duration
                self.parent_track.update_clips()
    
    def mouseReleaseEvent(self, event):
        self.dragging = False
        self.resizing = None
        self.setCursor(QCursor(Qt.ArrowCursor))
    
    def mouseDoubleClickEvent(self, event):
        """Double-clic pour éditer intensité"""
        self.edit_intensity()


class PlanDeFeuPreview(QWidget):
    """Prévisualisation du plan de feu sous la timeline"""
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setFixedHeight(120)
        self.setStyleSheet("background: #0a0a0a; border-top: 2px solid #3a3a3a;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Titre
        title = QLabel("🎭 Plan de Feu - Prévisualisation")
        title.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Grille des projecteurs
        grid = QGridLayout()
        grid.setSpacing(5)
        
        # Récupérer les projectors depuis le plan de feu du main_window
        self.projector_widgets = {}
        
        # Face
        face_label = QLabel("Face:")
        face_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(face_label, 0, 0)
        self.face_widget = QLabel("◯")
        self.face_widget.setFixedSize(40, 40)
        self.face_widget.setAlignment(Qt.AlignCenter)
        self.face_widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
        grid.addWidget(self.face_widget, 0, 1)
        
        # Douches
        for i in range(3):
            douche_label = QLabel(f"Douche {i+1}:")
            douche_label.setStyleSheet("color: #888; font-size: 11px;")
            grid.addWidget(douche_label, 0, 2 + i*2)
            widget = QLabel("◯")
            widget.setFixedSize(40, 40)
            widget.setAlignment(Qt.AlignCenter)
            widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
            grid.addWidget(widget, 0, 3 + i*2)
            self.projector_widgets[f'douche{i+1}'] = widget
        
        # Contres
        contres_label = QLabel("Contres:")
        contres_label.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(contres_label, 0, 8)
        self.contres_widget = QLabel("◯")
        self.contres_widget.setFixedSize(40, 40)
        self.contres_widget.setAlignment(Qt.AlignCenter)
        self.contres_widget.setStyleSheet("background: #1a1a1a; border-radius: 20px; font-size: 20px;")
        grid.addWidget(self.contres_widget, 0, 9)
        
        layout.addLayout(grid)
        
        # Timer pour update
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_preview)
        self.update_timer.start(50)  # 20 FPS
    
    def update_preview(self):
        """Met à jour la prévisualisation depuis les projecteurs du main_window"""
        if not self.main_window or not hasattr(self.main_window, 'projectors'):
            return
        
        # Parcourir les projecteurs et mettre à jour les widgets
        for proj in self.main_window.projectors:
            widget = None
            
            # Trouver le bon widget selon le groupe
            if proj.group == "face":
                widget = self.face_widget
            elif proj.group == "contre":
                # Les contres sont dans projector_widgets mais pas face
                pass  
            elif proj.group == "douche":
                widget = self.projector_widgets.get(f'douche{proj.index + 1}')
            
            if widget and proj.level > 0:
                # Afficher la couleur avec intensité
                color = proj.color
                widget.setStyleSheet(f"""
                    background: {color.name()};
                    border-radius: 20px;
                    font-size: 20px;
                """)
            elif widget:
                # Éteint
                widget.setStyleSheet("""
                    background: #1a1a1a;
                    border-radius: 20px;
                    font-size: 20px;
                """)


class ColorPalette(QWidget):
    """Palette de couleurs draggable avec VRAIES couleurs"""
    def __init__(self, parent_editor):
        super().__init__()
        self.parent_editor = parent_editor
        self.setFixedHeight(70)
        self.setStyleSheet("background: #1a1a1a; border-top: 2px solid #3a3a3a;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)
        
        # Couleurs disponibles - Vert plus doux
        self.colors = [
            ("Rouge", QColor(255, 0, 0)),
            ("Vert", QColor(0, 200, 0)),  # Vert moins agressif
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
            # Couleur SOLIDE sans transparence
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
            
            # Rendre draggable
            btn.mousePressEvent = lambda e, c=color: self.start_drag(e, c)
            
            layout.addWidget(btn)
        
        layout.addSpacing(20)
        
        # === DOUBLES COULEURS (AKAI style) ===
        # Combinaisons bicolores harmonieuses
        self.bicolors = [
            ("R+V", QColor(255, 0, 0), QColor(0, 200, 0)),      # Rouge + Vert doux
            ("R+O", QColor(255, 0, 0), QColor(255, 128, 0)),    # Rouge + Orange
            ("R+Rose", QColor(255, 0, 0), QColor(255, 105, 180)), # Rouge + Rose
            ("B+C", QColor(0, 0, 255), QColor(0, 255, 255)),    # Bleu + Cyan
            ("V+J", QColor(0, 200, 0), QColor(255, 255, 0)),    # Vert + Jaune
            ("B+V", QColor(0, 0, 255), QColor(128, 0, 255)),    # Bleu + Violet
            ("O+J", QColor(255, 128, 0), QColor(255, 255, 0)),  # Orange + Jaune
            ("C+V", QColor(0, 255, 255), QColor(128, 0, 255)),  # Cyan + Violet
        ]
        
        for name, col1, col2 in self.bicolors:
            btn = QPushButton("")
            btn.setFixedSize(50, 50)
            
            # Créer pixmap avec 2 couleurs côte à côte ARRONDI
            from PySide6.QtGui import QPainterPath
            pixmap = QPixmap(50, 50)
            pixmap.fill(Qt.transparent)
            painter_btn = QPainter(pixmap)
            painter_btn.setRenderHint(QPainter.Antialiasing)
            
            # Path arrondi
            path = QPainterPath()
            path.addRoundedRect(0, 0, 50, 50, 8, 8)
            painter_btn.setClipPath(path)
            
            # 2 couleurs
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
            
            # Rendre draggable avec 2 couleurs
            btn.mousePressEvent = lambda e, c1=col1, c2=col2: self.start_bicolor_drag(e, c1, c2)
            
            layout.addWidget(btn)
        
        layout.addStretch()
    
    def start_drag(self, event, color):
        """Démarre un drag&drop de couleur"""
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDrag
        
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(color.name())
        drag.setMimeData(mime_data)
        
        # Créer un pixmap COLORÉ pour visualiser le drag
        pixmap = QPixmap(50, 50)
        pixmap.fill(color)
        drag.setPixmap(pixmap)
        
        drag.exec(Qt.CopyAction)
    
    def start_bicolor_drag(self, event, color1, color2):
        """Démarre un drag&drop de bicolore"""
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDrag
        
        drag = QDrag(self)
        mime_data = QMimeData()
        # Format : "color1#color2"
        mime_data.setText(f"{color1.name()}#{color2.name()}")
        drag.setMimeData(mime_data)
        
        # Créer un pixmap bicolore
        pixmap = QPixmap(50, 50)
        painter = QPainter(pixmap)
        painter.fillRect(0, 0, 25, 50, color1)
        painter.fillRect(25, 0, 25, 50, color2)
        painter.end()
        drag.setPixmap(pixmap)
        
        drag.exec(Qt.CopyAction)


class LightTrack(QWidget):
    """Une piste de lumière (une ligne dans la timeline)"""
    def __init__(self, name, total_duration, parent_editor):
        super().__init__()
        self.name = name
        self.total_duration = total_duration  # ms
        self.parent_editor = parent_editor
        self.clips = []
        self.pixels_per_ms = 0.05  # Zoom par défaut
        
        self.setMinimumHeight(60)
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
        self.resizing_clip = None
        self.resize_edge = None
        self.selected_clips = []  # Sélection multiple
        
        # Variables pour sélection rectangulaire (rubber band)
        self.rubber_band_start = None
        self.rubber_band_rect = None
        
        # Forme d'onde audio
        self.waveform_data = None  # Sera généré à la demande
        
        self.setMouseTracking(True)
    
    def generate_waveform(self, audio_path, max_samples=1000):
        """Génère des données de forme d'onde à partir d'un fichier audio (WAV ou MP3)"""
        print(f"🎵 Génération forme d'onde: {audio_path}")
        
        # D'abord essayer WAV directement
        try:
            with wave.open(audio_path, 'rb') as wav_file:
                n_channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                n_frames = wav_file.getnframes()
                
                print(f"   WAV détecté: {n_channels}ch, {sampwidth*8}bit, {framerate}Hz")
                
                # Lire les données
                frames = wav_file.readframes(n_frames)
                
                # Convertir en array
                if sampwidth == 1:
                    dtype = 'B'  # unsigned char
                    audio_data = array.array(dtype, frames)
                    audio_data = [x - 128 for x in audio_data]  # Centrer autour de 0
                elif sampwidth == 2:
                    dtype = 'h'  # signed short
                    audio_data = array.array(dtype, frames)
                else:
                    print(f"⚠️ Sample width {sampwidth} non supporté")
                    return None
                
                # Si stéréo, prendre la moyenne des deux canaux
                if n_channels == 2:
                    audio_data = [abs(audio_data[i] + audio_data[i+1]) // 2 for i in range(0, len(audio_data), 2)]
                else:
                    audio_data = [abs(x) for x in audio_data]
                
                # Downsampler pour avoir max_samples points
                step = max(1, len(audio_data) // max_samples)
                waveform = []
                for i in range(0, len(audio_data), step):
                    chunk = audio_data[i:i+step]
                    if chunk:
                        waveform.append(max(chunk))
                
                # Normaliser entre 0 et 1
                if waveform:
                    max_val = max(waveform)
                    if max_val > 0:
                        waveform = [x / max_val for x in waveform]
                
                print(f"✅ Forme d'onde générée: {len(waveform)} points")
                return waveform
                
        except wave.Error:
            print(f"   ⚠️ Pas un fichier WAV, génération d'une forme d'onde factice")
            # Pour MP3 ou autres formats, générer une forme d'onde aléatoire simple
            # (une vraie extraction MP3→WAV nécessiterait ffmpeg ou pydub)
            import random
            waveform = [random.random() * 0.7 for _ in range(max_samples)]
            print(f"✅ Forme d'onde factice générée: {len(waveform)} points")
            return waveform
            
        except Exception as e:
            print(f"❌ Erreur génération forme d'onde: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
    
    def mousePressEvent(self, event):
        """Gère clic souris pour drag/resize/fade/menu + SÉLECTION MULTIPLE + RUBBER BAND + CUT MODE"""
        # === MODE CUT ACTIVÉ ===
        if hasattr(self.parent_editor, 'cut_mode') and self.parent_editor.cut_mode:
            result = self.get_clip_at_pos(event.position().x(), event.position().y())
            if result:
                clip, clip_x, clip_width = result
                # Couper le clip au milieu
                self.cut_clip_in_two(clip)
                # Désactiver le mode CUT
                self.parent_editor.cut_mode = False
                self.parent_editor.cut_btn.setChecked(False)
                self.parent_editor.setCursor(Qt.ArrowCursor)
            return
        
        result = self.get_clip_at_pos(event.position().x(), event.position().y())
        
        if result:
            clip, clip_x, clip_width = result
            x = event.position().x()
            y = event.position().y()
            
            # === GESTION SÉLECTION MULTIPLE ===
            modifiers = event.modifiers()
            
            if modifiers & Qt.ControlModifier:
                # Ctrl+clic : Ajouter/retirer de la sélection
                if clip in self.selected_clips:
                    self.selected_clips.remove(clip)
                else:
                    self.selected_clips.append(clip)
                self.update()
                return
            elif modifiers & Qt.ShiftModifier:
                # Shift+clic : Sélectionner range
                if self.selected_clips:
                    # Sélectionner tous les clips entre le dernier sélectionné et celui-ci
                    last_selected = self.selected_clips[-1]
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
                # Clic simple : sélectionner UNIQUEMENT si pas déjà sélectionné
                if clip not in self.selected_clips:
                    self.selected_clips = [clip]
                # Sinon garder la sélection actuelle pour drag multiple
            
            # Calculer positions des fades
            fade_in_px = int(clip.fade_in_duration * self.pixels_per_ms) if clip.fade_in_duration > 0 else 0
            fade_out_px = int(clip.fade_out_duration * self.pixels_per_ms) if clip.fade_out_duration > 0 else 0
            
            # Détecter clic sur fade in (triangle gauche)
            if fade_in_px > 0 and x < clip_x + fade_in_px and y >= 10 and y <= 50:
                self.resizing_clip = clip
                self.resize_edge = 'fade_in'
                self.saved_positions = {clip: (clip.start_time, clip.duration)}
            # Détecter clic sur fade out (triangle droit)
            elif fade_out_px > 0 and x > clip_x + clip_width - fade_out_px and y >= 10 and y <= 50:
                self.resizing_clip = clip
                self.resize_edge = 'fade_out'
                self.saved_positions = {clip: (clip.start_time, clip.duration)}
            # Détecter resize clip (5px des bords)
            elif x < clip_x + 5:
                self.resizing_clip = clip
                self.resize_edge = 'left'
                self.saved_positions = {clip: (clip.start_time, clip.duration)}
            elif x > clip_x + clip_width - 5:
                self.resizing_clip = clip
                self.resize_edge = 'right'
                self.saved_positions = {clip: (clip.start_time, clip.duration)}
            else:
                # Drag (de tous les clips sélectionnés si multiple)
                self.dragging_clip = clip
                self.drag_offset = x - clip_x
                
                # Sauvegarder positions AVANT drag pour undo collision
                clips_to_save = self.selected_clips if len(self.selected_clips) > 1 else [clip]
                self.saved_positions = {c: (c.start_time, c.duration) for c in clips_to_save}
        else:
            # Clic dans le vide : démarrer rubber band selection
            if event.position().x() > 145:  # Uniquement dans la zone timeline
                self.rubber_band_start = event.position().toPoint()
                self.rubber_band_rect = None
                self.selected_clips = []
                print(f"🔲 RUBBER BAND START at {self.rubber_band_start.x()}, {self.rubber_band_start.y()}")
                self.update()
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Gère drag et resize + RUBBER BAND"""
        x = event.position().x()
        
        # Gestion rubber band selection
        if self.rubber_band_start:
            from PySide6.QtCore import QRect
            self.rubber_band_rect = QRect(self.rubber_band_start, event.position().toPoint()).normalized()
            
            print(f"🔲 RUBBER BAND: {self.rubber_band_rect.x()},{self.rubber_band_rect.y()} → {self.rubber_band_rect.width()}x{self.rubber_band_rect.height()}")
            
            # Sélectionner les clips dans le rectangle
            self.selected_clips = []
            for clip in self.clips:
                clip_x = 145 + int(clip.start_time * self.pixels_per_ms)
                clip_width = int(clip.duration * self.pixels_per_ms)
                clip_rect = QRect(clip_x, 10, clip_width, 40)
                
                if self.rubber_band_rect.intersects(clip_rect):
                    self.selected_clips.append(clip)
                    print(f"   ✓ Clip sélectionné: {clip.start_time:.1f}s")
            
            print(f"   Total: {len(self.selected_clips)} clip(s) dans le rectangle")
            self.update()
            return
        
        if self.dragging_clip:
            # Drag du clip - AVEC SÉLECTION MULTIPLE + CHANGEMENT DE PISTE
            new_x = max(145, x - self.drag_offset)
            new_start = (new_x - 145) / self.pixels_per_ms
            
            # Calculer le delta de déplacement
            delta = new_start - self.dragging_clip.start_time
            
            # === DRAG ENTRE PISTES DÉSACTIVÉ ===
            # Le code de changement de piste a été désactivé pour éviter les accidents
            # Les clips restent sur leur piste d'origine
            
            # Si pas de changement de piste, comportement normal
            clips_to_move = self.selected_clips if len(self.selected_clips) > 1 else [self.dragging_clip]
            
            # Vérifier collision pour tous les clips AVEC LOGS (TOUT EN MS)
            can_move = True
            for moving_clip in clips_to_move:
                new_clip_start = moving_clip.start_time + delta
                new_clip_end = new_clip_start + moving_clip.duration
                
                # Vérifier collision avec clips NON sélectionnés
                for clip in self.clips:
                    if clip in clips_to_move:
                        continue
                    
                    clip_end = clip.start_time + clip.duration
                    
                    # COLLISION = chevauchement avec marge de sécurité (10ms)
                    overlap = (new_clip_start < clip_end - 10) and (new_clip_end > clip.start_time + 10)
                    if overlap:
                        can_move = False
                        print(f"❌ COLLISION DRAG: clip {new_clip_start:.0f}-{new_clip_end:.0f}ms VS {clip.start_time:.0f}-{clip_end:.0f}ms")
                        break
                
                if not can_move:
                    break
            
            # Déplacer tous les clips sélectionnés
            if can_move:
                for moving_clip in clips_to_move:
                    moving_clip.start_time = max(0, moving_clip.start_time + delta)
            
            self.update()
        
        elif self.resizing_clip:
            clip_x = 145 + int(self.resizing_clip.start_time * self.pixels_per_ms)
            
            if self.resize_edge == 'fade_in':
                # Resize fade in
                new_fade = max(0, (x - clip_x) / self.pixels_per_ms)
                self.resizing_clip.fade_in_duration = min(new_fade, self.resizing_clip.duration / 2)
            
            elif self.resize_edge == 'fade_out':
                # Resize fade out
                clip_end = clip_x + int(self.resizing_clip.duration * self.pixels_per_ms)
                new_fade = max(0, (clip_end - x) / self.pixels_per_ms)
                self.resizing_clip.fade_out_duration = min(new_fade, self.resizing_clip.duration / 2)
            
            elif self.resize_edge == 'left':
                # Resize clip début AVEC anti-collision + LOGS
                # IMPORTANT: start_time est en MS, duration est en MS
                new_start_ms = max(0, (x - 145) / self.pixels_per_ms)
                old_end_ms = self.resizing_clip.start_time + self.resizing_clip.duration
                
                print(f"🔧 RESIZE LEFT: x={x:.0f}, new_start_ms={new_start_ms:.0f}ms, old_end={old_end_ms:.0f}ms")
                
                # Vérifier collision avec clip précédent
                for clip in self.clips:
                    if clip == self.resizing_clip:
                        continue
                    if clip.start_time < self.resizing_clip.start_time:
                        clip_end_ms = clip.start_time + clip.duration
                        if new_start_ms < clip_end_ms:
                            # Limiter au bord du clip précédent
                            new_start_ms = clip_end_ms
                            print(f"   ⚠️ Collision avec clip précédent, limité à {new_start_ms:.0f}ms")
                
                if new_start_ms < old_end_ms - 500:  # Min 500ms
                    self.resizing_clip.start_time = new_start_ms
                    self.resizing_clip.duration = old_end_ms - new_start_ms
                    print(f"   ✅ Nouveau: start={new_start_ms:.0f}ms, duration={self.resizing_clip.duration:.0f}ms")
            
            else:  # right
                # Resize clip fin AVEC anti-collision
                new_duration_sec = (x - clip_x) / self.pixels_per_ms / 1000
                new_end = self.resizing_clip.start_time + new_duration_sec
                
                # Vérifier collision avec clip suivant
                can_resize = True
                for clip in self.clips:
                    if clip == self.resizing_clip:
                        continue
                    if clip.start_time > self.resizing_clip.start_time:
                        # Clip suivant détecté
                        if new_end > clip.start_time:
                            # Collision ! Limiter au bord du clip suivant
                            new_duration_sec = clip.start_time - self.resizing_clip.start_time
                            break
                
                self.resizing_clip.duration = max(500, new_duration_sec * 1000)
            
            self.update()
        
        else:
            # Changer curseur selon position
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
        """Fin drag/resize - VÉRIFIER COLLISION FINALE + FIN RUBBER BAND"""
        # Terminer rubber band
        if self.rubber_band_start:
            print(f"🔲 RUBBER BAND END - {len(self.selected_clips)} clip(s) sélectionné(s)")
            self.rubber_band_start = None
            self.rubber_band_rect = None
            self.update()
            return
        
        if self.dragging_clip or self.resizing_clip:
            # Vérifier collision finale AVEC MARGE (TOUT EN MS)
            has_collision = False
            collision_margin = 10  # 10ms de marge
            
            for i, clip1 in enumerate(self.clips):
                for j, clip2 in enumerate(self.clips):
                    if i >= j:
                        continue
                    
                    clip1_end = clip1.start_time + clip1.duration
                    clip2_end = clip2.start_time + clip2.duration
                    
                    # Chevauchement détecté AVEC MARGE
                    overlap = (clip1.start_time < clip2_end - collision_margin) and (clip1_end > clip2.start_time + collision_margin)
                    if overlap:
                        has_collision = True
                        print(f"⚠️ COLLISION FINALE: {clip1.start_time:.0f}-{clip1_end:.0f}ms VS {clip2.start_time:.0f}-{clip2_end:.0f}ms")
                        break
                
                if has_collision:
                    break
            
            if has_collision:
                print("❌ COLLISION DÉTECTÉE - RESTAURATION")
                # Restaurer positions sauvegardées
                if hasattr(self, 'saved_positions'):
                    for clip, (start, dur) in self.saved_positions.items():
                        clip.start_time = start
                        clip.duration = dur
                        print(f"   ↶ Restauré: start={start:.0f}ms, dur={dur:.0f}ms")
                    self.update()
                    del self.saved_positions
                else:
                    print("   ⚠️ Pas de saved_positions disponible!")
        
        self.dragging_clip = None
        self.resizing_clip = None
        self.resize_edge = None
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)
    
    def contextMenuEvent(self, event):
        """Menu contextuel sur clip OU zone vide"""
        result = self.get_clip_at_pos(event.pos().x(), event.pos().y())
        
        if result:
            clip, _, _ = result
            self.show_clip_menu(clip, event.globalPos())
        else:
            # Zone vide - Menu création
            self.show_empty_menu(event.pos(), event.globalPos())
        
        super().contextMenuEvent(event)
    
    def show_empty_menu(self, local_pos, global_pos):
        """Menu sur zone vide - UNIQUEMENT Combler vide"""
        print(f"📋 MENU VIDE: pos={local_pos.x()},{local_pos.y()}")
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                color: white;
                border: 2px solid #4a4a4a;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 30px;
            }
            QMenu::item:selected {
                background: #4a8aaa;
            }
        """)
        
        # Toutes les couleurs
        colors = [
            ("Rouge", QColor(255, 0, 0)),
            ("Vert", QColor(0, 255, 0)),
            ("Bleu", QColor(0, 0, 255)),
            ("Jaune", QColor(200, 200, 0)),
            ("Magenta", QColor(255, 0, 255)),
            ("Cyan", QColor(0, 255, 255)),
            ("Blanc", QColor(255, 255, 255)),
            ("Orange", QColor(255, 128, 0)),
            ("Rose", QColor(255, 105, 180)),
            ("Violet", QColor(138, 43, 226)),
        ]
        
        # Bicolores
        bicolors = [
            ("Rouge/Bleu", QColor(255, 0, 0), QColor(0, 0, 255)),
            ("Vert/Magenta", QColor(0, 255, 0), QColor(255, 0, 255)),
            ("Jaune/Cyan", QColor(200, 200, 0), QColor(0, 255, 255)),
            ("Rouge/Blanc", QColor(255, 0, 0), QColor(255, 255, 255)),
            ("Bleu/Blanc", QColor(0, 0, 255), QColor(255, 255, 255)),
            ("Orange/Violet", QColor(255, 128, 0), QColor(138, 43, 226)),
            ("Rose/Cyan", QColor(255, 105, 180), QColor(0, 255, 255)),
            ("Vert/Rouge", QColor(0, 255, 0), QColor(255, 0, 0)),
            ("Magenta/Jaune", QColor(255, 0, 255), QColor(255, 255, 0)),
            ("Blanc/Rouge", QColor(255, 255, 255), QColor(255, 0, 0)),
        ]
        
        # === MENU UNIQUE : COMBLER VIDE ===
        fill_gap_menu = menu.addMenu("🔧 Combler vide")
        
        # Couleurs simples
        for name, col in colors:
            action = fill_gap_menu.addAction(f"■ {name}")
            action.triggered.connect(lambda checked=False, c=col, p=local_pos: self.fill_gap_at_pos(c, p))
        
        fill_gap_menu.addSeparator()
        
        # Bicolores
        for name, col1, col2 in bicolors:
            action = fill_gap_menu.addAction(f"■■ {name}")
            action.triggered.connect(lambda checked=False, c1=col1, c2=col2, p=local_pos: self.fill_gap_bicolor_at_pos(c1, c2, p))
        
        print(f"   → Menu affiché : Combler vide avec {len(colors)} couleurs et {len(bicolors)} bicolores")
        menu.exec(global_pos)
    
    def fill_remaining_space(self, color, pos):
        """Remplit l'espace restant jusqu'à la fin du média"""
        drop_x = pos.x() - 145
        start_time = max(0, drop_x / self.pixels_per_ms)
        
        # Trouver position libre
        start_time = self.find_free_position(start_time, 1000)
        
        # Durée = jusqu'à la fin du média
        duration = self.total_duration - start_time
        
        if duration > 0:
            self.add_clip(start_time, duration, color, 80)
            print(f"🎨 Remplissage: {start_time/1000:.1f}s → fin ({duration/1000:.1f}s)")
    
    def add_color_at_pos(self, color, pos):
        """Ajoute un clip de couleur à la position"""
        drop_x = pos.x() - 145
        start_time = max(0, drop_x / self.pixels_per_ms)
        start_time = self.find_free_position(start_time, 5000)
        self.add_clip(start_time, 5000, color, 80)
        print(f"🎨 Ajouté: {color.name()} à {start_time/1000:.1f}s")
    
    def add_bicolor_at_pos(self, color1, color2, pos):
        """Ajoute un clip bicolore à la position"""
        drop_x = pos.x() - 145
        start_time = max(0, drop_x / self.pixels_per_ms)
        start_time = self.find_free_position(start_time, 5000)
        clip = self.add_clip(start_time, 5000, color1, 80)
        clip.color2 = color2
        self.update()
        print(f"🎨🎨 Ajouté bicolore: {color1.name()} / {color2.name()} à {start_time/1000:.1f}s")
    
    def fill_gap_at_pos(self, color, pos):
        """Comble le vide à la position cliquée (entre deux clips)"""
        drop_x = pos.x() - 145
        click_time = max(0, drop_x / self.pixels_per_ms)
        
        # Trier clips par start_time
        sorted_clips = sorted(self.clips, key=lambda c: c.start_time)
        
        # Trouver le vide où on a cliqué
        gap_start = 0
        gap_end = self.total_duration
        
        for clip in sorted_clips:
            clip_end = clip.start_time + clip.duration
            
            if clip_end <= click_time:
                # Ce clip est avant notre position
                gap_start = clip_end
            elif clip.start_time >= click_time:
                # Ce clip est après notre position
                gap_end = clip.start_time
                break
        
        # Calculer la durée du vide
        gap_duration = gap_end - gap_start
        
        if gap_duration > 100:  # Au moins 100ms
            self.add_clip(gap_start, gap_duration, color, 80)
            print(f"🔧 Vide comblé: {gap_start/1000:.1f}s → {gap_end/1000:.1f}s ({gap_duration/1000:.1f}s)")
        else:
            print(f"⚠️ Pas de vide à combler ici")
    
    def fill_gap_bicolor_at_pos(self, color1, color2, pos):
        """Comble le vide avec un bicolore"""
        drop_x = pos.x() - 145
        click_time = max(0, drop_x / self.pixels_per_ms)
        
        # Trier clips par start_time
        sorted_clips = sorted(self.clips, key=lambda c: c.start_time)
        
        # Trouver le vide où on a cliqué
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
            clip = self.add_clip(gap_start, gap_duration, color1, 80)
            clip.color2 = color2
            self.update()
            print(f"🔧🎨 Vide comblé (bicolore): {gap_start/1000:.1f}s → {gap_end/1000:.1f}s")
        else:
            print(f"⚠️ Pas de vide à combler ici")
    
    def show_clip_menu(self, clip, global_pos):
        """Affiche le menu contextuel d'un clip"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1a1a1a;
                color: white;
                border: 2px solid #4a4a4a;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 30px;
            }
            QMenu::item:selected {
                background: #4a8aaa;
            }
            QMenu::separator {
                background: #3a3a3a;
                height: 1px;
            }
        """)
        
        # === INTENSITÉ ===
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
            # Créer icône colorée
            pixmap = QPixmap(16, 16)
            pixmap.fill(col)
            icon = QIcon(pixmap)
            
            action = color_menu.addAction(icon, name)
            action.triggered.connect(lambda checked=False, c=col, cl=clip: self.set_clip_color(cl, c))
        
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
        copy_menu = menu.addMenu("📋 Copier vers...")
        for track in self.parent_editor.tracks:
            if track != self:  # Pas la piste actuelle
                action = copy_menu.addAction(track.name)
                action.triggered.connect(lambda checked=False, cl=clip, t=track: self.copy_clip_to_track(cl, t))
        
        # === COUPER ===
        menu.addSeparator()
        cut_action = menu.addAction("✂️ Couper en 2")
        cut_action.triggered.connect(lambda: self.cut_clip_in_two(clip))
        
        # === SUPPRIMER ===
        delete_action = menu.addAction("🗑️ Supprimer")
        delete_action.triggered.connect(lambda: self.delete_clip(clip))
        
        menu.exec(global_pos)
    
    def set_clip_intensity(self, clip, value):
        clip.intensity = value
        self.update()
    
    def edit_clip_intensity(self, clip):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QSlider, QPushButton, QHBoxLayout
        
        dialog = QDialog(self)
        dialog.setWindowTitle("💡 Intensité")
        dialog.setFixedSize(350, 200)
        dialog.setStyleSheet("background: #1a1a1a;")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        value_label = QLabel(f"{clip.intensity}%")
        value_label.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)
        
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(clip.intensity)
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #2a2a2a;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff;
                width: 20px;
                height: 20px;
                border-radius: 10px;
                margin: -6px 0;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8B00FF, stop:1 #FF00FF);
                border-radius: 4px;
            }
        """)
        slider.valueChanged.connect(lambda v: value_label.setText(f"{v}%"))
        layout.addWidget(slider)
        
        btn_layout = QHBoxLayout()
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(dialog.reject)
        cancel.setFixedHeight(40)
        cancel.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 20px;
            }
            QPushButton:hover { background: #4a4a4a; }
        """)
        btn_layout.addWidget(cancel)
        
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(dialog.accept)
        ok.setFixedHeight(40)
        ok.setStyleSheet("""
            QPushButton {
                background: #00d4ff;
                color: black;
                border: none;
                border-radius: 6px;
                padding: 0 30px;
                font-weight: bold;
            }
            QPushButton:hover { background: #00e4ff; }
        """)
        btn_layout.addWidget(ok)
        layout.addLayout(btn_layout)
        
        if dialog.exec() == QDialog.Accepted:
            clip.intensity = slider.value()
            self.update()
    
    def set_clip_color(self, clip, color):
        clip.color = color
        clip.color2 = None  # Reset bicolore
        self.update()
    
    def delete_clip(self, clip):
        """Supprime le(s) clip(s) - Support sélection multiple"""
        # Supprimer tous les clips sélectionnés si multiple
        clips_to_delete = self.selected_clips if len(self.selected_clips) > 1 else [clip]
        
        for c in clips_to_delete:
            if c in self.clips:
                self.clips.remove(c)
        
        self.selected_clips.clear()
        self.update()
        print(f"🗑️ {len(clips_to_delete)} clip(s) supprimé(s)")
    
    def cut_clip_in_two(self, clip):
        """Coupe un clip en deux parties égales"""
        if clip not in self.clips:
            return
        
        # Calculer le point de coupe (milieu)
        cut_point = clip.start_time + (clip.duration / 2)
        half_duration = clip.duration / 2
        
        print(f"✂️ CUT: Clip {clip.start_time/1000:.2f}s-{(clip.start_time+clip.duration)/1000:.2f}s → coupe à {cut_point/1000:.2f}s")
        
        # Première partie : raccourcir le clip existant
        clip.duration = half_duration
        
        # Deuxième partie : créer nouveau clip
        new_clip = self.add_clip_direct(
            cut_point,
            half_duration,
            clip.color,
            clip.intensity
        )
        
        # Copier les propriétés
        if hasattr(clip, 'color2') and clip.color2:
            new_clip.color2 = clip.color2
        if hasattr(clip, 'effect'):
            new_clip.effect = clip.effect
            new_clip.effect_speed = clip.effect_speed
        new_clip.fade_in_duration = clip.fade_in_duration
        new_clip.fade_out_duration = clip.fade_out_duration
        
        self.update()
        print(f"   ✅ Clip coupé en 2 : [{clip.start_time/1000:.2f}s-{(clip.start_time+clip.duration)/1000:.2f}s] + [{new_clip.start_time/1000:.2f}s-{(new_clip.start_time+new_clip.duration)/1000:.2f}s]")
    
    def copy_clip_to_track(self, clip, target_track):
        """Copie le(s) clip(s) vers une autre piste"""
        # Copier tous les clips sélectionnés si multiple, sinon juste celui-ci
        clips_to_copy = self.selected_clips if len(self.selected_clips) > 1 else [clip]
        
        for source_clip in clips_to_copy:
            # Créer nouveau clip avec mêmes propriétés
            new_clip = target_track.add_clip(
                source_clip.start_time,
                source_clip.duration,
                source_clip.color,
                source_clip.intensity
            )
            
            # Copier toutes les propriétés
            if hasattr(source_clip, 'color2') and source_clip.color2:
                new_clip.color2 = source_clip.color2
            new_clip.fade_in_duration = getattr(source_clip, 'fade_in_duration', 0)
            new_clip.fade_out_duration = getattr(source_clip, 'fade_out_duration', 0)
            new_clip.effect = getattr(source_clip, 'effect', None)
            new_clip.effect_speed = getattr(source_clip, 'effect_speed', 50)
        
        target_track.update()
        count = len(clips_to_copy)
        print(f"📋 {count} clip(s) copié(s) vers {target_track.name}")
    
    def add_clip_fade_in(self, clip):
        """Ajoute fade in - Étirable sur timeline"""
        # Définir fade par défaut 1s
        clip.fade_in_duration = 1000
        self.update()
    
    def add_clip_fade_out(self, clip):
        """Ajoute fade out - Étirable sur timeline"""
        clip.fade_out_duration = 1000
        self.update()
    
    def clear_clip_fades(self, clip):
        """Supprime les fades"""
        clip.fade_in_duration = 0
        clip.fade_out_duration = 0
        self.update()
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def find_free_position(self, start_time, duration):
        """Trouve une position libre sur la timeline (pas de collision)
        start_time et duration sont en MS"""
        # Trier clips par start_time
        sorted_clips = sorted(self.clips, key=lambda c: c.start_time)
        
        # Vérifier collision et trouver première position libre
        for clip in sorted_clips:
            clip_end = clip.start_time + clip.duration
            new_end = start_time + duration
            
            # Chevauchement détecté
            if start_time < clip_end and new_end > clip.start_time:
                # Placer APRÈS ce clip
                start_time = clip_end
        
        return start_time
    
    def dropEvent(self, event):
        """Drop d'une couleur (ou bicolore) sur la piste - ANTI-COLLISION"""
        color_data = event.mimeData().text()
        
        # Calculer position temporelle du drop
        drop_x = event.position().x() - 145
        start_time = max(0, drop_x / self.pixels_per_ms)
        
        # Durée par défaut
        clip_duration = 5000
        
        # TROUVER POSITION LIBRE (anti-collision)
        start_time = self.find_free_position(start_time, clip_duration)
        
        # Vérifier si c'est un bicolore (format: "color1#color2")
        print(f"🎨 DROP: color_data='{color_data}', count#={color_data.count('#')}")
        
        if '#' in color_data and color_data.count('#') >= 2:
            # Bicolore - Format peut être "#ff0000##00ff00" (3 dièses)
            parts = color_data.split('#')
            parts = [p for p in parts if p]  # Supprimer éléments vides
            print(f"   Parts filtrés: {parts}")
            
            if len(parts) >= 2:
                color1_hex = '#' + parts[0]
                color2_hex = '#' + parts[1]
                
                print(f"   Color1: {color1_hex}, Color2: {color2_hex}")
                color1 = QColor(color1_hex)
                color2 = QColor(color2_hex)
                
                if not color1.isValid() or not color2.isValid():
                    print(f"   ❌ COULEURS INVALIDES! color1.valid={color1.isValid()}, color2.valid={color2.isValid()}")
                    return
                
                # Créer clip bicolore
                clip = self.add_clip(start_time, clip_duration, color1, 100)
                clip.color2 = color2
                self.update()  # Forcer repaint avec bicolore
                print(f"   ✅ Bicolore créé: {color1.name()} + {color2.name()}, clip.color2={clip.color2}")
            else:
                print(f"   ❌ Pas assez de parts: {len(parts)}")
                return
        else:
            # Monocouleur
            color = QColor(color_data)
            self.add_clip(start_time, 5000, color, 100)
        
        event.acceptProposedAction()
    
    def add_clip(self, start_time, duration, color, intensity):
        """Ajoute un clip à la piste AVEC anti-collision"""
        free_start = self.find_free_position(start_time, duration)
        
        clip = LightClip(free_start, duration, color, intensity, self)
        self.clips.append(clip)
        self.update()
        
        # Sauvegarder état pour undo
        if hasattr(self.parent_editor, 'save_state'):
            self.parent_editor.save_state()
        
        return clip
    
    def add_clip_direct(self, start_time, duration, color, intensity):
        """Ajoute un clip SANS anti-collision (pour undo/redo)"""
        clip = LightClip(start_time, duration, color, intensity, self)
        self.clips.append(clip)
        self.update()
        return clip
    
    def update_clips(self):
        """Met à jour la position/taille de tous les clips"""
        # Les clips ne sont plus des widgets visibles
        # Ils sont juste des objets de données
        # Le dessin se fait dans paintEvent de LightTrack
        for clip in self.clips:
            x = 145 + int(clip.start_time * self.pixels_per_ms)
            width = int(clip.duration * self.pixels_per_ms)
            # Stocker position pour interactions souris
            clip.x_pos = x
            clip.width_val = max(20, width)
            print(f"📐 UPDATE_CLIP: x={x}, width={width}")
        
        # Redessiner la piste
        self.update()
        print(f"   → Track update called")
    
    def update_zoom(self, pixels_per_ms):
        """Met à jour le zoom"""
        self.pixels_per_ms = pixels_per_ms
        self.update_clips()
        self.update()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        
        print(f"🖼️ TRACK PAINT: {self.name}, clips={len(self.clips)}")
        
        # Ligne horizontale séparatrice en haut
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        painter.drawLine(0, 0, self.width(), 0)
        
        # === DESSINER LA FORME D'ONDE EN ARRIÈRE-PLAN (style Virtual DJ) ===
        if self.waveform_data:
            # Configuration selon la piste
            if self.name == "Audio":
                painter.setOpacity(1.0)  # Complètement opaque
                max_height = 35
                draw_mirror = True  # Effet miroir haut/bas
            else:
                painter.setOpacity(0.15)
                max_height = 20
                draw_mirror = False
            
            # Calculer la largeur totale de la timeline en pixels (basé sur durée et zoom)
            timeline_width_px = int(self.total_duration * self.pixels_per_ms)
            
            # Calculer combien de pixels par échantillon
            pixels_per_sample = timeline_width_px / len(self.waveform_data)
            
            # Dessiner uniquement les échantillons visibles
            y_center = self.height() // 2
            
            # Style Virtual DJ: barres remplies avec contraste fort pour voir les beats
            for i, amplitude in enumerate(self.waveform_data):
                x = 145 + int(i * pixels_per_sample)
                
                # Ne dessiner que ce qui est visible
                if x < 145 or x > self.width():
                    continue
                
                # Amplifier les peaks pour mieux voir les beats
                height = int(amplitude * max_height * 1.2)  # +20% pour plus de contraste
                height = min(height, max_height)  # Limiter à la hauteur max
                
                if draw_mirror:
                    # Effet miroir avec contraste fort (comme Virtual DJ)
                    bar_width = max(1, int(pixels_per_sample * 0.8))  # 80% de l'espace pour laisser des gaps
                    
                    # Partie haute - gradient plus agressif
                    gradient = QLinearGradient(x, y_center - height, x, y_center)
                    if amplitude > 0.7:  # Peak fort = blanc brillant
                        gradient.setColorAt(0, QColor("#ffffff"))  # Blanc éclatant
                        gradient.setColorAt(0.5, QColor("#00d4ff"))  # Cyan
                        gradient.setColorAt(1, QColor("#004060"))  # Bleu très foncé
                    else:  # Amplitude normale
                        gradient.setColorAt(0, QColor("#00d4ff"))  # Cyan
                        gradient.setColorAt(0.7, QColor("#006080"))  # Bleu moyen
                        gradient.setColorAt(1, QColor("#002030"))  # Bleu très foncé
                    painter.fillRect(int(x), y_center - height, bar_width, height, gradient)
                    
                    # Partie basse (miroir)
                    gradient_bottom = QLinearGradient(x, y_center, x, y_center + height)
                    if amplitude > 0.7:
                        gradient_bottom.setColorAt(0, QColor("#004060"))
                        gradient_bottom.setColorAt(0.5, QColor("#00d4ff"))
                        gradient_bottom.setColorAt(1, QColor("#ffffff"))
                    else:
                        gradient_bottom.setColorAt(0, QColor("#002030"))
                        gradient_bottom.setColorAt(0.3, QColor("#006080"))
                        gradient_bottom.setColorAt(1, QColor("#00d4ff"))
                    painter.fillRect(int(x), y_center, bar_width, height, gradient_bottom)
                else:
                    # Version simple pour les autres pistes
                    painter.setPen(QPen(QColor("#00d4ff"), 1))
                    painter.drawLine(x, y_center - height, x, y_center + height)
            
            painter.setOpacity(1.0)
        
        # Grille temporelle - lignes verticales
        painter.setPen(QPen(QColor("#2a2a2a"), 1, Qt.SolidLine))
        for sec in range(0, int(self.total_duration / 1000) + 1):
            x = 145 + int(sec * 1000 * self.pixels_per_ms)
            if x < self.width():
                painter.drawLine(x, 0, x, self.height())
        
        # === DESSINER LES CLIPS ICI ===
        painter.setRenderHint(QPainter.Antialiasing)
        for clip in self.clips:
            x = 145 + int(clip.start_time * self.pixels_per_ms)
            width = int(clip.duration * self.pixels_per_ms)
            y = 10
            height = 40
            
            # Rectangle du clip
            clip_rect = QRect(x, y, max(20, width), height)
            
            # Fond couleur
            if hasattr(clip, 'color2') and clip.color2:
                # Bicolore avec coins arrondis
                print(f"   Bicolore: {clip.color.name()} | {clip.color2.name()}")
                
                # Créer path arrondi pour clip
                from PySide6.QtGui import QPainterPath
                path = QPainterPath()
                path.addRoundedRect(clip_rect.x(), clip_rect.y(), clip_rect.width(), clip_rect.height(), 4, 4)
                
                # Clip au path arrondi
                painter.setClipPath(path)
                
                mid = clip_rect.left() + clip_rect.width() // 2
                
                # Moitié gauche
                left_rect = QRect(clip_rect.left(), clip_rect.top(), clip_rect.width() // 2, clip_rect.height())
                painter.fillRect(left_rect, clip.color)
                
                # Moitié droite
                right_rect = QRect(mid, clip_rect.top(), clip_rect.width() - clip_rect.width() // 2, clip_rect.height())
                painter.fillRect(right_rect, clip.color2)
                
                # Remettre clip normal
                painter.setClipRect(self.rect())
                
                # Bordure
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#2a2a2a"), 2))
                painter.drawRoundedRect(clip_rect, 4, 4)
            else:
                # Monocouleur
                painter.fillRect(clip_rect, clip.color)
                # Bordure
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#2a2a2a"), 2))
                painter.drawRoundedRect(clip_rect, 4, 4)  # Réduit de 6 à 4
            
            # Texte intensité - Couleur adaptative
            if width > 40:
                # Calculer luminosité de la couleur
                luminance = (clip.color.red() * 0.299 + clip.color.green() * 0.587 + clip.color.blue() * 0.114)
                
                # Texte noir si couleur claire, blanc sinon
                if luminance > 128:
                    painter.setPen(QColor(0, 0, 0))  # Noir
                else:
                    painter.setPen(QColor(255, 255, 255))  # Blanc
                
                font = painter.font()
                font.setBold(True)
                font.setPixelSize(14)
                painter.setFont(font)
                text = f"{clip.intensity}%"
                painter.drawText(clip_rect, Qt.AlignCenter, text)
            
            # === FADES (TRIANGLES BLANCS VISIBLES) ===
            fade_in_px = int(clip.fade_in_duration * self.pixels_per_ms) if getattr(clip, 'fade_in_duration', 0) > 0 else 0
            fade_out_px = int(clip.fade_out_duration * self.pixels_per_ms) if getattr(clip, 'fade_out_duration', 0) > 0 else 0
            
            # Fade In (triangle gauche)
            if fade_in_px > 5:
                # Triangle semi-transparent
                painter.setBrush(QColor(255, 255, 255, 100))  # BLANC semi-transparent
                painter.setPen(Qt.NoPen)
                fade_in_poly = [
                    QPoint(clip_rect.left(), clip_rect.top()),
                    QPoint(clip_rect.left() + fade_in_px, clip_rect.top()),
                    QPoint(clip_rect.left(), clip_rect.bottom())
                ]
                painter.drawPolygon(QPolygon(fade_in_poly))
                
                # Ligne diagonale blanche épaisse
                painter.setPen(QPen(QColor(255, 255, 255), 3))
                painter.drawLine(clip_rect.left() + fade_in_px, clip_rect.top(), 
                               clip_rect.left(), clip_rect.bottom())
                
                # Barre noire VERTICALE pour grab (plus visible)
                painter.setPen(QPen(QColor(0, 0, 0), 5))
                painter.drawLine(clip_rect.left() + fade_in_px, clip_rect.top() + 5,
                               clip_rect.left() + fade_in_px, clip_rect.bottom() - 5)
            
            # Fade Out (triangle droit)
            if fade_out_px > 5:
                # Triangle semi-transparent
                painter.setBrush(QColor(255, 255, 255, 100))  # BLANC semi-transparent
                painter.setPen(Qt.NoPen)
                fade_out_poly = [
                    QPoint(clip_rect.right() - fade_out_px, clip_rect.top()),
                    QPoint(clip_rect.right(), clip_rect.top()),
                    QPoint(clip_rect.right(), clip_rect.bottom())
                ]
                painter.drawPolygon(QPolygon(fade_out_poly))
                
                # Ligne diagonale blanche épaisse
                painter.setPen(QPen(QColor(255, 255, 255), 3))
                painter.drawLine(clip_rect.right() - fade_out_px, clip_rect.top(),
                               clip_rect.right(), clip_rect.bottom())
                
                # Barre noire VERTICALE pour grab
                painter.setPen(QPen(QColor(0, 0, 0), 5))
                painter.drawLine(clip_rect.right() - fade_out_px, clip_rect.top() + 5,
                               clip_rect.right() - fade_out_px, clip_rect.bottom() - 5)
            
            # === OUTLINE SI SÉLECTIONNÉ ===
            if clip in self.selected_clips:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#00d4ff"), 3))  # Cyan épais
                painter.drawRoundedRect(clip_rect, 6, 6)
        
        # Dessiner le rubber band (rectangle de sélection) - PLUS VISIBLE
        if self.rubber_band_rect:
            print(f"🎨 DRAWING RUBBER BAND: {self.rubber_band_rect}")
            painter.setBrush(QColor(0, 212, 255, 50))  # Cyan semi-transparent (plus opaque)
            painter.setPen(QPen(QColor("#00d4ff"), 3, Qt.DashLine))  # Bordure cyan épaisse
            painter.drawRect(self.rubber_band_rect)
        
        # Curseur de lecture (ligne rouge) - TOUJOURS dessiner
        cursor_x = 145 + int(self.parent_editor.playback_position * self.pixels_per_ms)
        if 145 <= cursor_x < self.width():
            painter.setPen(QPen(QColor("#ff0000"), 3))
            painter.drawLine(cursor_x, 0, cursor_x, self.height())
        
        # IMPORTANT : Terminer le painter
        painter.end()


class LightTimelineEditor(QDialog):
    """Éditeur de séquence lumière - Thème cohérent"""
    def __init__(self, main_window, media_row):
        super().__init__(main_window)
        self.main_window = main_window
        self.media_row = media_row
        
        # Récupérer infos du média
        item = main_window.seq.table.item(media_row, 1)
        self.media_path = item.data(Qt.UserRole) if item else ""
        self.media_name = item.text() if item else f"Média {media_row + 1}"
        
        self.setWindowTitle(f"🎬 Éditeur - {self.media_name}")
        
        # FORCER les couleurs de tooltip avec QPalette + LOGS
        print("🎨 Configuration des tooltips...")
        palette = self.palette()
        palette.setColor(QPalette.ToolTipBase, QColor("white"))
        palette.setColor(QPalette.ToolTipText, QColor("black"))
        self.setPalette(palette)
        print(f"   QPalette: Base={palette.color(QPalette.ToolTipBase).name()}, Text={palette.color(QPalette.ToolTipText).name()}")
        
        # Forcer aussi au niveau application
        app_palette = QApplication.instance().palette()
        app_palette.setColor(QPalette.ToolTipBase, QColor("white"))
        app_palette.setColor(QPalette.ToolTipText, QColor("black"))
        QApplication.instance().setPalette(app_palette)
        print(f"   App Palette configurée")
        
        # THÈME GLOBAL - Fond noir + styles
        self.setStyleSheet("""
            QDialog {
                background: #0a0a0a;
            }
            QToolTip {
                background-color: white !important;
                color: black !important;
                border: 2px solid #00d4ff;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton QToolTip {
                background-color: white !important;
                color: black !important;
            }
        """)
        print("   StyleSheet appliqué avec !important")
        print("✅ Configuration tooltips terminée")
        
        # Plein écran
        self.showMaximized()
        
        # Curseur de lecture - Initialiser depuis position actuelle si média en cours
        if main_window.player.playbackState() == QMediaPlayer.PlayingState:
            self.playback_position = main_window.player.position()
            print(f"⏸ Média en cours → Position initiale: {self.playback_position/1000:.1f}s")
        else:
            self.playback_position = 0
        
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.update_playhead)
        
        # Récupérer durée du média
        self.media_duration = self.get_media_duration()
        
        # === HISTORIQUE UNDO ===
        self.history = []  # Liste d'états (snapshot des clips)
        self.history_index = -1
        
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # === HEADER (sans Play - juste titre + zoom) ===
        header = QWidget()
        header.setStyleSheet("background: #1a1a1a; border-bottom: 2px solid #3a3a3a;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 10, 15, 10)
        
        title = QLabel(f"🎬 {self.media_name}")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; text-decoration: none;")
        header_layout.addWidget(title)
        
        # Durée en format mm:ss
        duration_seconds = int(self.media_duration / 1000)
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        duration_label = QLabel(f"⏱ {minutes}:{seconds:02d}")
        duration_label.setStyleSheet("color: #888; font-size: 13px; text-decoration: none;")
        header_layout.addWidget(duration_label)
        
        header_layout.addStretch()
        
        # === BOUTON UNDO ===
        undo_btn = QPushButton("↶")
        undo_btn.setToolTip("Annuler (Ctrl+Z)")
        undo_btn.clicked.connect(self.undo)
        undo_btn.setFixedSize(45, 45)
        undo_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                border-radius: 22px;
                font-size: 22px;
            }
            QPushButton:hover {
                background: #4a4a4a;
            }
        """)
        header_layout.addWidget(undo_btn)
        
        # === BOUTON CUT (après Undo) ===
        cut_btn = QPushButton("✂")
        cut_btn.setToolTip("Outil Couper (C)\nCoupez un clip en 2 parties")
        cut_btn.clicked.connect(self.toggle_cut_mode)
        cut_btn.setFixedSize(45, 45)
        cut_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                border: none;
                border-radius: 22px;
                font-size: 20px;
            }
            QPushButton:hover {
                background: #4a4a4a;
            }
            QPushButton:checked {
                background: #00d4ff;
                color: black;
            }
        """)
        cut_btn.setCheckable(True)
        self.cut_btn = cut_btn  # Stocker pour y accéder plus tard
        header_layout.addWidget(cut_btn)
        
        # Initialiser le mode cut
        self.cut_mode = False
        
        # === BOUTONS ACTIONS ===
        ai_btn = QPushButton("✨")
        ai_btn.setToolTip("Génération IA")
        ai_btn.clicked.connect(self.generate_ai_sequence)
        ai_btn.setFixedSize(45, 45)
        ai_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #8B00FF, stop:1 #FF00FF);
                color: white;
                border: none;
                border-radius: 22px;
                font-size: 22px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #9B10FF, stop:1 #FF10FF);
            }
        """)
        header_layout.addWidget(ai_btn)
        
        clear_btn = QPushButton("🗑")
        clear_btn.setToolTip("Tout effacer")
        clear_btn.clicked.connect(self.clear_all_clips)
        clear_btn.setFixedSize(45, 45)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: #aa2222;
                color: white;
                border: none;
                border-radius: 22px;
                font-size: 22px;
            }
            QPushButton:hover { background: #cc3333; }
        """)
        header_layout.addWidget(clear_btn)
        
        header_layout.addSpacing(20)
        
        # === ZOOM ===
        zoom_out_btn = QPushButton("➖")
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_out_btn.setFixedSize(40, 40)
        zoom_out_btn.setFocusPolicy(Qt.NoFocus)  # Empêcher capture du focus
        zoom_out_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                color: white;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-size: 18px;
            }
            QPushButton:hover { background: #3a3a3a; }
        """)
        header_layout.addWidget(zoom_out_btn)
        
        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("color: white; padding: 0 15px; font-size: 13px;")
        header_layout.addWidget(self.zoom_label)
        
        zoom_in_btn = QPushButton("➕")
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_in_btn.setFixedSize(40, 40)
        zoom_in_btn.setFocusPolicy(Qt.NoFocus)  # Empêcher capture du focus
        zoom_in_btn.setFixedSize(40, 40)
        zoom_in_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                color: white;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                font-size: 18px;
            }
            QPushButton:hover { background: #3a3a3a; }
        """)
        header_layout.addWidget(zoom_in_btn)
        
        layout.addWidget(header)
        
        # === RULER (règle temporelle) ===
        self.ruler = QWidget()
        self.ruler.setFixedHeight(35)
        self.ruler.setStyleSheet("background: #1a1a1a; border-bottom: 1px solid #2a2a2a;")
        self.ruler.paintEvent = self.paint_ruler
        self.ruler.mousePressEvent = self.ruler_mouse_press
        self.ruler.mouseMoveEvent = self.ruler_mouse_move
        self.ruler.mouseReleaseEvent = self.ruler_mouse_release
        layout.addWidget(self.ruler)
        
        # === SCROLL AREA pour les pistes ===
        self.tracks_scroll = QScrollArea()
        self.tracks_scroll.setWidgetResizable(True)
        self.tracks_scroll.setStyleSheet("""
            QScrollArea {
                background: #0a0a0a;
                border: none;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 12px;
            }
            QScrollBar::handle:vertical {
                background: #3a3a3a;
                border-radius: 6px;
            }
            QScrollBar:horizontal {
                background: #1a1a1a;
                height: 12px;
            }
            QScrollBar::handle:horizontal {
                background: #3a3a3a;
                border-radius: 6px;
            }
        """)
        
        tracks_container = QWidget()
        tracks_container.setStyleSheet("background: #0a0a0a;")
        tracks_layout = QVBoxLayout(tracks_container)
        tracks_layout.setSpacing(0)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        
        # Créer les pistes (Lat → Douche)
        self.track_face = LightTrack("Face", self.media_duration, self)
        self.track_douche1 = LightTrack("Douche 1", self.media_duration, self)
        self.track_douche2 = LightTrack("Douche 2", self.media_duration, self)
        self.track_douche3 = LightTrack("Douche 3", self.media_duration, self)
        self.track_contre = LightTrack("Contres", self.media_duration, self)
        
        # Piste spéciale pour la forme d'onde (lecture seule)
        self.track_waveform = LightTrack("Audio", self.media_duration, self)
        self.track_waveform.setAcceptDrops(False)  # Pas de drop sur cette piste
        self.track_waveform.setMinimumHeight(80)  # Plus haute pour mieux voir
        
        self.tracks = [self.track_face, self.track_douche1, self.track_douche2, 
                       self.track_douche3, self.track_contre]
        
        for track in self.tracks:
            tracks_layout.addWidget(track)
        
        # Ajouter la piste waveform en dernier
        tracks_layout.addWidget(self.track_waveform)
        
        tracks_layout.addStretch()
        self.tracks_scroll.setWidget(tracks_container)
        layout.addWidget(self.tracks_scroll)
        
        # === PALETTE DE COULEURS ===
        self.palette = ColorPalette(self)
        layout.addWidget(self.palette)
        
        # === FOOTER (avec Play/Pause) ===
        footer = QWidget()
        footer.setStyleSheet("background: #1a1a1a; border-top: 2px solid #3a3a3a;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(15, 10, 15, 10)
        footer_layout.setSpacing(10)
        
        # === CONTRÔLES AUDIO À GAUCHE ===
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
            QPushButton:pressed {
                background: #3a3a3a;
            }
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
            QPushButton {
                padding: 18px;
                font-size: 24px;
            }
        """)
        footer_layout.addWidget(self.play_pause_btn)
        
        # +10s
        fwd_btn = QPushButton("⏩")
        fwd_btn.setFixedSize(60, 60)
        fwd_btn.clicked.connect(lambda: self.seek_relative(10000))
        fwd_btn.setStyleSheet(transport_btn_style)
        footer_layout.addWidget(fwd_btn)
        
        footer_layout.addStretch()
        
        # === BOUTONS À DROITE ===
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
        
        layout.addWidget(footer)
        
        # Zoom par défaut
        self.current_zoom = 1.0
        
        # Player audio pour preview
        self.setup_audio_player()
        
        # Charger séquence existante
        self.load_existing_sequence()
        
        # Forcer l'affichage du curseur rouge au démarrage
        QTimer.singleShot(100, lambda: self.ruler.update())
        
        # === GÉNÉRER LA FORME D'ONDE AUDIO ===
        # Générer uniquement pour la piste waveform dédiée
        if self.media_path and os.path.exists(self.media_path):
            try:
                # Essayer de générer la forme d'onde
                waveform = self.track_waveform.generate_waveform(self.media_path, max_samples=3000)
                if waveform:
                    # Appliquer UNIQUEMENT à la piste waveform
                    self.track_waveform.waveform_data = waveform
                    print("✅ Forme d'onde appliquée à la piste dédiée")
                else:
                    print("⚠️ Impossible de générer la forme d'onde")
            except Exception as e:
                print(f"⚠️ Erreur forme d'onde: {e}")
    
    def get_media_duration(self):
        """Récupère la durée réelle du média"""
        try:
            from PySide6.QtCore import QEventLoop
            temp_player = QMediaPlayer()
            
            # Handler pour récupérer durée
            duration_ms = [0]
            
            def on_duration_changed(dur):
                if dur > 0:
                    duration_ms[0] = dur
            
            temp_player.durationChanged.connect(on_duration_changed)
            temp_player.setSource(QUrl.fromLocalFile(self.media_path))
            
            # Attendre avec event loop
            loop = QEventLoop()
            temp_player.durationChanged.connect(loop.quit)
            
            import time
            start = time.time()
            while duration_ms[0] == 0 and (time.time() - start) < 5:  # 5s timeout
                QApplication.processEvents()
                time.sleep(0.05)
            
            if duration_ms[0] > 0:
                print(f"📏 Durée média : {duration_ms[0]/1000:.1f}s")
                return duration_ms[0]
        except Exception as e:
            print(f"⚠️ Erreur durée : {e}")
        
        print("⚠️ Durée par défaut : 180s")
        return 180000  # 3 minutes par défaut
    
    def setup_audio_player(self):
        """Configure le player audio pour preview"""
        self.preview_player = QMediaPlayer()
        self.preview_audio = QAudioOutput()
        self.preview_player.setAudioOutput(self.preview_audio)
        
        if self.media_path:
            self.preview_player.setSource(QUrl.fromLocalFile(self.media_path))
    
    def toggle_play_pause(self):
        """Toggle play/pause avec timer"""
        if self.preview_player.playbackState() == QMediaPlayer.PlayingState:
            self.preview_player.pause()
            self.play_pause_btn.setText("▶")
            self.playback_timer.stop()
        else:
            self.preview_player.play()
            self.play_pause_btn.setText("⏸")
            self.playback_timer.start(50)  # Update toutes les 50ms
    
    def seek_relative(self, delta_ms):
        """Seek relatif (+/- 10s)"""
        current = self.preview_player.position()
        new_pos = max(0, min(current + delta_ms, self.media_duration))
        self.preview_player.setPosition(int(new_pos))
    
    def zoom_in(self):
        """Zoom avant centré sur le curseur de lecture"""
        old_zoom = self.current_zoom
        self.current_zoom = min(5.0, self.current_zoom * 1.5)
        self.apply_zoom_centered(old_zoom)
    
    def zoom_out(self):
        """Zoom arrière centré sur le curseur de lecture"""
        old_zoom = self.current_zoom
        self.current_zoom = max(0.05, self.current_zoom / 1.5)
        self.apply_zoom_centered(old_zoom)
    
    def apply_zoom_centered(self, old_zoom):
        """Applique le zoom en gardant le curseur de lecture centré"""
        # Sauvegarder la position actuelle du scroll horizontal
        scrollbar = self.tracks_scroll.horizontalScrollBar()
        old_scroll_pos = scrollbar.value()
        
        # Position actuelle du curseur en pixels (avant zoom)
        old_pixels_per_ms = 0.05 * old_zoom
        cursor_x_before = 145 + int(self.playback_position * old_pixels_per_ms)
        
        print(f"🔍 ZOOM: pos_curseur={self.playback_position/1000:.2f}s, old_zoom={old_zoom:.2f}, new_zoom={self.current_zoom:.2f}")
        print(f"   cursor_x_before={cursor_x_before}, scroll_before={old_scroll_pos}")
        
        # Appliquer le nouveau zoom
        pixels_per_ms = 0.05 * self.current_zoom
        for track in self.tracks:
            track.update_zoom(pixels_per_ms)
        self.track_waveform.update_zoom(pixels_per_ms)
        
        self.zoom_label.setText(f"{int(self.current_zoom * 100)}%")
        self.ruler.update()
        
        # Position du curseur après zoom (en pixels absolus)
        cursor_x_after = 145 + int(self.playback_position * pixels_per_ms)
        
        # Calculer le nouveau scroll pour garder le curseur au même endroit à l'écran
        # Le delta de position du curseur doit être compensé par le scroll
        delta_cursor = cursor_x_after - cursor_x_before
        new_scroll_pos = old_scroll_pos + delta_cursor
        
        print(f"   cursor_x_after={cursor_x_after}, delta={delta_cursor}, new_scroll={new_scroll_pos}")
        
        # Appliquer le nouveau scroll
        scrollbar.setValue(int(new_scroll_pos))
        print(f"   ✅ Scroll ajusté")
    
    def apply_zoom(self):
        """Applique le zoom à toutes les pistes (utilisé ailleurs)"""
        pixels_per_ms = 0.05 * self.current_zoom
        for track in self.tracks:
            track.update_zoom(pixels_per_ms)
        self.track_waveform.update_zoom(pixels_per_ms)
        
        self.zoom_label.setText(f"{int(self.current_zoom * 100)}%")
        self.ruler.update()
    
    def ruler_mouse_press(self, event):
        """Clic sur ruler pour déplacer le curseur"""
        self.ruler_dragging = True
        self.update_cursor_from_ruler(event)
    
    def ruler_mouse_move(self, event):
        """Drag sur ruler"""
        if hasattr(self, 'ruler_dragging') and self.ruler_dragging:
            self.update_cursor_from_ruler(event)
    
    def ruler_mouse_release(self, event):
        """Release sur ruler"""
        self.ruler_dragging = False
    
    def update_cursor_from_ruler(self, event):
        """Met à jour curseur depuis position souris SANS lancer la lecture"""
        x = event.position().x()
        if x >= 145:
            # Calculer position temporelle
            pixels_per_ms = 0.05 * self.current_zoom
            time_ms = (x - 145) / pixels_per_ms
            time_ms = max(0, min(time_ms, self.media_duration))
            
            # Déplacer curseur ET player SANS démarrer la lecture
            self.playback_position = time_ms
            self.preview_player.setPosition(int(time_ms))
            
            # Redessiner
            self.ruler.update()
            for track in self.tracks:
                track.update()
            self.track_waveform.update()
    
    def paint_ruler(self, event):
        """Dessine la règle temporelle avec curseur rouge"""
        painter = QPainter(self.ruler)
        painter.fillRect(0, 0, self.ruler.width(), self.ruler.height(), QColor("#1a1a1a"))
        
        # Texte secondes
        painter.setPen(QColor("#888"))
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        
        pixels_per_ms = 0.05 * self.current_zoom
        
        # Espacement adaptatif selon le zoom
        if self.current_zoom < 0.5:
            step = 5  # 5 secondes
        elif self.current_zoom < 1.0:
            step = 2  # 2 secondes
        else:
            step = 1  # 1 seconde
        
        for sec in range(0, int(self.media_duration / 1000) + 1, step):
            x = 145 + int(sec * 1000 * pixels_per_ms)
            if x < self.ruler.width():
                painter.drawLine(x, 25, x, 35)
                
                # Format temps : minutes:secondes si >= 60s
                if sec >= 60:
                    minutes = sec // 60
                    seconds = sec % 60
                    time_str = f"{minutes}:{seconds:02d}"
                else:
                    time_str = f"{sec}s"
                
                painter.drawText(x - 18, 18, time_str)
        
        # Curseur de lecture (bande rouge) - TOUJOURS visible
        cursor_x = 145 + int(self.playback_position * pixels_per_ms)
        if 145 <= cursor_x < self.ruler.width():
            # Ligne rouge épaisse
            painter.setPen(QPen(QColor("#ff0000"), 3))
            painter.drawLine(cursor_x, 0, cursor_x, self.ruler.height())
            
            # Triangle en haut
            painter.setBrush(QColor("#ff0000"))
            painter.setPen(Qt.NoPen)
            triangle = QPolygon([
                QPoint(cursor_x - 6, 0),
                QPoint(cursor_x + 6, 0),
                QPoint(cursor_x, 10)
            ])
            painter.drawPolygon(triangle)
    
    def update_playhead(self):
        """Met à jour la position du curseur pendant lecture"""
        if self.preview_player.playbackState() == QMediaPlayer.PlayingState:
            self.playback_position = self.preview_player.position()
            self.ruler.update()
            
            # Redessiner toutes les pistes Y COMPRIS waveform
            for track in self.tracks:
                track.update()
            self.track_waveform.update()
    
    def load_existing_sequence(self):
        """Charge la séquence existante si elle existe"""
        if self.media_row in self.main_window.seq.sequences:
            seq = self.main_window.seq.sequences[self.media_row]
            clips_data = seq.get('clips', [])
            
            print(f"📂 Chargement séquence : {len(clips_data)} clips")
            
            # Recréer les clips sur les pistes
            track_map = {
                'Face': self.track_face,
                'Douche 1': self.track_douche1,
                'Douche 2': self.track_douche2,
                'Douche 3': self.track_douche3,
                'Contres': self.track_contre,
                # Rétrocompatibilité avec anciens fichiers (avec emojis)
                '💡 Face': self.track_face,
                '💧 Douche 1': self.track_douche1,
                '💧 Douche 2': self.track_douche2,
                '💧 Douche 3': self.track_douche3,
                '🔴 Contres': self.track_contre,
                '🔵 Lat 1': self.track_douche1,
                '🔵 Lat 2': self.track_douche2,
                '🔵 Lat 3': self.track_douche3,
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
                    
                    # Charger les fades
                    clip.fade_in_duration = clip_data.get('fade_in', 0)
                    clip.fade_out_duration = clip_data.get('fade_out', 0)
                    
                    # Charger effets
                    clip.effect = clip_data.get('effect')
                    clip.effect_speed = clip_data.get('effect_speed', 50)
                    
                    # Charger color2 si bicolore
                    if 'color2' in clip_data:
                        clip.color2 = QColor(clip_data['color2'])
                        clip.update_visual()
    
    def save_sequence(self):
        """Sauvegarde la séquence au format .tui avec effets et bicolore"""
        # Convertir les clips en données complètes
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
                
                # Ajouter color2 si bicolore
                if hasattr(clip, 'color2') and clip.color2:
                    clip_data['color2'] = clip.color2.name()
                
                all_clips.append(clip_data)
        
        # Sauvegarder dans sequences
        self.main_window.seq.sequences[self.media_row] = {
            'clips': all_clips,
            'duration': self.media_duration
        }
        
        # Marquer dirty pour sauvegarde
        self.main_window.seq.is_dirty = True
        
        # Ajouter "Play Lumière" au combo DMX
        dmx_widget = self.main_window.seq.table.cellWidget(self.media_row, 4)
        if dmx_widget and isinstance(dmx_widget, QComboBox):
            if dmx_widget.findText("Play Lumière") == -1:
                dmx_widget.addItem("Play Lumière")
            dmx_widget.setCurrentText("Play Lumière")
            self.main_window.seq.on_dmx_changed(self.media_row, "Play Lumière")
        
        print(f"💾 Séquence sauvegardée : {len(all_clips)} clips")
        QMessageBox.information(self, "Sauvegarde",
            f"✅ Séquence sauvegardée avec succès !\n\n{len(all_clips)} clips")
        
        # Fermer l'éditeur après sauvegarde
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
            print("🗑️ Tous les clips effacés")
    
    def generate_ai_sequence(self):
        """Génère une séquence avec IA - DIALOG AMÉLIORÉ"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QProgressBar, QPushButton, QCheckBox, QHBoxLayout
        
        dialog = QDialog(self)
        dialog.setWindowTitle("✨ Génération IA")
        dialog.setFixedSize(550, 450)
        dialog.setStyleSheet("background: #1a1a1a;")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # Titre
        title = QLabel("🎨 Choisissez la dominante de couleur")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        # Sélection couleur
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
            ("🔴 Rouge énergique", "#ff0000"),
            ("🟢 Vert apaisant", "#00ff00"),
            ("🔵 Bleu froid", "#0000ff"),
            ("🟡 Jaune chaleureux", "#c8c800"),
            ("🟣 Violet mystique", "#ff00ff"),
            ("🔶 Orange dynamique", "#ff8800"),
            ("⚪ Blanc pur", "#ffffff"),
            ("🌈 Arc-en-ciel (mix)", "rainbow"),
            ("🎨 Bicolore Rouge+Bleu", "rb"),
            ("🎨 Bicolore Vert+Jaune", "gy"),
        ]
        
        for name, _ in colors:
            color_combo.addItem(name)
        
        layout.addWidget(color_combo)
        
        # === CHOIX DES PISTES ===
        tracks_label = QLabel("🎭 Pistes à générer :")
        tracks_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(tracks_label)
        
        # Checkboxes pour chaque piste
        tracks_checks = {}
        for track in self.tracks:
            # Compter clips existants
            clip_count = len(track.clips)
            
            checkbox = QCheckBox(f"{track.name} {'⚠️ (' + str(clip_count) + ' clips)' if clip_count > 0 else ''}")
            checkbox.setChecked(True)  # Toutes cochées par défaut
            checkbox.setStyleSheet("""
                QCheckBox {
                    color: white;
                    font-size: 13px;
                    spacing: 10px;
                }
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                }
            """)
            tracks_checks[track] = checkbox
            layout.addWidget(checkbox)
        
        # Avertissement si clips existants
        has_existing_clips = any(len(track.clips) > 0 for track in self.tracks)
        if has_existing_clips:
            warning = QLabel("⚠️ Des clips seront supprimés sur les pistes cochées")
            warning.setStyleSheet("color: #ffaa00; font-size: 12px; margin-top: 5px;")
            layout.addWidget(warning)
        
        # Barre de progression
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
        
        cancel_btn = QPushButton("Annuler")
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
        
        generate_btn = QPushButton("✨ Générer")
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
            
            # Récupérer pistes sélectionnées
            selected_tracks = [track for track, checkbox in tracks_checks.items() if checkbox.isChecked()]
            
            # Générer séquence
            self.perform_ai_generation(color_code, selected_tracks, progress, status_label, dialog)
        
        generate_btn.clicked.connect(start_generation)
        btn_layout.addWidget(generate_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def perform_ai_generation(self, color_code, selected_tracks, progress, status_label, dialog):
        """Génère les clips avec progression - IA améliorée + choix pistes"""
        import random
        
        # Effacer clips UNIQUEMENT sur pistes sélectionnées
        for track in selected_tracks:
            track.clips.clear()
        
        progress.setValue(10)
        status_label.setText("🎵 Analyse du rythme...")
        QApplication.processEvents()
        
        # Paramètres selon couleur + jaune moins flashy
        if color_code == "rainbow":
            main_colors = [QColor("#ff0000"), QColor("#00ff00"), QColor("#0000ff"), 
                          QColor("#c8c800"), QColor("#ff00ff"), QColor("#00ffff")]  # Jaune moins flashy
            secondary_colors = [QColor("#ff8800"), QColor("#00ff88"), QColor("#8800ff")]
        elif color_code == "rb":
            main_colors = [QColor("#ff0000"), QColor("#0000ff")]
            secondary_colors = [QColor("#ff00ff"), QColor("#ff8800")]
        elif color_code == "gy":
            main_colors = [QColor("#00ff00"), QColor("#c8c800")]  # Jaune moins flashy
            secondary_colors = [QColor("#88ff00"), QColor("#ffff88")]
        elif color_code == "#ffff00":
            # Jaune dominant - moins flashy + variations
            main_colors = [QColor("#c8c800")]
            secondary_colors = [QColor("#ffaa00"), QColor("#ff8800")]
        else:
            main_colors = [QColor(color_code)]
            # Générer variations de la couleur dominante
            base = QColor(color_code)
            secondary_colors = [
                QColor(min(255, base.red() + 30), base.green(), base.blue()),
                QColor(base.red(), min(255, base.green() + 30), base.blue()),
            ]
        
        progress.setValue(30)
        status_label.setText("✨ Création des variations...")
        QApplication.processEvents()
        
        # BPM simulation (120 BPM typique)
        beat_duration = 500  # ms (120 BPM = 500ms par beat)
        
        duration_ms = self.media_duration
        current_time = 0
        clip_count = 0
        
        # Identifier quelles pistes sont sélectionnées
        has_face = self.track_face in selected_tracks
        has_douche1 = self.track_douche1 in selected_tracks
        has_douche2 = self.track_douche2 in selected_tracks
        has_douche3 = self.track_douche3 in selected_tracks
        has_contre = self.track_contre in selected_tracks
        
        # Générer variations subtiles de la couleur principale
        def get_color_variations(base_color):
            """Crée des variations subtiles d'une couleur"""
            r, g, b = base_color.red(), base_color.green(), base_color.blue()
            variations = [base_color]
            
            # Variation plus sombre
            variations.append(QColor(max(0, r-40), max(0, g-40), max(0, b-40)))
            # Variation plus claire
            variations.append(QColor(min(255, r+40), min(255, g+40), min(255, b+40)))
            # Variation saturée
            if r > 200:  # Rouge dominant
                variations.append(QColor(r, max(0, g-20), max(0, b-20)))
            elif g > 200:  # Vert dominant
                variations.append(QColor(max(0, r-20), g, max(0, b-20)))
            elif b > 200:  # Bleu dominant
                variations.append(QColor(max(0, r-20), max(0, g-20), b))
            
            return variations
        
        # Créer palettes de variations
        color_variations = {}
        for color in main_colors:
            color_variations[color] = get_color_variations(color)
        
        last_colors = {}  # Mémoriser la dernière couleur par piste pour éviter répétitions immédiates
        
        while current_time < duration_ms:
            # Durée basée sur beats (2, 4, 8 beats) - changements plus fréquents
            beats = random.choice([2, 4, 8])
            clip_duration = beat_duration * beats
            
            # === FACE TOUJOURS EN BLANC (si sélectionnée) ===
            if has_face:
                self.track_face.add_clip(current_time, clip_duration, QColor("#ffffff"), random.randint(85, 100))
                clip_count += 1
            
            # === DOUCHES - TOUTES REMPLIES AVEC VARIATIONS ===
            selected_douches = []
            if has_douche1:
                selected_douches.append(self.track_douche1)
            if has_douche2:
                selected_douches.append(self.track_douche2)
            if has_douche3:
                selected_douches.append(self.track_douche3)
            
            for douche in selected_douches:
                # Choisir une variation de la couleur principale
                base_color = random.choice(main_colors)
                variations = color_variations[base_color]
                
                # Éviter la répétition immédiate
                if douche in last_colors:
                    available = [c for c in variations if c != last_colors[douche]]
                    color = random.choice(available) if available else random.choice(variations)
                else:
                    color = random.choice(variations)
                
                last_colors[douche] = color
                
                # 20% chance de bicolore pour dynamisme
                if random.random() < 0.2 and secondary_colors:
                    clip = douche.add_clip(current_time, clip_duration, color, random.randint(75, 95))
                    clip.color2 = random.choice(secondary_colors)
                else:
                    douche.add_clip(current_time, clip_duration, color, random.randint(75, 95))
                clip_count += 1
            
            # === CONTRES - TOUJOURS REMPLIES avec variations subtiles ===
            if has_contre:
                # Alterner entre couleur principale et variations
                if random.random() < 0.6:  # 60% couleur principale
                    contre_base = random.choice(main_colors)
                    contre_variations = color_variations[contre_base]
                    contre_color = random.choice(contre_variations)
                else:  # 40% couleur secondaire
                    contre_color = random.choice(secondary_colors) if secondary_colors else random.choice(main_colors)
                
                self.track_contre.add_clip(current_time, clip_duration, contre_color, random.randint(70, 90))
                clip_count += 1
            
            # AVANCER LE TEMPS
            current_time += clip_duration
            
            # Mettre à jour progression
            progress.setValue(30 + int((current_time / duration_ms) * 60))
            QApplication.processEvents()
        
        progress.setValue(100)
        status_label.setText(f"✅ {clip_count} clips créés !")
        QApplication.processEvents()
        
        # Fermer après 1s
        QTimer.singleShot(1000, dialog.accept)
        
        print(f"✨ IA : {clip_count} clips générés (Face blanc + dominante {color_code})")
    
    def wheelEvent(self, event):
        """Scroll souris = Zoom/Dezoom"""
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()
    
    def keyPressEvent(self, event):
        """Barre espace = Play/Pause + Ctrl+Z = Undo + Delete = Supprimer"""
        if event.key() == Qt.Key_Space:
            # Ne PAS propager aux boutons
            self.toggle_play_pause()
            event.accept()
            return
        elif event.key() == Qt.Key_Z and event.modifiers() & Qt.ControlModifier:
            # Ctrl+Z = Undo
            self.undo()
            event.accept()
            return
        elif event.key() == Qt.Key_Delete:
            # Suppr = Supprimer clips sélectionnés
            self.delete_selected_clips()
            event.accept()
            return
        elif event.key() == Qt.Key_A and event.modifiers() & Qt.ControlModifier:
            # Ctrl+A = Tout sélectionner
            self.select_all_clips()
            event.accept()
            return
        else:
            super().keyPressEvent(event)
    
    def select_all_clips(self):
        """Sélectionne tous les clips de toutes les pistes"""
        for track in self.tracks:
            track.selected_clips = track.clips[:]  # Copie de la liste
            track.update()
        
        total = sum(len(track.selected_clips) for track in self.tracks)
        print(f"✅ {total} clip(s) sélectionné(s)")
    
    def delete_selected_clips(self):
        """Supprime tous les clips sélectionnés dans toutes les pistes"""
        if not any(track.selected_clips for track in self.tracks):
            return
        
        total_deleted = 0
        for track in self.tracks:
            if track.selected_clips:
                count = len(track.selected_clips)
                for clip in track.selected_clips[:]:  # Copie pour éviter modif pendant iteration
                    track.clips.remove(clip)
                track.selected_clips.clear()
                track.update()
                total_deleted += count
        
        print(f"🗑️ {total_deleted} clip(s) supprimé(s)")
        self.save_state()
    
    def save_state(self):
        """Sauvegarde l'état actuel pour undo"""
        state = []
        for track in self.tracks:
            for clip in track.clips:
                clip_data = {
                    'track': track.name,
                    'start': clip.start_time,
                    'duration': clip.duration,
                    'color': clip.color.name(),
                    'color2': clip.color2.name() if hasattr(clip, 'color2') and clip.color2 else None,
                    'intensity': clip.intensity,
                    'fade_in': getattr(clip, 'fade_in_duration', 0),
                    'fade_out': getattr(clip, 'fade_out_duration', 0),
                }
                state.append(clip_data)
        
        # Ajouter au history
        self.history = self.history[:self.history_index + 1]  # Supprimer futurs après undo
        self.history.append(state)
        self.history_index += 1
        
        # Limiter à 50 états
        if len(self.history) > 50:
            self.history.pop(0)
            self.history_index -= 1
    
    def undo(self):
        """Annuler la dernière action"""
        if self.history_index > 0:
            self.history_index -= 1
            state = self.history[self.history_index]
            
            print(f"↶ UNDO: Restauration état {self.history_index} avec {len(state)} clips")
            
            # Restaurer l'état
            for track in self.tracks:
                track.clips.clear()
            
            track_map = {
                'Face': self.track_face,
                'Douche 1': self.track_douche1,
                'Douche 2': self.track_douche2,
                'Douche 3': self.track_douche3,
                'Contres': self.track_contre,
            }
            
            for clip_data in state:
                track = track_map.get(clip_data['track'])
                if track:
                    color = QColor(clip_data['color'])
                    # UTILISER add_clip_direct pour ne PAS déplacer les clips
                    clip = track.add_clip_direct(
                        clip_data['start'],
                        clip_data['duration'],
                        color,
                        clip_data['intensity']
                    )
                    if clip_data['color2']:
                        clip.color2 = QColor(clip_data['color2'])
                    clip.fade_in_duration = clip_data['fade_in']
                    clip.fade_out_duration = clip_data['fade_out']
            
            # Forcer update de toutes les pistes
            for track in self.tracks:
                track.update()
            
            print(f"   ✅ État restauré avec succès")
    
    def toggle_cut_mode(self):
        """Active/désactive le mode CUT"""
        self.cut_mode = not self.cut_mode
        
        if self.cut_mode:
            print("✂️ Mode CUT activé - Cliquez sur un clip pour le couper")
            self.setCursor(Qt.SplitHCursor)  # Curseur de découpe
        else:
            print("✂️ Mode CUT désactivé")
            self.setCursor(Qt.ArrowCursor)
    
    def close_editor(self):
        """Ferme l'éditeur"""
        self.preview_player.stop()
        self.reject()


# --- MAIN WINDOW ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1800, 1000)
        
        # Icône de l'application (créer un icône simple)
        icon_pixmap = QPixmap(64, 64)
        icon_pixmap.fill(Qt.transparent)
        painter = QPainter(icon_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Dessiner un spotlight stylisé
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4a8aaa"))
        painter.drawEllipse(12, 12, 40, 40)
        painter.setBrush(QColor("#ffdd00"))
        painter.drawPolygon(QPolygon([QPoint(32, 12), QPoint(42, 2), QPoint(52, 12)]))
        painter.end()
        
        self.setWindowIcon(QIcon(icon_pixmap))
        
        # Création des projecteurs avec nouveaux groupes
        self.projectors = []
        
        # 4 FACE
        for _ in range(4):
            self.projectors.append(Projector("face"))
        
        # 3 x 3 DOUCHES
        for _ in range(3):
            self.projectors.append(Projector("douche1"))
        for _ in range(3):
            self.projectors.append(Projector("douche2"))
        for _ in range(3):
            self.projectors.append(Projector("douche3"))
        
        # 2 LAT
        for _ in range(2):
            self.projectors.append(Projector("lat"))
        
        # 6 CONTRE (au lieu de 8)
        for _ in range(6):
            self.projectors.append(Projector("contre"))
        
        self.active_pad = None
        self.active_dual_pad = None  # Pour les pads multicouleurs
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
        
        # Configuration AKAI - Luminosités réglables
        self.akai_active_brightness = 100   # Luminosité des pads actifs (50-100%)
        self.akai_inactive_brightness = 20  # Luminosité des pads inactifs (10-50%)
        self.blackout_active = False        # État du blackout
        
        # DMX Art-Net Handler
        self.dmx = ArtNetDMX()
        
        # Patch automatique au démarrage : 1, 11, 21, 31...
        self.auto_patch_at_startup()
        
        self.dmx_send_timer = QTimer()
        self.dmx_send_timer.timeout.connect(self.send_dmx_update)
        self.dmx_send_timer.start(40)  # 25 FPS (40ms)
        
        # MIDI Handler
        self.midi_handler = MIDIHandler()
        self.midi_handler.owner_window = self  # Donner la référence
        self.midi_handler.fader_changed.connect(self.on_midi_fader)
        self.midi_handler.pad_pressed.connect(self.on_midi_pad)
        
        # Fichiers récents
        self.recent_files = self.load_recent_files()
        
        bar = self.menuBar()
        
        file = bar.addMenu("📁 Fichier")
        
        # Nouveau Show
        new_action = file.addAction("📄 Nouveau Show", self.new_show)
        new_action.setShortcut("Ctrl+N")
        
        file.addSeparator()
        
        # Ouvrir
        open_action = file.addAction("Ouvrir Show...", self.load_show)
        open_action.setShortcut("Ctrl+O")
        
        # Enregistrer
        save_action = file.addAction("Enregistrer Show", self.save_show)
        save_action.setShortcut("Ctrl+S")
        
        file.addSeparator()
        
        # Sous-menu Récents
        self.recent_menu = file.addMenu("📂 Récents")
        self.update_recent_menu()
        
        file.addSeparator()
        file.addAction("Quitter", self.close)
        
        # Menu Patch DMX
        # Patch DMX - Action directe
        bar.addAction("🔌 Patch DMX", self.show_dmx_patch_config)
        
        # REC Lumière - Action directe
        bar.addAction("🔴 REC Lumière", self.open_light_editor)
        
        # Menu Connexion (fusion AKAI + DMX)
        conn_menu = bar.addMenu("🔌 Connexion")
        conn_menu.addAction("⚙️ Assistant de connexion", self.show_connection_wizard)
        conn_menu.addSeparator()
        conn_menu.addAction("📊 État des connexions", self.show_connection_status)
        conn_menu.addSeparator()
        conn_menu.addAction("🔄 Reconnecter AKAI", self.reconnect_midi)
        conn_menu.addSeparator()
        # Supprimé: Réglages luminosité (pas utile)
        
        # Menu À propos
        about_menu = bar.addMenu("ℹ️ À propos")
        about_menu.addAction("📌 Version", self.show_version)
        about_menu.addAction("🔄 Vérifier les mises à jour", self.check_updates)

        # Action Restart directe dans la barre de menu
        bar.addAction("🔄 Restart", self.restart_application)

        # AKAI Frame
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
        self.video_frame = QFrame()
        vv = QVBoxLayout(self.video_frame)
        vv.setContentsMargins(10, 10, 10, 10)
        title = QLabel("🎬 Vidéo")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        vv.addWidget(title)
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(400)
        self.video_widget.setStyleSheet("background: #000; border: 1px solid #2a2a2a; border-radius: 6px;")
        self.player.setVideoOutput(self.video_widget)
        vv.addWidget(self.video_widget)

        # Séquenceur
        self.seq = Sequencer(self)  # Passer MainWindow directement
        self.seq.table.cellDoubleClicked.connect(self.seq.play_row)
        self.seq.table.setContextMenuPolicy(Qt.CustomContextMenu)
        # DÉSACTIVÉ : show_vol_menu (ancien système, remplacé par show_media_context_menu)
        # self.seq.table.customContextMenuRequested.connect(self.show_vol_menu)

        # Transport
        self.transport = self.create_transport_panel()

        # Timer IA et événements
        self.ai_timer = QTimer(self)
        self.ai_timer.timeout.connect(self.update_audio_ai)
        self.ai_timer.start(100)
        
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)

        # Layout principal
        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.addWidget(self.seq)
        mv.addWidget(self.transport)
        
        plan_scroll = QScrollArea()
        plan_scroll.setWidgetResizable(True)
        self.plan_de_feu = PlanDeFeu(self.projectors, self)
        plan_scroll.setWidget(self.plan_de_feu)
        plan_scroll.setStyleSheet("QScrollArea { border: none; }")
        
        right = QSplitter(Qt.Vertical)
        right.setHandleWidth(2)
        right.addWidget(plan_scroll)
        right.addWidget(self.video_frame)
        right.setStretchFactor(0, 3)  # Augmenté de 2 à 3 pour le Plan de Feu
        right.setStretchFactor(1, 2)  # Réduit de 3 à 2 pour la vidéo
        
        main_split = QSplitter(Qt.Horizontal)
        main_split.setHandleWidth(2)
        main_split.addWidget(self.akai)
        main_split.addWidget(mid)
        main_split.addWidget(right)
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 3)
        main_split.setStretchFactor(2, 2)
        
        self.setCentralWidget(main_split)
        self.player.playbackStateChanged.connect(self.update_play_icon)
        
        self.apply_styles()
        
        # Activer les PADs blancs à 100% au démarrage
        QTimer.singleShot(100, self.activate_default_white_pads)
        
        # Éteindre tous les effets au démarrage
        QTimer.singleShot(200, self.turn_off_all_effects)
        
        # Test automatique de la connexion DMX au démarrage
        QTimer.singleShot(1000, self.test_dmx_on_startup)

    def create_akai_panel(self):
        """Crée le panneau AKAI avec 8 colonnes + carré rouge par ligne + colonne effets"""
        frame = QFrame()
        frame.setFixedWidth(380)  # Réduit de 400 à 380
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(10, 10, 10, 10)
        
        title = QLabel("🎹 AKAI APC mini")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(title)
        
        # Grille de pads 8x8 + carrés rouges
        pads = QGridLayout()
        pads.setSpacing(4)
        
        base_colors = [
            QColor("white"), QColor("#ff0000"), QColor("#ff8800"), QColor("#ffdd00"), 
            QColor("#00ff00"), QColor("#00dddd"), QColor("#0000ff"), QColor("#ff00ff")
        ]
        
        color_mixes = {
            5: [
                (QColor("white"), QColor("#ff0000")),
                (QColor("#ff0000"), QColor("#ff8800")),
                (QColor("#ff8800"), QColor("#ffdd00")),
                (QColor("#ffdd00"), QColor("#00ff00")),
                (QColor("#00ff00"), QColor("#00dddd")),
                (QColor("#00dddd"), QColor("#0000ff")),
                (QColor("#0000ff"), QColor("#ff00ff")),
                (QColor("#ff00ff"), QColor("white")),
            ],
            6: [
                (QColor("white"), QColor("#ff8800")),
                (QColor("#ff0000"), QColor("#ffdd00")),
                (QColor("#ff8800"), QColor("#00ff00")),
                (QColor("#ffdd00"), QColor("#00dddd")),
                (QColor("#00ff00"), QColor("#0000ff")),
                (QColor("#00dddd"), QColor("#ff00ff")),
                (QColor("#0000ff"), QColor("white")),
                (QColor("#ff00ff"), QColor("#ff0000")),
            ],
            7: [
                (QColor("white"), QColor("#ffdd00")),
                (QColor("#ff0000"), QColor("#00ff00")),
                (QColor("#ff8800"), QColor("#00dddd")),
                (QColor("#ffdd00"), QColor("#0000ff")),
                (QColor("#00ff00"), QColor("#ff00ff")),
                (QColor("#00dddd"), QColor("white")),
                (QColor("#0000ff"), QColor("#ff0000")),
                (QColor("#ff00ff"), QColor("#ff8800")),
            ]
        }
        
        for r in range(8):
            for c in range(8):
                if c < 5:
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
                else:
                    col1, col2 = color_mixes[c][r]
                    b = DualColorButton(col1, col2)
                    b.setProperty("base_color", col1)
                    b.setProperty("color2", col2)
                    b.clicked.connect(lambda _, btn=b, col=c: self.activate_pad_dual(btn, col))
                
                pads.addWidget(b, r, c)
                self.pads[(r, c)] = b
            
            # Carré rouge à la fin de chaque ligne
            effect_btn = EffectButton(r)
            effect_btn.clicked.connect(lambda _, idx=r: self.toggle_effect(idx))
            self.effect_buttons.append(effect_btn)
            pads.addWidget(effect_btn, r, 8)
        
        layout.addLayout(pads)
        layout.addSpacing(10)
        
        # Faders + mute (8 colonnes) + fader effet
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
        
        # Dernier carré rouge + fader effet
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
        
        layout.addStretch()
        
        return frame

    def create_transport_panel(self):
        """Crée le panneau transport avec timeline"""
        frame = QFrame()
        frame.setFixedHeight(150)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Timeline avec temps
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
            QSlider::handle:horizontal:hover {
                background: #00ffff;
                border: 3px solid #00d4ff;
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
        
        # Waveform de recording (invisible par défaut)
        self.recording_waveform = RecordingWaveform()
        self.recording_waveform.setFixedHeight(30)  # Hauteur normale
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
            QToolButton:pressed {
                background: #3a3a3a;
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
        
        # Bouton REC global
        rec_style = """
            QPushButton {
                background: #1a1a1a;
                border: 2px solid #3a3a3a;
                border-radius: 8px;
                padding: 12px 20px;
                color: #666666;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #2a2a2a;
                border: 2px solid #ff4444;
                color: #ff4444;
            }
            QPushButton:checked {
                background: #ff4444;
                color: white;
                border: 2px solid #ffffff;
            }
        """
        
        # Bouton REC supprimé - remplacé par Menu → Séquence → REC Lumière
        # self.rec_btn = QPushButton("🔴 REC")
        # self.rec_btn.setFixedSize(100, 60)
        # self.rec_btn.setStyleSheet(rec_style)
        # self.rec_btn.setCheckable(True)
        # self.rec_btn.clicked.connect(self.toggle_global_recording)
        
        btns.addStretch()
        btns.addWidget(prev)
        btns.addWidget(self.play_btn)
        btns.addWidget(nxt)
        btns.addStretch()
        # btns.addWidget(self.rec_btn)  # REC supprimé
        layout.addLayout(btns)
        
        return frame

    def trigger_pause_mode(self):
        """Active le mode pause sans clignotement"""
        self.pause_mode = True
        self.player.pause()
        
        # Arrêter le timer de clignotement s'il existe
        if self.blink_timer:
            self.blink_timer.stop()
            self.blink_timer = None

    def toggle_play(self):
        if self.pause_mode:
            # Sortir du mode pause et lancer la lecture du média chargé
            if self.blink_timer:
                self.blink_timer.stop()
            self.pause_mode = False
            # Lancer la lecture du média déjà chargé (pas passer au suivant)
            self.player.play()
        elif self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()
    
    def toggle_global_recording(self, checked):
        """Gère le bouton REC global : bascule en Programme, lance le média + enregistre"""
        if checked:
            # Démarrer l'enregistrement
            current_row = self.seq.current_row
            if current_row < 0:
                current_row = self.seq.table.currentRow()
            
            if current_row < 0:
                QMessageBox.warning(self, "Aucune ligne sélectionnée",
                    "Sélectionnez d'abord une ligne dans le séquenceur")
                self.rec_btn.setChecked(False)
                return
            
            # Vérifier que c'est un média (pas pause/tempo)
            item = self.seq.table.item(current_row, 1)
            if not item or not item.data(Qt.UserRole):
                self.rec_btn.setChecked(False)
                return
            
            data = item.data(Qt.UserRole)
            if data == "PAUSE" or str(data).startswith("TEMPO:"):
                QMessageBox.warning(self, "Type invalide",
                    "Impossible d'enregistrer sur une PAUSE ou une Pause minutée")
                self.rec_btn.setChecked(False)
                return
            
            # Basculer automatiquement en mode Programme
            dmx_widget = self.seq.table.cellWidget(current_row, 4)
            if dmx_widget and isinstance(dmx_widget, QComboBox):
                if dmx_widget.currentText() != "Programme":
                    dmx_widget.setCurrentText("Programme")
                    self.seq.on_dmx_changed(current_row, "Programme")
                    print(f"🔄 Ligne {current_row} basculée en mode Programme")
            
            # BLACKOUT pour l'enregistrement (garde les pads visibles)
            print("🔲 REC → Blackout (pads visibles)")
            self.rec_blackout()
            
            # Afficher et initialiser la waveform
            self.recording_waveform.clear()
            self.recording_waveform.show()
            
            # Initialiser l'enregistrement
            self.seq.recording = True
            self.seq.recording_row = current_row
            self.seq.recording_start_time = 0
            self.seq.sequences[current_row] = {
                "keyframes": [],
                "duration": 0
            }
            
            # Timer pour enregistrer les keyframes
            if not self.seq.recording_timer:
                self.seq.recording_timer = QTimer()
                self.seq.recording_timer.timeout.connect(self.seq.record_keyframe)
            
            self.seq.recording_timer.start(500)
            print("⏱ Timer d'enregistrement démarré (500ms)")
            
            # Lancer le média depuis le début
            path = data
            vol_item = self.seq.table.item(current_row, 3)
            if vol_item:
                vol = int(vol_item.text())
                self.audio.setVolume(vol / 100)
            
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.play()
            
            print(f"🔴 REC : Ligne {current_row} - Enregistrement démarré")
        
        else:
            # Arrêter l'enregistrement
            self.stop_recording()
    
    def stop_recording(self):
        """Arrête l'enregistrement (appelé manuellement ou à la fin du média)"""
        if not self.seq.recording:
            return
        
        self.seq.recording = False
        if self.seq.recording_timer:
            self.seq.recording_timer.stop()
        
        # NE PAS masquer la waveform - la garder visible pour voir le Programme
        # self.recording_waveform.hide()
        
        # Sauvegarder la durée et la séquence
        if self.seq.recording_row >= 0 and self.seq.recording_row in self.seq.sequences:
            self.seq.sequences[self.seq.recording_row]["duration"] = self.seq.recording_start_time
            nb_keyframes = len(self.seq.sequences[self.seq.recording_row]["keyframes"])
            print(f"⏹ REC arrêté - {nb_keyframes} keyframes ({self.seq.recording_start_time/1000:.1f}s)")
            print(f"💾 Programme sauvegardé pour la ligne {self.seq.recording_row}")
            
            # Ajouter "Programme" au combo s'il n'existe pas déjà
            dmx_widget = self.seq.table.cellWidget(self.seq.recording_row, 4)
            if dmx_widget and isinstance(dmx_widget, QComboBox):
                if dmx_widget.findText("Programme") == -1:
                    dmx_widget.addItem("Programme")
                dmx_widget.setCurrentText("Programme")
                self.seq.on_dmx_changed(self.seq.recording_row, "Programme")
                print(f"✅ Mode Programme activé sur ligne {self.seq.recording_row}")
        
        self.seq.recording_row = -1
        self.seq.recording_start_time = 0
        self.seq.is_dirty = True
        
        # Décoche le bouton REC
        self.rec_btn.setChecked(False)
        
        # Pause le média
        self.player.pause()

    def update_play_icon(self, s):
        if s == QMediaPlayer.PlayingState:
            self.play_btn.setIcon(create_icon("pause", "#ffffff"))
        else:
            self.play_btn.setIcon(create_icon("play", "#ffffff"))

    def on_timeline_update(self, position):
        try:
            duration = self.player.duration()
            
            # S'assurer que le maximum est bien défini
            if duration > 0 and self.timeline.maximum() != duration:
                self.timeline.setMaximum(duration)
            
            # Ne pas dépasser le maximum
            if duration > 0:
                position = min(position, duration)
            
            self.timeline.setValue(position)
            self.time_label.setText(fmt_time(position))
            
            if duration > 0:
                remaining = duration - position
                self.remaining_label.setText(f"-{fmt_time(remaining)}")
            else:
                self.remaining_label.setText("-00:00")
            
            # Mettre à jour la waveform si en enregistrement
            if self.seq.recording and self.recording_waveform.isVisible():
                self.recording_waveform.set_position(position, duration)
        except:
            pass

    def on_media_status_changed(self, status):
        """Passe automatiquement au suivant (mode continu) ou gère les TEMPO"""
        if status == QMediaPlayer.EndOfMedia:
            # Arrêter playback timeline si actif
            if hasattr(self.seq, 'timeline_playback_timer') and self.seq.timeline_playback_timer.isActive():
                self.seq.timeline_playback_timer.stop()
                print("⏹ Fin média → Arrêt playback timeline")
            
            # Si on était en enregistrement, l'arrêter
            if self.seq.recording:
                print("⏹ Fin du média → Arrêt automatique du REC")
                self.stop_recording()
                return  # Ne pas passer au suivant pendant l'enregistrement
            
            # Vérifier si passage AUTO -> Manuel pour reset faders
            current_mode = self.seq.get_dmx_mode(self.seq.current_row)
            next_row = self.seq.current_row + 1
            
            if next_row < self.seq.table.rowCount():
                # Vérifier si c'est un TEMPO
                next_item = self.seq.table.item(next_row, 1)
                if next_item and next_item.data(Qt.UserRole) and str(next_item.data(Qt.UserRole)).startswith("TEMPO:"):
                    # C'est un TEMPO, attendre la durée spécifiée
                    seconds = int(next_item.data(Qt.UserRole).split(":")[1])
                    self.seq.current_row = next_row
                    self.seq.table.selectRow(next_row)
                    print(f"⏱ Pause minutée: Attente de {seconds} secondes...")
                    
                    # Lancer un timer pour passer au suivant
                    QTimer.singleShot(seconds * 1000, lambda: self.continue_after_tempo(next_row))
                    return
                
                next_mode = self.seq.get_dmx_mode(next_row)
                if (current_mode in ["IA Lumière", "Programme"]) and next_mode == "Manuel":
                    print("🔲 Passage en mode Manuel → Blackout complet")
                    # Blackout complet
                    self.full_blackout()
                
                # Passer au média suivant
                self.seq.play_row(next_row)
    
    def continue_after_tempo(self, tempo_row):
        """Continue la séquence après une Pause minutée"""
        next_row = tempo_row + 1
        if next_row < self.seq.table.rowCount():
            self.seq.play_row(next_row)
        else:
            print("✅ Fin de la séquence")
    
    def full_blackout(self):
        """Blackout complet : faders, projecteurs, pads, effets"""
        # Faders à 0
        for idx in range(9):
            if idx in self.faders:
                self.faders[idx].value = 0
                self.faders[idx].update()
        
        # Projecteurs éteints
        for p in self.projectors:
            p.level = 0
            p.color = QColor("black")
        
        # Désactiver tous les pads
        if self.active_pad:
            old_color = self.active_pad.property("base_color")
            dim_color = QColor(int(old_color.red() * 0.5), int(old_color.green() * 0.5), int(old_color.blue() * 0.5))
            self.active_pad.setStyleSheet(f"QPushButton {{ background: {dim_color.name()}; border: 1px solid #2a2a2a; border-radius: 4px; }}")
            self.active_pad = None
        
        if self.active_dual_pad:
            self.active_dual_pad.active = False
            self.active_dual_pad.brightness = 0.3
            self.active_dual_pad.update()
            self.active_dual_pad = None
        
        # Désactiver tous les effets
        for i, btn in enumerate(self.effect_buttons):
            if btn.active:
                btn.active = False
                btn.update_style()
        
        if self.active_effect is not None:
            self.stop_effect()
            self.active_effect = None
        
        # Éteindre l'AKAI physique (pads uniquement, pas les faders)
        if MIDI_AVAILABLE and self.midi_handler.midi_out:
            for row in range(8):
                for col in range(8):
                    self.midi_handler.set_pad_led(row, col, 0, 0)
    
    def rec_blackout(self):
        """Blackout pour REC : éteint les projecteurs MAIS garde les pads visibles"""
        # Faders à 0
        for idx in range(9):
            if idx in self.faders:
                self.faders[idx].value = 0
                self.faders[idx].update()
        
        # Projecteurs éteints
        for p in self.projectors:
            p.level = 0
            p.color = QColor("black")
        
        # On garde les pads visuellement actifs mais sans active_pad/active_dual_pad
        # Ceci permet de voir les couleurs disponibles
        self.active_pad = None
        self.active_dual_pad = None
        
        # Désactiver tous les effets
        for i, btn in enumerate(self.effect_buttons):
            if btn.active:
                btn.active = False
                btn.update_style()
        
        if self.active_effect is not None:
            self.stop_effect()
            self.active_effect = None

    def activate_pad(self, btn, col_idx):
        """Active un pad simple (colonnes 1-5)"""
        color = btn.property("base_color")
        groups = ["face", "douche1", "douche2", "douche3", "lat_contre"]
        
        if self.active_pad and self.active_pad != btn:
            old_color = self.active_pad.property("base_color")
            dim_color = QColor(int(old_color.red() * 0.5), int(old_color.green() * 0.5), int(old_color.blue() * 0.5))
            self.active_pad.setStyleSheet(f"QPushButton {{ background: {dim_color.name()}; border: 1px solid #2a2a2a; border-radius: 4px; }}")
        
        # Si on active un pad de la colonne 4 (lat_contre), désactiver le pad dual actif
        if col_idx == 4 and self.active_dual_pad:
            self.active_dual_pad.active = False
            self.active_dual_pad.brightness = 0.3
            self.active_dual_pad.update()
            self.active_dual_pad = None
        
        btn.setStyleSheet(f"QPushButton {{ background: {color.name()}; border: 2px solid {color.lighter(130).name()}; border-radius: 4px; }}")
        self.active_pad = btn
        
        # Appliquer aux projecteurs
        target_group = groups[col_idx] if col_idx < len(groups) else "face"
        for p in self.projectors:
            if p.group == target_group or (target_group == "lat_contre" and p.group in ["lat", "contre"]):
                p.base_color = color
                # Pas besoin de modifier p.color ici, le fader s'en charge
                # On stocke juste la couleur de base
                if p.level > 0:
                    # p.level est déjà entre 0-100, on l'utilise directement
                    brightness = p.level / 100.0
                    p.color = QColor(
                        int(color.red() * brightness),
                        int(color.green() * brightness),
                        int(color.blue() * brightness)
                    )

    def activate_pad_dual(self, btn, col_idx):
        """Active un pad bicolore (colonnes 6-8) avec pattern symétrique"""
        color1 = btn.property("base_color")
        color2 = btn.property("color2")
        
        # Désactiver l'ancien pad dual actif
        if self.active_dual_pad and self.active_dual_pad != btn:
            self.active_dual_pad.active = False
            self.active_dual_pad.brightness = 0.3
            self.active_dual_pad.update()
        
        # Désactiver le pad simple actif de la colonne 4 (faders 5-8)
        if self.active_pad:
            old_color = self.active_pad.property("base_color")
            dim_color = QColor(int(old_color.red() * 0.5), int(old_color.green() * 0.5), int(old_color.blue() * 0.5))
            self.active_pad.setStyleSheet(f"QPushButton {{ background: {dim_color.name()}; border: 1px solid #2a2a2a; border-radius: 4px; }}")
            self.active_pad = None
        
        # Activer/désactiver le pad cliqué
        btn.active = not btn.active
        if btn.active:
            btn.brightness = 1.0
            self.active_dual_pad = btn
        else:
            btn.brightness = 0.3
            self.active_dual_pad = None
        btn.update()
        
        # Appliquer uniquement si actif
        if btn.active:
            # Pattern exact: LAT identiques (color1), CONTRE alternés
            # LAT1=Rouge, LAT2=Rouge, CONTRE=[Blanc,Rouge,Blanc,Blanc,Rouge,Blanc]
            patterns = {
                "lat": [color1, color1],  # 2 LAT même couleur (color1 = Rouge)
                "contre": [color2, color1, color2, color2, color1, color2]  # 6 CONTRE: Blanc,Rouge,Blanc,Blanc,Rouge,Blanc
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

    def set_proj_level(self, index, value):
        """Gère les faders avec liaison 5-8 et activation auto du PAD blanc (OPTIMISÉ)"""
        if 4 <= index <= 7:
            # Faders 5-8 liés - MAJ en une seule passe
            for i in range(4, 8):
                self.faders[i].value = value
            
            # Update visuel en batch (à la fin)
            QTimer.singleShot(0, lambda: [self.faders[i].update() for i in range(4, 8)])
            
            # Si aucun PAD n'est actif et value > 0, activer le PAD blanc de la colonne 4
            if not self.active_pad and not self.active_dual_pad and value > 0:
                white_pad = self.pads.get((0, 4))
                if white_pad:
                    self.activate_pad(white_pad, 4)
            
            # Appliquer à lat et contre en une seule passe
            brightness = value / 100.0 if value > 0 else 0
            for p in self.projectors:
                if p.group in ["lat", "contre"]:
                    p.level = value
                    if value > 0:
                        p.color = QColor(
                            int(p.base_color.red() * brightness),
                            int(p.base_color.green() * brightness),
                            int(p.base_color.blue() * brightness)
                        )
                    else:
                        p.color = QColor("black")
        else:
            # Faders individuels (0-3)
            groups = ["face", "douche1", "douche2", "douche3"]
            if index < len(groups):
                target = groups[index]
                
                # Si aucun PAD n'est actif, activer le PAD blanc (ligne 0) de la bonne colonne
                if not self.active_pad and not self.active_dual_pad and value > 0:
                    white_pad = self.pads.get((0, index))
                    if white_pad:
                        # Important: utiliser directement activate_pad avec le bon index de colonne
                        color = white_pad.property("base_color")
                        
                        # Désactiver l'ancien pad actif
                        if self.active_pad and self.active_pad != white_pad:
                            old_color = self.active_pad.property("base_color")
                            dim_color = QColor(int(old_color.red() * 0.5), int(old_color.green() * 0.5), int(old_color.blue() * 0.5))
                            self.active_pad.setStyleSheet(f"QPushButton {{ background: {dim_color.name()}; border: 1px solid #2a2a2a; border-radius: 4px; }}")
                        
                        # Activer le nouveau pad
                        white_pad.setStyleSheet(f"QPushButton {{ background: {color.name()}; border: 2px solid {color.lighter(130).name()}; border-radius: 4px; }}")
                        self.active_pad = white_pad
                        
                        # Appliquer la couleur aux projecteurs
                        for p in self.projectors:
                            if p.group == target:
                                p.base_color = color
                
                for p in self.projectors:
                    if p.group == target:
                        p.level = value
                        if value > 0:
                            brightness = value / 100.0
                            p.color = QColor(
                                int(p.base_color.red() * brightness),
                                int(p.base_color.green() * brightness),
                                int(p.base_color.blue() * brightness)
                            )
                        else:
                            p.color = QColor("black")

    def toggle_mute(self, index, active):
        """Gère les mutes avec liaison 5-8"""
        print(f"🔇 Toggle mute fader {index}: {'MUTE' if active else 'UNMUTE'}")
        
        if 4 <= index <= 7:
            # Mutes 5-8 liés
            for i in range(4, 8):
                self.fader_buttons[i].active = active
                self.fader_buttons[i].update_style()
            
            muted_count = 0
            for p in self.projectors:
                if p.group in ["lat", "contre"]:
                    p.muted = active
                    muted_count += 1
            print(f"   → {muted_count} projecteurs LAT/CONTRE {'mutés' if active else 'démutés'}")
        else:
            groups = ["face", "douche1", "douche2", "douche3"]
            if index < len(groups):
                muted_count = 0
                for p in self.projectors:
                    if p.group == groups[index]:
                        p.muted = active
                        muted_count += 1
                print(f"   → {muted_count} projecteurs {groups[index]} {'mutés' if active else 'démutés'}")

    def activate_default_white_pads(self):
        """Active la première ligne (colonnes 0-4) à 100%, le reste à 20%"""
        # Activer les PADs blancs (ligne 0) à 100% dans le simulateur
        for col in range(5):
            white_pad = self.pads.get((0, col))
            if white_pad:
                color = white_pad.property("base_color")
                white_pad.setStyleSheet(f"QPushButton {{ background: {color.name()}; border: 2px solid {color.lighter(130).name()}; border-radius: 4px; }}")
        
        # Allumer physiquement TOUS les pads sur l'AKAI
        if MIDI_AVAILABLE and hasattr(self, 'midi_handler') and self.midi_handler.midi_out:
            print("💡 Allumage des pads sur l'AKAI...")
            
            for row in range(8):
                for col in range(8):
                    pad = self.pads.get((row, col))
                    if pad and col < 8:  # Pas les effets
                        # Récupérer la couleur réelle du pad
                        base_color = pad.property("base_color")
                        velocity = rgb_to_akai_velocity(base_color)
                        
                        # Première ligne (row 0) + colonnes 0-4 → 100%
                        # Reste → 20%
                        if row == 0 and col < 5:
                            brightness = 100
                        else:
                            brightness = 20
                        
                        # Allumer avec la bonne luminosité
                        note = (7 - row) * 8 + col
                        channel = 0x96 if brightness >= 80 else 0x90
                        self.midi_handler.midi_out.send_message([channel, note, velocity])
                        print(f"  Pad L{row} C{col} → {brightness}%")
            
            print("💡 Première ligne (colonnes 0-4) à 100%, reste à 20% !")
            
            # Démarrer le timer pour les pads bicolores
            self.start_bicolor_blinking()
    
    def start_bicolor_blinking(self):
        """Démarre le clignotement pour les pads bicolores actifs"""
        if not hasattr(self, 'bicolor_timer'):
            self.bicolor_timer = QTimer()
            self.bicolor_timer.timeout.connect(self.update_bicolor_pads)
            self.bicolor_state = 0
        
        if not self.bicolor_timer.isActive():
            self.bicolor_timer.start(3000)  # Toutes les 3 secondes (au lieu de 1)
    
    def update_bicolor_pads(self):
        """Alterne les couleurs des pads bicolores actifs"""
        if not MIDI_AVAILABLE or not hasattr(self, 'midi_handler') or not self.midi_handler.midi_out:
            return
        
        self.bicolor_state = 1 - self.bicolor_state  # Alterne entre 0 et 1
        
        for (row, col), pad in self.pads.items():
            if col >= 5 and col < 8:  # Colonnes bicolores
                if hasattr(pad, 'active') and pad.active:
                    # Récupérer les deux couleurs
                    color1 = pad.property("base_color")
                    color2 = pad.property("color2")
                    
                    # Alterner
                    current_color = color1 if self.bicolor_state == 0 else color2
                    velocity = rgb_to_akai_velocity(current_color)
                    
                    # Envoyer à 100% luminosité (canal 7)
                    note = (7 - row) * 8 + col
                    self.midi_handler.midi_out.send_message([0x96, note, velocity])
    
    def turn_off_all_effects(self):
        """Éteindre tous les effets au démarrage (simulateur + AKAI physique)"""
        print("🔴 Extinction de tous les effets au démarrage...")
        
        # Éteindre les boutons dans le simulateur
        for btn in self.effect_buttons:
            btn.active = False
            btn.update_style()
        
        # Éteindre les LEDs sur l'AKAI physique
        if MIDI_AVAILABLE and hasattr(self, 'midi_handler') and self.midi_handler.midi_out:
            for i in range(8):
                note = 112 + i
                # Canal 1 (0x90) pour les carrés monochromes rouges
                self.midi_handler.midi_out.send_message([0x90, note, 0])
                print(f"  Carré rouge {i+1} (note {note}) éteint")

    def toggle_effect(self, effect_idx):
        """Active/désactive un effet"""
        for i, btn in enumerate(self.effect_buttons):
            if i == effect_idx:
                btn.active = not btn.active
                if btn.active:
                    self.active_effect = effect_idx
                    self.start_effect(effect_idx)
                    # Désactiver tous les AUTRES effets
                    for j, other_btn in enumerate(self.effect_buttons):
                        if j != i and other_btn.active:
                            other_btn.active = False
                            other_btn.update_style()
                            # Éteindre la LED de l'autre effet sur l'AKAI (canal 7)
                            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                                self.midi_handler.set_pad_led(j, 8, 0)
                else:
                    self.active_effect = None
                    self.stop_effect()
            btn.update_style()
    
    def start_effect(self, effect_idx):
        """Démarre l'effet sélectionné"""
        self.effect_state = 0
        self.effect_saved_colors = {}
        
        # Sauvegarder les couleurs actuelles
        for p in self.projectors:
            self.effect_saved_colors[id(p)] = (p.base_color, p.color)
        
        if effect_idx == 0:
            # Effet 1: Stroboscope BLANC avec canal DMX strobe
            # Mettre tous les projecteurs en mode Strobe
            for p in self.projectors:
                p.dmx_mode = "Strobe"
            
            if not hasattr(self, 'effect_timer'):
                self.effect_timer = QTimer()
                self.effect_timer.timeout.connect(self.update_effect)
            self.effect_timer.start(100)  # 10 Hz par défaut
        elif effect_idx == 1:
            # Effet 2: Stroboscope COULEUR
            if not hasattr(self, 'effect_timer'):
                self.effect_timer = QTimer()
                self.effect_timer.timeout.connect(self.update_effect)
            self.effect_timer.start(100)
        elif effect_idx == 2:
            # Effet 3: Alternance 1/2
            if not hasattr(self, 'effect_timer'):
                self.effect_timer = QTimer()
                self.effect_timer.timeout.connect(self.update_effect)
            self.effect_timer.start(1000)
        elif effect_idx == 3:
            # Effet 4: Passage blanc en vague
            if not hasattr(self, 'effect_timer'):
                self.effect_timer = QTimer()
                self.effect_timer.timeout.connect(self.update_effect)
            self.effect_timer.start(200)
        elif effect_idx == 4:
            # Effet 5: Arc-en-ciel LAT & CONTRE
            if not hasattr(self, 'effect_timer'):
                self.effect_timer = QTimer()
                self.effect_timer.timeout.connect(self.update_effect)
            self.effect_hue = 0
            self.effect_timer.start(50)
        elif effect_idx == 5:
            # Effet 6: Vague de couleur
            if not hasattr(self, 'effect_timer'):
                self.effect_timer = QTimer()
                self.effect_timer.timeout.connect(self.update_effect)
            self.effect_hue = 0
            self.effect_timer.start(100)
        elif effect_idx == 6:
            # Effet 7: Clignotement aléatoire
            if not hasattr(self, 'effect_timer'):
                self.effect_timer = QTimer()
                self.effect_timer.timeout.connect(self.update_effect)
            self.effect_timer.start(150)
        elif effect_idx == 7:
            # Effet 8: Pulse (respiration)
            if not hasattr(self, 'effect_timer'):
                self.effect_timer = QTimer()
                self.effect_timer.timeout.connect(self.update_effect)
            self.effect_brightness = 0
            self.effect_direction = 1
            self.effect_timer.start(30)
    
    def stop_effect(self):
        """Arrête l'effet en cours et restaure les couleurs précédentes"""
        if hasattr(self, 'effect_timer'):
            self.effect_timer.stop()
        
        # Réinitialiser dmx_mode à Manuel
        for p in self.projectors:
            p.dmx_mode = "Manuel"
        
        # Restaurer les couleurs sauvegardées
        for p in self.projectors:
            if id(p) in self.effect_saved_colors:
                base_color, color = self.effect_saved_colors[id(p)]
                p.base_color = base_color
                p.color = color
        
        # Réappliquer les couleurs du pad actif (si il y en a un)
        if self.active_pad is not None:
            # Réappliquer le pad simple
            color = self.active_pad.property("base_color")
            col_idx = None
            # Trouver l'index de colonne
            for (r, c), pad in self.pads.items():
                if pad == self.active_pad:
                    col_idx = c
                    break
            
            if col_idx is not None:
                groups = ["face", "douche1", "douche2", "douche3", "lat_contre"]
                target_group = groups[col_idx] if col_idx < len(groups) else "face"
                for p in self.projectors:
                    if p.group == target_group or (target_group == "lat_contre" and p.group in ["lat", "contre"]):
                        p.base_color = color
                        if p.level > 0:
                            brightness = p.level / 100.0
                            p.color = QColor(
                                int(color.red() * brightness),
                                int(color.green() * brightness),
                                int(color.blue() * brightness)
                            )
        
        elif self.active_dual_pad is not None and self.active_dual_pad.active:
            # Réappliquer le pad bicolore
            color1 = self.active_dual_pad.property("base_color")
            color2 = self.active_dual_pad.property("color2")
            
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
        
        print("✅ Effet arrêté, couleurs restaurées")
    
    def update_effect(self):
        """Met à jour l'effet en cours"""
        if self.active_effect is None:
            return
        
        # Calculer l'intervalle selon le fader 9
        # effect_speed 0-100: 0 = lent (1000ms), 100 = rapide (50ms)
        if self.effect_speed == 0:
            speed_factor = 1.0  # Lent par défaut
        else:
            # Plus le fader monte, plus c'est rapide
            speed_factor = max(0.05, 1.0 - (self.effect_speed / 100.0 * 0.95))
        
        if self.active_effect == 0:
            # Stroboscope BLANC
            interval = int(100 * speed_factor)
            self.effect_timer.setInterval(interval)
            
            for p in self.projectors:
                if p.level > 0:
                    if self.effect_state % 2 == 0:
                        p.color = QColor(255, 255, 255)
                    else:
                        p.color = QColor("black")
            self.effect_state += 1
        
        elif self.active_effect == 1:
            # Stroboscope COULEUR
            interval = int(100 * speed_factor)
            self.effect_timer.setInterval(interval)
            
            for p in self.projectors:
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
        
        elif self.active_effect == 2:
            # Alternance 1/2
            interval = int(1000 * speed_factor)
            self.effect_timer.setInterval(interval)
            
            for i, p in enumerate(self.projectors):
                if p.level > 0:
                    if (i % 2 == 0 and self.effect_state % 2 == 0) or (i % 2 == 1 and self.effect_state % 2 == 1):
                        brightness = p.level / 100.0
                        p.color = QColor(
                            int(p.base_color.red() * brightness),
                            int(p.base_color.green() * brightness),
                            int(p.base_color.blue() * brightness)
                        )
                    else:
                        p.color = QColor("black")
            self.effect_state += 1
        
        elif self.active_effect == 3:
            # Passage blanc en vague
            interval = int(200 * speed_factor)
            self.effect_timer.setInterval(interval)
            
            for i, p in enumerate(self.projectors):
                if p.level > 0:
                    if i == self.effect_state % len(self.projectors):
                        p.color = QColor(255, 255, 255)
                    else:
                        brightness = p.level / 100.0
                        p.color = QColor(
                            int(p.base_color.red() * brightness),
                            int(p.base_color.green() * brightness),
                            int(p.base_color.blue() * brightness)
                        )
            self.effect_state += 1
        
        elif self.active_effect == 4:
            # Vague de couleur (décalage progressif)
            for i, p in enumerate(self.projectors):
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
        
        elif self.active_effect == 5:
            # Arc-en-ciel LAT & CONTRE
            for p in self.projectors:
                if p.group in ["lat", "contre"] and p.level > 0:
                    color = QColor.fromHsv(self.effect_hue % 360, 255, 255)
                    brightness = p.level / 100.0
                    p.color = QColor(
                        int(color.red() * brightness),
                        int(color.green() * brightness),
                        int(color.blue() * brightness)
                    )
            self.effect_hue += int(10 * (1 + self.effect_speed / 30))
        
        elif self.active_effect == 6:
            # Clignotement aléatoire
            interval = int(150 * speed_factor)
            self.effect_timer.setInterval(interval)
            
            for p in self.projectors:
                if p.level > 0:
                    if random.random() > 0.5:
                        brightness = p.level / 100.0
                        p.color = QColor(
                            int(p.base_color.red() * brightness),
                            int(p.base_color.green() * brightness),
                            int(p.base_color.blue() * brightness)
                        )
                    else:
                        p.color = QColor("black")
        
        elif self.active_effect == 7:
            # Pulse (respiration)
            for p in self.projectors:
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

    def toggle_effect_old(self, effect_idx):
        """ANCIENNE VERSION - À SUPPRIMER"""
        pass

    def set_effect_speed(self, index, value):
        """Définit la vitesse et l'intensité de l'effet"""
        self.effect_speed = value
        print(f"⚡ Effect Speed Master: {value}%")
        
        # Mettre à jour l'intervalle du timer d'effet en temps réel
        if self.effect_timer and self.effect_timer.isActive():
            # Recalculer l'intervalle
            if self.effect_speed == 0:
                speed_factor = 1.0
            else:
                speed_factor = max(0.05, 1.0 - (self.effect_speed / 100.0 * 0.95))
            
            # Appliquer selon le type d'effet
            if self.active_effect in [0, 1]:  # Strobes
                interval = int(100 * speed_factor)
            elif self.active_effect == 2:  # Alternance
                interval = int(1000 * speed_factor)
            elif self.active_effect == 3:  # Passage blanc
                interval = int(200 * speed_factor)
            elif self.active_effect == 6:  # Clignotement aléatoire
                interval = int(150 * speed_factor)
            else:
                interval = 50  # Défaut pour effets continus
            
            self.effect_timer.setInterval(interval)
            print(f"   → Timer interval: {interval}ms (factor: {speed_factor:.2f})")

    def update_audio_ai(self):
        """IA Lumière - Analyse musicale et pilotage intelligent"""
        try:
            # Mode IA Lumière
            if self.seq.current_row >= 0:
                dmx_mode = self.seq.get_dmx_mode(self.seq.current_row)
                if dmx_mode == "IA Lumière" and self.player.playbackState() == QMediaPlayer.PlayingState:
                    # Analyse audio
                    volume = self.audio.volume()
                    elapsed = self.player.position()
                    duration = self.player.duration()
                    
                    # Détection d'énergie (0-100)
                    energy = min(100, int(volume * 150))
                    
                    # === INTRO (3 premières secondes) ===
                    if elapsed < 3000:
                        fade = elapsed / 3000.0
                        # Monte progressivement la face en blanc
                        face_level = int(80 * fade)
                        for idx in range(4):  # FACE
                            self.faders[idx].value = face_level
                            self.set_proj_level(idx, face_level)
                            self.faders[idx].update()
                        
                        # Active le pad blanc si pas déjà fait
                        if not self.active_pad and elapsed > 500:
                            white_pad = self.pads.get((0, 0))  # Blanc face
                            if white_pad:
                                self.activate_pad(white_pad, 0)
                                # LED AKAI
                                if MIDI_AVAILABLE and self.midi_handler.midi_out:
                                    velocity = rgb_to_akai_velocity(white_pad.property("base_color"))
                                    self.midi_handler.set_pad_led(0, 0, velocity, 100)
                    
                    # === OUTRO (3 dernières secondes) ===
                    elif duration > 0 and (duration - elapsed) < 3000:
                        fade = (duration - elapsed) / 3000.0
                        # Descend tout progressivement
                        for idx in range(8):
                            current = self.faders[idx].value
                            target = int(current * fade)
                            self.faders[idx].value = target
                            self.set_proj_level(idx, target)
                            self.faders[idx].update()
                    
                    # === CORPS DU SON ===
                    else:
                        # Temps écoulé en secondes
                        elapsed_sec = elapsed / 1000.0
                        
                        # Changement de couleur toutes les 4 secondes (plus fréquent)
                        if int(elapsed_sec) % 4 == 0 and (elapsed % 1000) < 200:
                            # Probabilité d'utiliser un pad bicolore (60%)
                            use_bicolor = random.random() < 0.6
                            
                            if use_bicolor:
                                # Colonnes 5-7 = pads bicolores
                                row = random.randint(0, 7)
                                col = random.randint(5, 7)
                                pad = self.pads.get((row, col))
                                if pad and isinstance(pad, DualColorButton):
                                    self.activate_pad_dual(pad, col)
                                    # LED AKAI bicolore
                                    if MIDI_AVAILABLE and self.midi_handler.midi_out:
                                        velocity = rgb_to_akai_velocity(pad.property("base_color"))
                                        self.midi_handler.set_pad_led(row, col, velocity, 100)
                            else:
                                # Pad simple (colonnes 0-4)
                                row = random.randint(1, 7)  # Éviter ligne 0 (blanc)
                                col = 4  # Colonne lat/contre
                                pad = self.pads.get((row, col))
                                if pad:
                                    self.activate_pad(pad, col)
                                    if MIDI_AVAILABLE and self.midi_handler.midi_out:
                                        velocity = rgb_to_akai_velocity(pad.property("base_color"))
                                        self.midi_handler.set_pad_led(row, col, velocity, 100)
                        
                        # Pilotage selon l'énergie - FOCUS CONTRES/LAT
                        if energy > 70:
                            # SON ÉNERGIQUE - CONTRES/LAT dominent !
                            face_level = 70  # Face en support
                            douche_level = 50  # Douches discrètes
                            contre_lat_level = 90 + int((energy - 70) * 0.33)  # 90-100 !
                            
                            # Variation forte sur contres/lat pour effet dynamique
                            contre_lat_variation = random.randint(-15, 15)
                            
                            # Activer des effets parfois
                            if random.random() < 0.08 and self.active_effect is None:
                                effect_idx = random.choice([0, 1, 2, 6])  # Strobe, alternance
                                self.toggle_effect(effect_idx)
                        
                        elif energy > 40:
                            # SON MOYEN - CONTRES/LAT actifs + Face
                            face_level = 75
                            douche_level = 55
                            contre_lat_level = 75 + int((energy - 40) * 0.5)  # 75-90
                            contre_lat_variation = random.randint(-10, 10)
                        
                        else:
                            # SON CALME - Ambiance douce, Contres/Lat subtils
                            face_level = 65
                            douche_level = 45
                            contre_lat_level = 50 + int(energy * 0.5)  # 50-70
                            contre_lat_variation = random.randint(-5, 5)
                        
                        # Face (0-3) - Variation légère
                        face_variation = random.randint(-3, 3)
                        for idx in range(4):
                            target = min(100, max(0, face_level + face_variation))
                            self.faders[idx].value = target
                            self.set_proj_level(idx, target)
                            self.faders[idx].update()
                        
                        # CONTRES + LAT (faders 4-7 liés) - FOCUS ICI
                        target = min(100, max(0, contre_lat_level + contre_lat_variation))
                        self.faders[4].value = target
                        self.set_proj_level(4, target)
                        for idx in range(4, 8):
                            self.faders[idx].update()
                        
                        # Douches - Variation individuelle pour diversité
                        for idx, douche_group in enumerate(["douche1", "douche2", "douche3"]):
                            douche_target = min(100, max(0, douche_level + random.randint(-8, 8)))
                            for p in self.projectors:
                                if p.group == douche_group:
                                    p.level = douche_target
                                    brightness = douche_target / 100.0
                                    p.color = QColor(
                                        int(p.base_color.red() * brightness),
                                        int(p.base_color.green() * brightness),
                                        int(p.base_color.blue() * brightness)
                                    )
        
        except Exception as e:
            print(f"Erreur IA Lumière: {e}")

    def play_path(self, path):
        try:
            self.player.setSource(QUrl.fromLocalFile(path))
            
            # Connecter le signal de durée
            try:
                self.player.durationChanged.disconnect()
            except:
                pass
            
            row = self.seq.current_row
            self.player.durationChanged.connect(lambda d: self.update_duration_display(d, row))
            
            self.player.play()
        except Exception as e:
            print(f"Erreur play: {e}")
    
    def update_duration_display(self, duration_ms, row):
        """Met à jour l'affichage de la durée dans le séquenceur"""
        if row >= 0 and duration_ms > 0:
            minutes = duration_ms // 60000
            seconds = (duration_ms % 60000) // 1000
            dur_text = f"{minutes:02d}:{seconds:02d}"
            
            dur_item = self.seq.table.item(row, 2)
            if dur_item:
                dur_item.setText(dur_text)
                print(f"✅ Durée mise à jour: {dur_text} pour ligne {row}")

    def show_vol_menu(self, pos):
        idx = self.seq.table.indexAt(pos)
        if idx.isValid():
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { background: #1a1a1a; border: 1px solid #2a2a2a; }")
            f = ApcFader(idx.row(), self.seq.set_volume, True)
            vol_item = self.seq.table.item(idx.row(), 3)
            if vol_item and vol_item.text() != "--":
                f.value = int(vol_item.text()) * 1.27
            wa = QWidgetAction(menu)
            wa.setDefaultWidget(f)
            menu.addAction(wa)
            menu.exec(self.seq.table.viewport().mapToGlobal(pos))

    def new_show(self):
        """Crée un nouveau show (vide le séquenceur)"""
        self.clear_sequence()
    
    def clear_sequence(self):
        if self.seq.table.rowCount() == 0:
            QMessageBox.information(self, "Programme vide", "La séquence est déjà vide.")
            return
            
        if self.seq.is_dirty:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("⚠️ Vider la séquence")
            msg.setText("Attention ! Vous allez supprimer tous les médias de la séquence.")
            msg.setInformativeText("Voulez-vous sauvegarder avant de vider ?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            msg.setDefaultButton(QMessageBox.Cancel)
            res = msg.exec()
            
            if res == QMessageBox.Yes:
                if not self.save_show():
                    return
            elif res == QMessageBox.Cancel:
                return
        else:
            res = QMessageBox.question(
                self,
                "⚠️ Vider la séquence",
                "Voulez-vous vraiment supprimer tous les médias ?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.No:
                return
        
        self.seq.clear_sequence()

    def save_show(self):
        path, _ = QFileDialog.getSaveFileName(self, "Sauvegarder Show", "", "TUI Show (*.tui)")
        if not path:
            return False
        data = []
        for r in range(self.seq.table.rowCount()):
            path_item = self.seq.table.item(r, 1)
            vol_item = self.seq.table.item(r, 3)
            
            # Vérifier si c'est une pause
            if path_item and path_item.data(Qt.UserRole) == "PAUSE":
                data.append({
                    'type': 'pause',
                    'p': 'PAUSE',
                    'v': '--'
                })
            # Vérifier si c'est un TEMPO
            elif path_item and str(path_item.data(Qt.UserRole)).startswith("TEMPO:"):
                tempo_data = str(path_item.data(Qt.UserRole))
                seconds = tempo_data.split(":")[1]
                dmx_widget = self.seq.table.cellWidget(r, 4)
                dmx_mode = self.seq.get_dmx_mode(r)
                data.append({
                    'type': 'tempo',
                    'duration': seconds,
                    'd': dmx_mode
                })
            else:
                dmx_widget = self.seq.table.cellWidget(r, 4)
                if path_item and vol_item and dmx_widget:
                    dmx_mode = self.seq.get_dmx_mode(r)
                    row_data = {
                        'type': 'media',
                        'p': path_item.data(Qt.UserRole),
                        'v': vol_item.text(),
                        'd': dmx_mode
                    }
                    
                    # Sauvegarder la séquence si elle existe
                    if r in self.seq.sequences:
                        sequence = self.seq.sequences[r]
                        # Convertir les QColor en strings pour JSON
                        keyframes_json = []
                        for kf in sequence["keyframes"]:
                            kf_copy = kf.copy()
                            if kf_copy.get("active_pad"):
                                # La couleur est déjà en string
                                pass
                            keyframes_json.append(kf_copy)
                        
                        row_data['sequence'] = {
                            'keyframes': keyframes_json,
                            'duration': sequence['duration']
                        }
                    
                    data.append(row_data)
        
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            self.seq.is_dirty = False
            self.add_recent_file(path)
            print(f"💾 Show sauvegardé : {path}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder: {e}")
            return False

    def load_show(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Ouvrir Show", "", "TUI Show (*.tui)")
        if not path:
            return
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            self.seq.table.setRowCount(0)
            self.seq.sequences = {}  # Réinitialiser les séquences
            
            for item in data:
                if item.get('type') == 'pause':
                    self.seq.add_pause()
                elif item.get('type') == 'tempo':
                    # Ajouter un tempo
                    self.seq.add_tempo()
                    row = self.seq.table.rowCount() - 1
                    
                    # Restaurer la durée
                    tempo_seconds = int(item.get('duration', '10'))
                    tempo_item = self.seq.table.item(row, 1)
                    if tempo_item:
                        tempo_item.setData(Qt.UserRole, f"TEMPO:{tempo_seconds}")
                    
                    dur_item = self.seq.table.item(row, 2)
                    if dur_item:
                        dur_item.setText(f"00:{tempo_seconds:02d}")
                    
                    # Restaurer DMX
                    dmx_widget = self.seq.table.cellWidget(row, 4)
                    if dmx_widget and 'd' in item:
                        # Chercher le QComboBox dans le container
                        for i in range(dmx_widget.layout().count() if hasattr(dmx_widget, 'layout') else 0):
                            w = dmx_widget.layout().itemAt(i).widget()
                            if isinstance(w, QComboBox):
                                w.setCurrentText(item['d'])
                                break
                else:
                    # Ajouter média
                    self.seq.add_files([item['p']])
                    row = self.seq.table.rowCount() - 1
                    
                    # Restaurer volume
                    vol_item = self.seq.table.item(row, 3)
                    if vol_item:
                        vol_item.setText(item.get('v', '100'))
                    
                    # Restaurer DMX et déclencher on_dmx_changed
                    if 'd' in item:
                        self.seq.on_dmx_changed(row, item['d'])
                    
                    # Restaurer la séquence si elle existe
                    if 'sequence' in item:
                        seq_data = item['sequence']
                        self.seq.sequences[row] = {
                            'keyframes': seq_data['keyframes'],
                            'duration': seq_data['duration']
                        }
                        print(f"📼 Programme chargée ligne {row} : {len(seq_data['keyframes'])} keyframes")
            
            self.seq.is_dirty = False
            self.add_recent_file(path)
            print(f"📂 Show chargé : {path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger: {e}")
            print(f"Erreur chargement: {e}")
    
    def load_recent_files(self):
        """Charge la liste des fichiers récents depuis un fichier JSON"""
        try:
            recent_path = os.path.join(os.path.expanduser("~"), ".maestro_recent.json")
            if os.path.exists(recent_path):
                with open(recent_path, 'r') as f:
                    return json.load(f)
        except:
            pass
        return []
    
    def save_recent_files(self):
        """Sauvegarde la liste des fichiers récents"""
        try:
            recent_path = os.path.join(os.path.expanduser("~"), ".maestro_recent.json")
            with open(recent_path, 'w') as f:
                json.dump(self.recent_files, f)
        except:
            pass
    
    def add_recent_file(self, filepath):
        """Ajoute un fichier à la liste des récents"""
        # Enlever le fichier s'il existe déjà
        if filepath in self.recent_files:
            self.recent_files.remove(filepath)
        
        # Ajouter en premier
        self.recent_files.insert(0, filepath)
        
        # Garder seulement les 10 derniers
        self.recent_files = self.recent_files[:10]
        
        # Sauvegarder
        self.save_recent_files()
        
        # Mettre à jour le menu
        self.update_recent_menu()
    
    def update_recent_menu(self):
        """Met à jour le menu des fichiers récents"""
        self.recent_menu.clear()
        
        if not self.recent_files:
            action = self.recent_menu.addAction("(Aucun fichier récent)")
            action.setEnabled(False)
            return
        
        for filepath in self.recent_files:
            if os.path.exists(filepath):
                filename = os.path.basename(filepath)
                action = self.recent_menu.addAction(f"📄 {filename}")
                # Fix closure: utiliser functools.partial ou créer une vraie fonction
                action.setData(filepath)  # Stocker le chemin dans l'action
                action.triggered.connect(self.load_recent_file)
    
    def load_recent_file(self):
        """Charge un fichier depuis le menu récent"""
        action = self.sender()
        if action:
            filepath = action.data()
            self.load_show(filepath)


    def on_midi_fader(self, fader_idx, value):
        """Réception d'un mouvement de fader MIDI"""
        # Convertir la valeur MIDI (0-127) en valeur logicielle (0-100)
        converted_value = int((value / 127.0) * 100)
        
        # Fader 9 (index 8) = Master Effect Speed
        if fader_idx == 8:
            self.set_effect_speed(fader_idx, converted_value)
            if fader_idx in self.faders:
                self.faders[fader_idx].value = converted_value
                self.faders[fader_idx].update()
        # Faders 1-8 (index 0-7) = Projecteurs
        elif 0 <= fader_idx <= 7:
            self.set_proj_level(fader_idx, converted_value)
            # Mettre à jour le fader visuel
            if fader_idx in self.faders:
                self.faders[fader_idx].value = converted_value
                self.faders[fader_idx].update()
    
    def toggle_blackout_from_midi(self):
        """Toggle le blackout depuis le bouton 9 de l'AKAI"""
        self.blackout_active = not self.blackout_active
        
        print(f"⚫ BLACKOUT {'ACTIVÉ' if self.blackout_active else 'DÉSACTIVÉ'}")
        
        if self.blackout_active:
            # BLACKOUT ON: Éteindre tous les projecteurs UNIQUEMENT
            for proj in self.projectors:
                proj.r = 0
                proj.g = 0
                proj.b = 0
                proj.level = 0
            
            # Allumer le bouton blackout en rouge (ne pas toucher aux pads)
            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                self.midi_handler.midi_out.send_message([0x90, 122, 3])
        else:
            # BLACKOUT OFF: Juste remettre les niveaux des faders
            # NE PAS réactiver les pads blancs automatiquement
            for i, fader in self.faders.items():
                if i < 8:  # Pas le fader d'effet
                    self.set_proj_level(i, fader.value)
            
            # Éteindre le bouton blackout
            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                self.midi_handler.midi_out.send_message([0x90, 122, 0])
    
    def toggle_fader_mute_from_midi(self, fader_idx):
        """Toggle le mute d'un fader depuis l'AKAI physique (carrés du bas)"""
        # Le fader 9 (index 8) n'est plus géré ici, c'est le blackout
        if fader_idx == 8:
            return
        
        if 0 <= fader_idx < len(self.fader_buttons):
            btn = self.fader_buttons[fader_idx]
            
            # Groupement des boutons 5, 6, 7, 8 (indices 4, 5, 6, 7)
            # Tous s'allument ou s'éteignent ENSEMBLE
            if 4 <= fader_idx <= 7:
                # Inverser l'état du groupe entier
                new_state = not btn.active
                for i in range(4, 8):
                    self.fader_buttons[i].active = new_state
                    self.fader_buttons[i].update_style()
                    self.toggle_mute(i, new_state)
                    # Allumer/éteindre tous les LEDs sur l'AKAI
                    if MIDI_AVAILABLE and self.midi_handler.midi_out:
                        note = 100 + i
                        velocity = 3 if new_state else 0
                        # Canal 1 (0x90) pour les carrés monochromes
                        self.midi_handler.midi_out.send_message([0x90, note, velocity])
                print(f"🔇 Groupe faders 5-8 {'muté' if new_state else 'démuté'} depuis AKAI")
                return
            
            # Pour les autres faders (1-4 et 9), comportement normal
            btn.active = not btn.active
            btn.update_style()
            self.toggle_mute(fader_idx, btn.active)
            print(f"🔇 Fader {fader_idx+1} {'muté' if btn.active else 'démuté'} depuis AKAI")
            
            # Allumer/éteindre le carré du bas sur l'AKAI (sauf le 9 qui est blackout)
            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                note = 100 + fader_idx  # Boutons 1-8 = notes 100-107
                velocity = 3 if btn.active else 0
                print(f"💡 DEBUG: Envoi LED note {note}, vélocité {velocity}, canal 1")
                # Canal 1 (0x90) pour les carrés monochromes rouges
                self.midi_handler.midi_out.send_message([0x90, note, velocity])
                print(f"💡 LED note {note} {'allumée' if velocity > 0 else 'éteinte'} (canal 1)")
    
    def on_midi_pad(self, row, col):
        """Réception d'un appui de pad MIDI"""
        # Colonne 8 = boutons effets (carrés rouges) - PAS de pad virtuel
        if col == 8:
            print(f"🔴 Carré rouge {row+1} détecté, activation effet...")
            self.toggle_effect(row)
            # Allumer/éteindre le carré rouge avec vélocité 3
            if MIDI_AVAILABLE and self.midi_handler.midi_out:
                velocity = 1 if self.effect_buttons[row].active else 0
                self.midi_handler.set_pad_led(row, col, velocity, brightness_percent=100)
                print(f"🔴 Carré rouge {row+1} (note {112+row}) {'allumé' if velocity > 0 else 'éteint'}")
            return
        
        # Pour les autres colonnes, chercher le pad virtuel
        pad = self.pads.get((row, col))
        if pad:
            if col < 5:
                # Désactiver tous les autres pads de la MÊME COLONNE
                for r in range(8):
                    if r != row:
                        other_pad = self.pads.get((r, col))
                        if other_pad:
                            # Remettre à 20%
                            other_color = other_pad.property("base_color")
                            other_velocity = rgb_to_akai_velocity(other_color)
                            self.midi_handler.set_pad_led(r, col, other_velocity, brightness_percent=20)
                
                # Activer le pad cliqué
                self.activate_pad(pad, col)
                # Allumer la LED du pad sur l'AKAI à 100% avec sa vraie couleur
                if MIDI_AVAILABLE and self.midi_handler.midi_out:
                    base_color = pad.property("base_color")
                    velocity = rgb_to_akai_velocity(base_color)
                    self.midi_handler.set_pad_led(row, col, velocity, brightness_percent=100)
                    print(f"💡 Pad L{row} C{col} → {base_color.name()} → vélocité {velocity} (100%)")
            elif col < 8:
                # Désactiver tous les autres pads de la MÊME COLONNE
                for r in range(8):
                    if r != row:
                        other_pad = self.pads.get((r, col))
                        if other_pad and hasattr(other_pad, 'active'):
                            other_pad.active = False
                            # Remettre à 20%
                            other_color = other_pad.property("base_color")
                            other_velocity = rgb_to_akai_velocity(other_color)
                            self.midi_handler.set_pad_led(r, col, other_velocity, brightness_percent=20)
                
                # Activer le pad bicolore cliqué
                self.activate_pad_dual(pad, col)
                # LED bicolore - démarrer le clignotement
                if MIDI_AVAILABLE and self.midi_handler.midi_out:
                    color1 = pad.property("base_color")
                    velocity = rgb_to_akai_velocity(color1)
                    self.midi_handler.set_pad_led(row, col, velocity, brightness_percent=100)
                    print(f"💡 Pad bicolore L{row} C{col} activé (clignotement démarré)")
    
    def toggle_debug_midi(self):
        """Active/désactive le mode debug MIDI"""
        self.midi_debug_mode = not self.midi_debug_mode
        self.debug_action.setChecked(self.midi_debug_mode)
        
        if hasattr(self, 'midi_handler'):
            self.midi_handler.debug_mode = self.midi_debug_mode
        
        if self.midi_debug_mode:
            print("\n" + "="*60)
            print("🔍 MODE DEBUG MIDI ACTIVÉ")
            print("="*60)
            print("Tous les messages MIDI seront affichés dans la console.")
            print("Appuyez sur les pads et bougez les faders pour voir les messages.")
            print("Pour désactiver: Menu AKAI → Mode Debug MIDI")
            print("="*60 + "\n")
            QMessageBox.information(self, "Mode Debug MIDI", 
                "🔍 Mode Debug activé !\n\n"
                "Tous les messages MIDI seront affichés\n"
                "dans la console (terminal).\n\n"
                "Appuyez sur les pads et carrés rouges de votre AKAI\n"
                "pour voir les numéros de notes.\n\n"
                "Regardez la console pour les détails !")
        else:
            print("\n🔍 Mode Debug MIDI désactivé\n")
    
    def test_leds(self):
        """Test des LEDs de l'AKAI"""
        if not MIDI_AVAILABLE or not self.midi_handler.midi_out:
            QMessageBox.warning(self, "Test impossible", 
                "L'AKAI n'est pas connecté (sortie MIDI).")
            return
        
        print("\n💡 Test des LEDs AKAI...")
        
        # Test toutes les couleurs sur la première ligne
        colors = [0, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29,
                  31, 33, 35, 37, 39, 41, 43, 45, 47, 49, 51, 53, 55, 57, 59,
                  61, 63, 65, 67, 69, 71, 73, 75, 77, 79, 81, 83, 85, 87, 89,
                  91, 93, 95, 97, 99, 101, 103, 105, 107, 109, 111, 113, 115, 117, 119, 121, 123, 125, 127]
        
        # Tester chaque pad de la première ligne avec différentes couleurs
        for col in range(8):
            for color in [0, 1, 3, 5, 7, 9, 13, 17, 21, 25, 29, 33, 41, 49, 53, 57, 61, 65, 69, 73, 77, 81, 85, 89, 93, 97, 101, 105, 109, 113, 117, 121, 125]:
                note = 56 + col  # Ligne du haut
                self.midi_handler.midi_out.send_message([0x90, note, color])
                QTimer.singleShot(100 * col, lambda: None)  # Petit délai
        
        QMessageBox.information(self, "Test LEDs", 
            "Test des LEDs lancé !\n\n"
            "Regardez votre AKAI, la première ligne\n"
            "devrait s'allumer avec différentes couleurs.\n\n"
            "Valeurs testées : 0-127\n"
            "Regardez la console pour voir les couleurs.")
    
    def test_rainbow(self):
        """Test arc-en-ciel sur tous les pads"""
        if not MIDI_AVAILABLE or not self.midi_handler.midi_out:
            QMessageBox.warning(self, "Test impossible", 
                "L'AKAI n'est pas connecté (sortie MIDI).")
            return
        
        print("\n🌈 Test Arc-en-ciel sur l'AKAI...")
        
        # Couleurs AKAI connues (documentation):
        # 0=Off, 1=Vert, 3=Rouge, 5=Jaune, 7=Vert clair
        # 9=Orange, 11=Jaune clair, 13=Vert lime, etc.
        
        colors = [1, 3, 5, 7, 9, 13, 17, 21]  # 8 couleurs différentes
        
        # Allumer chaque ligne avec une couleur différente
        for row in range(8):
            color = colors[row]
            for col in range(8):
                note = (7 - row) * 8 + col
                self.midi_handler.midi_out.send_message([0x90, note, color])
                print(f"LED Note {note} (Ligne {row}, Col {col}) → Couleur {color}")
        
        # Allumer les carrés rouges aussi
        for row in range(8):
            note = 82 + row
            self.midi_handler.midi_out.send_message([0x90, note, 3])  # Rouge
            print(f"LED Carré rouge {row+1} (Note {note}) → Rouge")
        
        QMessageBox.information(self, "Test Arc-en-ciel", 
            "🌈 Arc-en-ciel affiché !\n\n"
            "Votre AKAI devrait s'allumer en couleurs.\n"
            "Chaque ligne a une couleur différente.\n\n"
            "Regardez la console pour les détails.")
    
    def test_red_squares(self):
        """Test spécifique des carrés rouges avec tous les types de messages"""
        if not MIDI_AVAILABLE or not self.midi_handler.midi_out:
            QMessageBox.warning(self, "Test impossible", 
                "L'AKAI n'est pas connecté (sortie MIDI).")
            return
        
        print("\n🔴 TEST DÉTAILLÉ DES CARRÉS ROUGES")
        print("="*60)
        print("Test LENT pour bien observer")
        print("="*60)
        
        msg = "🔴 Test des Carrés Rouges\n\n"
        msg += "Test LENT avec vélocité 3\n"
        msg += "sur différentes notes.\n\n"
        msg += "Regardez votre AKAI !\n"
        msg += "Le test dure 1 minute.\n\n"
        msg += "Cliquez OK pour commencer..."
        
        QMessageBox.information(self, "Test Carrés Rouges", msg)
        
        import time
        
        # TEST 1: Notes 82-89 avec vélocité 3 (LENT)
        print("\n--- TEST 1: Notes 82-89 (Note On) vélocité 3 ---")
        for i in range(8):
            note = 82 + i
            print(f"Carré {i+1}: Note {note} vélocité 3")
            self.midi_handler.midi_out.send_message([0x90, note, 3])
            time.sleep(2)  # 2 secondes pour bien voir
            self.midi_handler.midi_out.send_message([0x90, note, 0])
            time.sleep(0.5)
        
        print("\n--- TEST 2: Notes 98-105 (Note On) vélocité 3 ---")
        for i in range(8):
            note = 98 + i
            print(f"Carré {i+1}: Note {note} vélocité 3")
            self.midi_handler.midi_out.send_message([0x90, note, 3])
            time.sleep(2)
            self.midi_handler.midi_out.send_message([0x90, note, 0])
            time.sleep(0.5)
        
        print("\n--- TEST 3: Notes 112-119 (Note On) vélocité 3 ---")
        for i in range(8):
            note = 112 + i
            print(f"Carré {i+1}: Note {note} vélocité 3")
            self.midi_handler.midi_out.send_message([0x90, note, 3])
            time.sleep(2)
            self.midi_handler.midi_out.send_message([0x90, note, 0])
            time.sleep(0.5)
        
        print("\n" + "="*60)
        print("Test terminé !")
        print("Quelles notes ont allumé les carrés rouges ?")
        print("82-89 ? 98-105 ? 112-119 ?")
        print("="*60)
        
        QMessageBox.information(self, "Test terminé", 
            "Test terminé !\n\n"
            "Quelles notes ont allumé les carrés ?\n"
            "- 82-89 ?\n"
            "- 98-105 ?\n"
            "- 112-119 ?")
    
    def test_brightness_levels(self):
        """Test de différents modes et canaux pour contrôler la luminosité"""
        if not MIDI_AVAILABLE or not self.midi_handler.midi_out:
            QMessageBox.warning(self, "Test impossible", 
                "L'AKAI n'est pas connecté (sortie MIDI).")
            return
        
        print("\n🔆 TEST COMPLET LUMINOSITÉ AKAI APC MINI")
        print("="*60)
        print("L'AKAI APC mini a 2 modes de LED:")
        print("1. Mode Normal: Vélocité = couleur (pas luminosité)")
        print("2. Mode LED: Bit 7 de la vélocité contrôle clignotement")
        print("="*60)
        
        msg = "🔆 Test Luminosité AKAI\n\n"
        msg += "IMPORTANT: Sur l'AKAI APC mini,\n"
        msg += "la vélocité contrôle la COULEUR,\n"
        msg += "PAS la luminosité.\n\n"
        msg += "Ce test va essayer différentes méthodes\n"
        msg += "pour augmenter la luminosité.\n\n"
        msg += "Regardez votre AKAI pendant 20 secondes.\n"
        msg += "Cliquez OK pour commencer..."
        
        QMessageBox.information(self, "Test Luminosité", msg)
        
        import time
        
        # TEST 1: Vélocités normales (couleurs)
        print("\n--- TEST 1: Couleurs standard (rouge) ---")
        velocities = [1, 3, 5, 7, 9, 13, 17, 21, 25]  # Différentes nuances de rouge
        for v in velocities:
            print(f"Vélocité {v}")
            for col in range(8):
                self.midi_handler.midi_out.send_message([0x90, 56 + col, v])
            time.sleep(1)
        
        # Éteindre
        for col in range(8):
            self.midi_handler.midi_out.send_message([0x90, 56 + col, 0])
        time.sleep(0.5)
        
        # TEST 2: Mode LED avec bit 7 (clignotement)
        print("\n--- TEST 2: Mode clignotement (bit 7 = 1) ---")
        # Vélocités avec bit 7 à 1 (128+)
        for v in [128+3, 128+5, 128+9]:
            print(f"Vélocité {v} (mode clignotant)")
            for col in range(8):
                self.midi_handler.midi_out.send_message([0x90, 56 + col, v])
            time.sleep(2)
        
        # Éteindre
        for col in range(8):
            self.midi_handler.midi_out.send_message([0x90, 56 + col, 0])
        time.sleep(0.5)
        
        # TEST 3: Tous les pads au maximum
        print("\n--- TEST 3: Toutes les couleurs vives simultanément ---")
        colors = [5, 9, 13, 17, 21, 25, 49, 53]  # 8 couleurs différentes
        for row in range(8):
            for col in range(8):
                note = (7 - row) * 8 + col
                self.midi_handler.midi_out.send_message([0x90, note, colors[row]])
        time.sleep(3)
        
        print("\n" + "="*60)
        print("Test terminé !")
        print("="*60)
        print("CONCLUSION:")
        print("- L'AKAI APC mini a une luminosité FIXE par LED")
        print("- La vélocité contrôle la COULEUR, pas la luminosité")
        print("- Il n'y a pas de réglage de luminosité par logiciel")
        print("- La luminosité dépend de la couleur choisie")
        print("="*60)
        
        QMessageBox.information(self, "Test terminé", 
            "Test terminé !\n\n"
            "CONCLUSION:\n"
            "L'AKAI APC mini n'a PAS de contrôle\n"
            "de luminosité par logiciel.\n\n"
            "La vélocité change la COULEUR,\n"
            "pas la luminosité.\n\n"
            "Chaque LED a une luminosité fixe.\n"
            "Certaines couleurs paraissent plus vives\n"
            "(rouge=3, jaune=5, orange=9).")
    
    def reconnect_midi(self):
        """Force la reconnexion MIDI et restaure les couleurs"""
        if not MIDI_AVAILABLE:
            QMessageBox.information(self, "MIDI non disponible", 
                "Le support MIDI n'est pas activé.\n\n"
                "Pour activer le MIDI, installez python-rtmidi.")
            return
        
        try:
            print("🔄 Reconnexion MIDI manuelle...")
            self.midi_handler.connect_akai()
            
            if self.midi_handler.midi_in and self.midi_handler.midi_out:
                # Réactiver les pads blancs par défaut
                QTimer.singleShot(200, self.activate_default_white_pads)
                
                # Restaurer les effets éteints
                QTimer.singleShot(300, self.turn_off_all_effects)
                
                # Mettre à jour les indicateurs
                QTimer.singleShot(400, self.update_connection_indicators)
                
                QMessageBox.information(self, "Reconnexion réussie", 
                    "✅ AKAI APC mini reconnecté avec succès !\n\n"
                    "Les couleurs des pads ont été restaurées.")
            elif self.midi_handler.midi_in:
                QMessageBox.warning(self, "Reconnexion partielle", 
                    "⚠️ Entrée MIDI connectée mais pas la sortie (LEDs)\n"
                    "Les faders et pads fonctionnent mais les LEDs ne s'allumeront pas.")
            elif self.midi_handler.midi_out:
                QMessageBox.warning(self, "Reconnexion partielle", 
                    "⚠️ Sortie MIDI connectée mais pas l'entrée\n"
                    "Les LEDs fonctionnent mais les contrôles ne répondent pas.")
            else:
                QMessageBox.warning(self, "Reconnexion échouée", 
                    "❌ AKAI non détecté\n\n"
                    "Vérifiez que l'AKAI est bien branché et allumé.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur de reconnexion: {e}")
    
    def show_brightness_settings(self):
        """Affiche les réglages de luminosité AKAI"""
        dialog = QDialog(self)
        dialog.setWindowTitle("⚙️ Réglages Luminosité AKAI")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        # Titre
        title = QLabel("Configuration de la luminosité des pads AKAI")
        title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        layout.addWidget(title)
        
        layout.addSpacing(10)
        
        # Luminosité pads actifs
        active_label = QLabel(f"🔆 Luminosité pads ACTIFS : {self.akai_active_brightness}%")
        layout.addWidget(active_label)
        
        active_slider = QSlider(Qt.Horizontal)
        active_slider.setMinimum(50)
        active_slider.setMaximum(100)
        active_slider.setValue(self.akai_active_brightness)
        active_slider.setTickPosition(QSlider.TicksBelow)
        active_slider.setTickInterval(10)
        
        def update_active(value):
            self.akai_active_brightness = value
            active_label.setText(f"🔆 Luminosité pads ACTIFS : {value}%")
        
        active_slider.valueChanged.connect(update_active)
        layout.addWidget(active_slider)
        
        layout.addSpacing(20)
        
        # Luminosité pads inactifs
        inactive_label = QLabel(f"🌙 Luminosité pads INACTIFS : {self.akai_inactive_brightness}%")
        layout.addWidget(inactive_label)
        
        inactive_slider = QSlider(Qt.Horizontal)
        inactive_slider.setMinimum(10)
        inactive_slider.setMaximum(50)
        inactive_slider.setValue(self.akai_inactive_brightness)
        inactive_slider.setTickPosition(QSlider.TicksBelow)
        inactive_slider.setTickInterval(10)
        
        def update_inactive(value):
            self.akai_inactive_brightness = value
            inactive_label.setText(f"🌙 Luminosité pads INACTIFS : {value}%")
        
        inactive_slider.valueChanged.connect(update_inactive)
        layout.addWidget(inactive_slider)
        
        layout.addSpacing(20)
        
        # Boutons
        btn_layout = QHBoxLayout()
        
        apply_btn = QPushButton("✅ Appliquer")
        apply_btn.clicked.connect(lambda: self.apply_brightness_settings())
        apply_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(apply_btn)
        
        cancel_btn = QPushButton("❌ Annuler")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec_()
    
    def apply_brightness_settings(self):
        """Applique les nouveaux réglages de luminosité à tous les pads"""
        if not MIDI_AVAILABLE or not self.midi_handler.midi_out:
            return
        
        print(f"\n⚙️ Application des réglages de luminosité:")
        print(f"  Actifs: {self.akai_active_brightness}%")
        print(f"  Inactifs: {self.akai_inactive_brightness}%")
        
        # Réappliquer à tous les pads
        for row in range(8):
            for col in range(8):
                pad = self.pads.get((row, col))
                if pad and col < 8:
                    base_color = pad.property("base_color")
                    velocity = rgb_to_akai_velocity(base_color)
                    
                    # Déterminer si actif
                    is_active = False
                    if row == 0 and col < 5:
                        is_active = True  # Première ligne toujours active
                    elif hasattr(pad, 'active') and pad.active:
                        is_active = True
                    
                    brightness = self.akai_active_brightness if is_active else self.akai_inactive_brightness
                    
                    note = (7 - row) * 8 + col
                    channel = 0x96 if brightness >= 80 else 0x90
                    self.midi_handler.midi_out.send_message([channel, note, velocity])
        
        QMessageBox.information(self, "Réglages appliqués", 
            f"✅ Luminosité mise à jour !\n\n"
            f"Actifs: {self.akai_active_brightness}%\n"
            f"Inactifs: {self.akai_inactive_brightness}%")
    
    def show_midi_status(self):
        """Affiche l'état de la connexion MIDI"""
        if not MIDI_AVAILABLE:
            QMessageBox.information(self, "État AKAI", 
                "❌ Support MIDI non disponible\n\n"
                "Le logiciel fonctionne en mode SIMULATEUR uniquement.")
            return
        
        status = "État de la connexion AKAI:\n\n"
        
        if self.midi_handler.midi_in:
            status += "✅ Entrée MIDI : Connectée\n"
            status += "   (Faders et pads fonctionnels)\n\n"
        else:
            status += "❌ Entrée MIDI : Non connectée\n"
            status += "   (Faders et pads inactifs)\n\n"
        
        if self.midi_handler.midi_out:
            status += "✅ Sortie MIDI : Connectée\n"
            status += "   (LEDs fonctionnelles)\n\n"
        else:
            status += "❌ Sortie MIDI : Non connectée\n"
            status += "   (LEDs inactives)\n\n"
        
        if not self.midi_handler.midi_in and not self.midi_handler.midi_out:
            status += "💡 Le logiciel tentera de reconnecter\n"
            status += "   automatiquement toutes les 2 secondes.\n\n"
            status += "Vous pouvez aussi utiliser le menu:\n"
            status += "🎹 AKAI → Reconnecter AKAI"
        
        status += "\n💡 ASTUCE:\n"
        status += "Activez le Mode Debug MIDI pour voir\n"
        status += "tous les messages de votre AKAI en temps réel."
        
        QMessageBox.information(self, "État AKAI", status)

    def keyPressEvent(self, event):
        """Gère les raccourcis clavier + ZAPETTE POWERPOINT"""
        key = event.key()
        
        # Espace ou Entrée → Play/Pause
        if key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.toggle_play()
            event.accept()
        # Page Down → Média suivant (zapette)
        elif key == Qt.Key_PageDown:
            self.next_media()
            event.accept()
        # Page Up → Média précédent (zapette)
        elif key == Qt.Key_PageUp:
            self.previous_media()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def next_media(self):
        """Passe au média suivant"""
        if self.seq.current_row + 1 < self.seq.table.rowCount():
            self.seq.play_row(self.seq.current_row + 1)
    
    def previous_media(self):
        """Revient au média précédent"""
        if self.seq.current_row > 0:
            self.seq.play_row(self.seq.current_row - 1)
    
    def show_version(self):
        """Affiche la version de Maestro"""
        version_text = f"""
<center>
<h2>🎭 Maestro Light Control</h2>
<p style="font-size: 14px; color: #4a8aaa;"><b>Version {VERSION}</b></p>
<hr style="border: 1px solid #3a3a3a; margin: 20px 0;">
<p style="color: #888;">
Maestro.py - Controleur Lumiere DMX<br>
Contrôle professionnel DMX + AKAI APC mini<br><br>
Développé avec ❤️ par Nicolas PRIETO
</p>
<hr style="border: 1px solid #3a3a3a; margin: 20px 0;">
<p style="font-size: 11px; color: #666;">
© 2026 Maestro Light Control<br>
Tous droits réservés
</p>
</center>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle("À propos de Maestro")
        msg.setTextFormat(Qt.RichText)
        msg.setText(version_text)
        msg.setIconPixmap(QPixmap())  # Pas d'icône par défaut
        msg.setStandardButtons(QMessageBox.Ok)
        
        # Style personnalisé
        msg.setStyleSheet("""
            QMessageBox {
                background: #1a1a1a;
            }
            QLabel {
                color: white;
                min-width: 400px;
                min-height: 300px;
            }
            QPushButton {
                background: #4a8aaa;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background: #5a9aba;
            }
        """)
        
        msg.exec()
    
    def check_updates(self):
        """Vérifie les mises à jour disponibles"""
        # Pour l'instant, affiche juste un message
        # Plus tard, on pourra implémenter une vraie vérification
        msg = QMessageBox(self)
        msg.setWindowTitle("🔄 Vérifier les mises à jour")
        msg.setIcon(QMessageBox.Information)
        
        update_text = f"""
<h3>Vérification des mises à jour</h3>
<p>Version actuelle : <b>{VERSION}</b></p>
<hr>
<p style="color: #888;">
La fonctionnalité de mise à jour automatique<br>
sera disponible dans une prochaine version.
</p>
<p style="color: #4aaa4a;">
✓ Vous utilisez la dernière version !
</p>
        """
        
        msg.setTextFormat(Qt.RichText)
        msg.setText(update_text)
        msg.setStandardButtons(QMessageBox.Ok)
        
        msg.setStyleSheet("""
            QMessageBox {
                background: #1a1a1a;
            }
            QLabel {
                color: white;
                min-width: 350px;
            }
            QPushButton {
                background: #4a8aaa;
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background: #5a9aba;
            }
        """)
        
        msg.exec()

    def restart_application(self):
        """Redémarre l'application pour prendre en compte les modifications du code"""
        reply = QMessageBox.question(
            self,
            "🔄 Redémarrer l'application",
            "Voulez-vous redémarrer l'application ?\n\nLes modifications non sauvegardées seront perdues.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Fermer proprement les connexions
            if hasattr(self, 'midi_handler') and self.midi_handler:
                try:
                    if self.midi_handler.midi_in:
                        self.midi_handler.midi_in.close_port()
                    if self.midi_handler.midi_out:
                        self.midi_handler.midi_out.close_port()
                except:
                    pass

            # Redémarrer le script Python
            python = sys.executable
            os.execv(python, [python] + sys.argv)

    def open_light_editor(self):
        """Ouvre l'éditeur de séquence lumière façon montage vidéo"""
        # Mettre en pause si lecture en cours
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            print("⏸ Mise en pause pour REC Lumière")
        
        # Vérifier qu'un média est sélectionné
        current_row = self.seq.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Aucun média sélectionné",
                "Sélectionnez d'abord un média dans le séquenceur")
            return
        
        item = self.seq.table.item(current_row, 1)
        if not item or not item.data(Qt.UserRole):
            return
        
        # Créer l'éditeur
        editor = LightTimelineEditor(self, current_row)
        editor.exec()
    
    def closeEvent(self, e):
        # Fermer le MIDI
        if hasattr(self, 'midi_handler'):
            self.midi_handler.close()
        
        if self.seq.is_dirty:
            res = QMessageBox.question(
                self,
                "Quitter",
                "Sauvegarder avant de quitter ?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if res == QMessageBox.Yes:
                if self.save_show():
                    e.accept()
                else:
                    e.ignore()
            elif res == QMessageBox.Cancel:
                e.ignore()
            else:
                e.accept()
        else:
            e.accept()

    def apply_styles(self):
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
            QMessageBox QLabel { color: #ddd; min-width: 300px; }
            QMessageBox QPushButton {
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px 16px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background: #3a3a3a;
                border: 1px solid #00d4ff;
            }
        """)
    
    # ==================== FONCTIONS PATCH DMX ====================
    
    def auto_patch_at_startup(self):
        """Patch automatique au démarrage : charge la config sauvegardée ou utilise 1, 11, 21, 31..."""
        # Essayer de charger la configuration sauvegardée
        if self.load_dmx_patch_config():
            print("✅ Patch DMX restauré depuis la configuration")
            return
        
        # Sinon, créer le patch par défaut
        print("🔧 Création du patch DMX par défaut")
        dmx_addr = 1
        for i, proj in enumerate(self.projectors):
            proj_key = f"{proj.group}_{i}"
            
            # Mode 5 canaux par défaut (R, V, B, Dim, Strobe)
            self.dmx.projector_channels[proj_key] = [
                dmx_addr,      # Canal 1 : Rouge
                dmx_addr + 1,  # Canal 2 : Vert
                dmx_addr + 2,  # Canal 3 : Bleu
                dmx_addr + 3,  # Canal 4 : Dimmer
                dmx_addr + 4   # Canal 5 : Strobe
            ]
            self.dmx.projector_modes[proj_key] = "5CH"
            dmx_addr += 10
    
    def show_dmx_patch_config(self):
        """Interface simplifiée de configuration du mode DMX"""
        dialog = QDialog(self)
        dialog.setWindowTitle("⚙️ Configuration du Mode DMX")
        dialog.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(dialog)
        
        # Titre
        title = QLabel("🔌 Configuration du Mode DMX")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        info = QLabel(
            "Les projecteurs sont déjà adressés automatiquement : DMX 1, 11, 21, 31...\n"
            "Vous pouvez changer le mode (nombre de canaux) pour chaque projecteur."
        )
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #888; padding: 10px;")
        layout.addWidget(info)
        
        layout.addSpacing(10)
        
        # Tableau de configuration
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #3a3a3a;
                background: #1a1a1a;
            }
        """)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # Stocker les widgets pour récupérer les valeurs
        self.mode_inputs = {}
        
        for i, proj in enumerate(self.projectors):
            proj_frame = QFrame()
            proj_frame.setStyleSheet("""
                QFrame {
                    background: #2a2a2a;
                    border: 1px solid #3a3a3a;
                    border-radius: 6px;
                    padding: 10px;
                    margin: 5px;
                }
            """)
            
            proj_layout = QHBoxLayout(proj_frame)
            
            # Nom du projecteur simplifié
            if proj.group == "face":
                proj_name = f"<b>Face #{i+1}</b>"
            elif proj.group.startswith("douche"):
                douche_num = proj.group[-1]  # Récupère 1, 2 ou 3
                proj_name = f"<b>Douche {douche_num}</b>"
            elif proj.group == "contre":
                proj_name = f"<b>Contre #{i+1}</b>"
            else:
                proj_name = f"<b>{proj.group.capitalize()} #{i+1}</b>"
            
            name_label = QLabel(proj_name)
            name_label.setMinimumWidth(150)
            name_label.setStyleSheet("color: white; font-size: 13px;")
            proj_layout.addWidget(name_label)
            
            # Adresse DMX avec préfixe
            dmx_addr = (i * 10) + 1
            addr_label = QLabel(f"<b>DMX {dmx_addr}</b>")
            addr_label.setMinimumWidth(80)
            addr_label.setStyleSheet("color: #4a8aaa; font-weight: bold; font-size: 14px;")
            proj_layout.addWidget(addr_label)
            
            # Mode actuel
            proj_key = f"{proj.group}_{i}"
            current_mode = self.dmx.projector_modes.get(proj_key, "5CH")
            
            # Choix du mode
            mode_label = QLabel("Mode:")
            proj_layout.addWidget(mode_label)
            
            # Choix du mode simplifié
            mode_combo = QComboBox()
            mode_combo.setStyleSheet("""
                QComboBox {
                    background: #3a3a3a;
                    border: 1px solid #4a4a4a;
                    border-radius: 4px;
                    padding: 5px;
                    color: white;
                    min-width: 80px;
                }
            """)
            
            # EMPÊCHER SCROLL sur ComboBox
            mode_combo.wheelEvent = lambda e: e.ignore()
            
            mode_combo.addItem("5CH", "5CH")
            mode_combo.addItem("4CH", "4CH")
            mode_combo.addItem("3CH", "3CH")
            mode_combo.addItem("6CH", "6CH")
            
            # Sélectionner le mode actuel
            index = mode_combo.findData(current_mode)
            if index >= 0:
                mode_combo.setCurrentIndex(index)
            
            proj_layout.addWidget(mode_combo)
            
            # Bouton info
            info_btn = QPushButton("ℹ️")
            info_btn.setFixedSize(30, 30)
            info_btn.setToolTip("Informations sur les modes DMX")
            info_btn.setStyleSheet("""
                QPushButton {
                    background: #2a2a2a;
                    border: 1px solid #3a3a3a;
                    border-radius: 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #3a3a3a;
                }
            """)
            
            def show_mode_info():
                mode = mode_combo.currentData()
                info_dialog = QMessageBox(self)
                info_dialog.setWindowTitle(f"ℹ️ Mode {mode}")
                info_dialog.setStyleSheet("background: #1a1a1a; color: white;")
                
                if mode == "5CH":
                    text = "<b>Mode 5 Canaux</b><br><br>" \
                           "• Canal 1: Rouge (0-255)<br>" \
                           "• Canal 2: Vert (0-255)<br>" \
                           "• Canal 3: Bleu (0-255)<br>" \
                           "• Canal 4: Dimmer (0-255)<br>" \
                           "• Canal 5: Strobe (0-255)"
                elif mode == "4CH":
                    text = "<b>Mode 4 Canaux</b><br><br>" \
                           "• Canal 1: Rouge (0-255)<br>" \
                           "• Canal 2: Vert (0-255)<br>" \
                           "• Canal 3: Bleu (0-255)<br>" \
                           "• Canal 4: Dimmer (0-255)"
                elif mode == "6CH":
                    text = "<b>Mode 6 Canaux</b><br><br>" \
                           "• Canal 1: Rouge (0-255)<br>" \
                           "• Canal 2: Vert (0-255)<br>" \
                           "• Canal 3: Bleu (0-255)<br>" \
                           "• Canaux 4-6: Non utilisés<br>" \
                           "• Dimmer & Strobe: Virtuels (logiciel)"
                else:  # 3CH
                    text = "<b>Mode 3 Canaux</b><br><br>" \
                           "• Canal 1: Rouge (0-255)<br>" \
                           "• Canal 2: Vert (0-255)<br>" \
                           "• Canal 3: Bleu (0-255)"
                
                info_dialog.setText(text)
                info_dialog.exec()
            
            info_btn.clicked.connect(show_mode_info)
            proj_layout.addWidget(info_btn)
            
            proj_layout.addStretch()
            
            scroll_layout.addWidget(proj_frame)
            
            # Stocker le widget avec l'index du projecteur
            self.mode_inputs[i] = mode_combo
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # Boutons
        btn_layout = QHBoxLayout()
        
        # Appliquer
        apply_btn = QPushButton("✅ Appliquer")
        apply_btn.setStyleSheet("""
            QPushButton {
                background: #2a5a2a;
                color: white;
                padding: 10px 30px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #3a6a3a;
            }
        """)
        apply_btn.clicked.connect(lambda: self.apply_dmx_modes(dialog))
        btn_layout.addWidget(apply_btn)
        
        # Annuler
        cancel_btn = QPushButton("❌ Annuler")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                padding: 10px 30px;
                border-radius: 6px;
            }
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def apply_dmx_modes(self, dialog):
        """Applique les modes configurés"""
        for i, proj in enumerate(self.projectors):
            proj_key = f"{proj.group}_{i}"
            combo = self.mode_inputs[i]
            mode = combo.currentData()
            
            # Calculer l'adresse de base (1, 11, 21, 31...)
            dmx_addr = (i * 10) + 1
            
            # Configurer les canaux selon le mode
            if mode == "5CH":
                self.dmx.projector_channels[proj_key] = [
                    dmx_addr,      # Canal 1 : Rouge
                    dmx_addr + 1,  # Canal 2 : Vert
                    dmx_addr + 2,  # Canal 3 : Bleu
                    dmx_addr + 3,  # Canal 4 : Dimmer
                    dmx_addr + 4   # Canal 5 : Strobe
                ]
            elif mode == "6CH":
                self.dmx.projector_channels[proj_key] = [
                    dmx_addr,      # Canal 1 : Rouge
                    dmx_addr + 1,  # Canal 2 : Vert
                    dmx_addr + 2,  # Canal 3 : Bleu
                    -1,            # Pas de canal Dimmer (virtuel)
                    -1             # Pas de canal Strobe (virtuel)
                ]
            elif mode == "4CH":
                self.dmx.projector_channels[proj_key] = [
                    dmx_addr,      # Canal 1 : Rouge
                    dmx_addr + 1,  # Canal 2 : Vert
                    dmx_addr + 2,  # Canal 3 : Bleu
                    dmx_addr + 3   # Canal 4 : Dimmer
                ]
            else:  # 3CH
                self.dmx.projector_channels[proj_key] = [
                    dmx_addr,      # Canal 1 : Rouge
                    dmx_addr + 1,  # Canal 2 : Vert
                    dmx_addr + 2   # Canal 3 : Bleu
                ]
            
            self.dmx.projector_modes[proj_key] = mode
        
        # Sauvegarder le patch dans un fichier de configuration
        self.save_dmx_patch_config()
        
        QMessageBox.information(dialog, "Modes appliqués",
            f"✅ Modes DMX appliqués avec succès !\n\n"
            f"{len(self.projectors)} projecteurs configurés\n"
            f"Configuration sauvegardée automatiquement")
        
        dialog.accept()
    
    def save_dmx_patch_config(self):
        """Sauvegarde la configuration du patch DMX"""
        config = {
            'channels': self.dmx.projector_channels,
            'modes': self.dmx.projector_modes
        }
        try:
            config_path = Path.home() / '.maestro_dmx_patch.json'
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print("💾 Patch DMX sauvegardé")
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde patch: {e}")
    
    def load_dmx_patch_config(self):
        """Charge la configuration du patch DMX sauvegardée"""
        try:
            config_path = Path.home() / '.maestro_dmx_patch.json'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                self.dmx.projector_channels = config.get('channels', {})
                self.dmx.projector_modes = config.get('modes', {})
                print("📂 Patch DMX chargé depuis la configuration")
                return True
        except Exception as e:
            print(f"⚠️ Erreur chargement patch: {e}")
        return False
    
    def show_current_patch(self):
        """Affiche le patch DMX actuel"""
        if not self.dmx.projector_channels:
            QMessageBox.information(self, "Patch DMX",
                "❌ Aucun projecteur n'est patché\n\n"
                "Utilisez 'Configuration du Patch' pour patcher vos projecteurs.")
            return
        
        msg = "📋 Patch DMX actuel :\n\n"
        
        for i, proj in enumerate(self.projectors):
            proj_key = f"{proj.group}_{i}"
            if proj_key in self.dmx.projector_channels:
                channels = self.dmx.projector_channels[proj_key]
                mode = self.dmx.projector_modes.get(proj_key, "5CH")
                
                msg += f"• {proj.group} #{i+1} ({mode}):\n"
                
                if len(channels) == 5:
                    msg += f"  DMX {channels[0]:03d} (R), {channels[1]:03d} (V), {channels[2]:03d} (B), {channels[3]:03d} (Dim), {channels[4]:03d} (Strobe)\n\n"
                elif len(channels) == 4:
                    msg += f"  DMX {channels[0]:03d} (R), {channels[1]:03d} (V), {channels[2]:03d} (B), {channels[3]:03d} (Dim)\n\n"
                else:
                    msg += f"  DMX {channels[0]:03d} (R), {channels[1]:03d} (V), {channels[2]:03d} (B)\n\n"
        
        QMessageBox.information(self, "Patch DMX actuel", msg)
    
    def reset_dmx_patch(self):
        """Réinitialise le patch DMX"""
        reply = QMessageBox.question(self, "Réinitialiser le patch",
            "⚠️ Cette opération va supprimer toutes les assignations DMX.\n\n"
            "Continuer?",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.dmx.projector_channels = {}
            QMessageBox.information(self, "Patch réinitialisé",
                "✅ Le patch DMX a été réinitialisé")
    
    def show_dmx_debug(self):
        """Affiche les valeurs DMX en temps réel sous forme de tableau"""
        dialog = QDialog(self)
        dialog.setWindowTitle("🔍 Tableau DMX Temps Réel")
        dialog.setMinimumSize(900, 600)
        
        layout = QVBoxLayout(dialog)
        
        title = QLabel("📡 Valeurs DMX envoyées au Node 2")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        info = QLabel("Mise à jour en temps réel - Canaux 1-50")
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color: #888; padding: 5px;")
        layout.addWidget(info)
        
        # Tableau QTableWidget pour un affichage propre
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Canal", "Rouge", "Vert", "Bleu", "Dimmer", "Strobe"])
        table.setStyleSheet("""
            QTableWidget {
                background: #1a1a1a;
                gridline-color: #2a2a2a;
                color: white;
            }
            QHeaderView::section {
                background: #2a2a2a;
                color: white;
                padding: 5px;
                border: 1px solid #3a3a3a;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)
        
        # 10 rangées pour 10 projecteurs (1, 11, 21, ...91)
        table.setRowCount(10)
        
        def update_display():
            for i in range(10):
                base_ch = (i * 10) + 1
                
                # Canal de base
                item_ch = QTableWidgetItem(f"DMX {base_ch:03d}")
                item_ch.setTextAlignment(Qt.AlignCenter)
                table.setItem(i, 0, item_ch)
                
                # Rouge
                r = self.dmx.dmx_data[base_ch - 1] if base_ch <= 512 else 0
                item_r = QTableWidgetItem(str(r))
                item_r.setTextAlignment(Qt.AlignCenter)
                if r > 0:
                    item_r.setBackground(QColor(255, 100, 100))
                table.setItem(i, 1, item_r)
                
                # Vert
                g = self.dmx.dmx_data[base_ch] if base_ch + 1 <= 512 else 0
                item_g = QTableWidgetItem(str(g))
                item_g.setTextAlignment(Qt.AlignCenter)
                if g > 0:
                    item_g.setBackground(QColor(100, 255, 100))
                table.setItem(i, 2, item_g)
                
                # Bleu
                b = self.dmx.dmx_data[base_ch + 1] if base_ch + 2 <= 512 else 0
                item_b = QTableWidgetItem(str(b))
                item_b.setTextAlignment(Qt.AlignCenter)
                if b > 0:
                    item_b.setBackground(QColor(100, 100, 255))
                table.setItem(i, 3, item_b)
                
                # Dimmer
                d = self.dmx.dmx_data[base_ch + 2] if base_ch + 3 <= 512 else 0
                item_d = QTableWidgetItem(str(d))
                item_d.setTextAlignment(Qt.AlignCenter)
                if d > 0:
                    item_d.setBackground(QColor(255, 255, 100))
                table.setItem(i, 4, item_d)
                
                # Strobe
                s = self.dmx.dmx_data[base_ch + 3] if base_ch + 4 <= 512 else 0
                item_s = QTableWidgetItem(str(s))
                item_s.setTextAlignment(Qt.AlignCenter)
                if s > 0:
                    item_s.setBackground(QColor(255, 150, 0))
                table.setItem(i, 5, item_s)
        
        timer = QTimer()
        timer.timeout.connect(update_display)
        timer.start(100)  # Mise à jour toutes les 100ms
        
        layout.addWidget(table)
        
        # Bouton fermer
        close_btn = QPushButton("✅ Fermer")
        close_btn.clicked.connect(lambda: (timer.stop(), dialog.accept()))
        close_btn.setStyleSheet("""
            QPushButton {
                background: #2a5a2a;
                padding: 10px;
                border-radius: 6px;
                color: white;
                font-weight: bold;
            }
        """)
        layout.addWidget(close_btn)
        
        update_display()  # Premier affichage
        dialog.exec()
    
    # ==================== FONCTIONS CONNEXION ====================
    
    def on_akai_status_click(self):
        """Clic sur l'indicateur AKAI pour reconnecter"""
        akai_connected = False
        if MIDI_AVAILABLE and self.midi_handler.midi_in and self.midi_handler.midi_out:
            try:
                akai_connected = self.midi_handler.midi_in.is_port_open() and self.midi_handler.midi_out.is_port_open()
            except:
                pass
        
        if not akai_connected:
            # Tenter la reconnexion
            self.reconnect_midi()
            QTimer.singleShot(500, self.update_connection_indicators)
    
    def on_dmx_status_click(self):
        """Clic sur l'indicateur DMX pour ouvrir l'assistant"""
        if not self.dmx.connected:
            self.show_connection_wizard()
    
    def test_dmx_on_startup(self):
        """Test automatique de la connexion DMX au démarrage"""
        try:
            import subprocess
            import platform
            
            # Test ping silencieux
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '1', '-w', '500', '2.0.0.15']
            result = subprocess.run(command, capture_output=True, text=True, timeout=2)
            
            if result.returncode == 0:
                # Node 2 répond, on tente la connexion
                if self.dmx.connect():
                    # Connexion réussie
                    self.update_connection_indicators()
        except:
            # Échec silencieux, l'utilisateur verra le statut rouge
            pass
    
    def update_connection_indicators(self):
        """Met à jour les indicateurs de connexion AKAI et DMX (console uniquement)"""
        # AKAI - Vérification réelle de la connexion
        akai_connected = False
        if MIDI_AVAILABLE and self.midi_handler.midi_in and self.midi_handler.midi_out:
            try:
                in_count = self.midi_handler.midi_in.get_port_count()
                out_count = self.midi_handler.midi_out.get_port_count()
                akai_connected = in_count > 0 and out_count > 0 and self.midi_handler.midi_in.is_port_open() and self.midi_handler.midi_out.is_port_open()
            except:
                akai_connected = False
        
        if akai_connected:
            print("🎹 AKAI: ✅ Connecté")
        else:
            print("🎹 AKAI: ❌ Déconnecté")
        
        # DMX
        if self.dmx.connected:
            print(f"🌐 Boîtier DMX: ✅ Connecté ({self.dmx.target_ip})")
        else:
            print("🌐 Boîtier DMX: ❌ Déconnecté")
    
    def show_connection_wizard(self):
        """Assistant de connexion complet avec configuration Node 2 intégrée"""
        wizard = QDialog(self)
        wizard.setWindowTitle("⚙️ Configuration complète - Boîtier DMX Node 2")
        wizard.setMinimumSize(800, 650)
        
        layout = QVBoxLayout(wizard)
        
        # Titre
        title = QLabel("🌐 Assistant de configuration Boîtier Node 2")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("Configuration automatique pour Maestro (basée sur la procédure GrandMA)")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #888; padding-bottom: 15px;")
        layout.addWidget(subtitle)
        
        # Tabs pour organiser
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                background: #1a1a1a;
            }
            QTabBar::tab {
                background: #2a2a2a;
                color: white;
                padding: 10px 20px;
                border: 1px solid #3a3a3a;
            }
            QTabBar::tab:selected {
                background: #3a5a6a;
            }
        """)
        
        # TAB 1: Configuration réseau PC
        tab_pc = QWidget()
        tab_pc_layout = QVBoxLayout(tab_pc)
        
        pc_title = QLabel("📡 Étape 1 : Configuration de votre PC")
        pc_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        tab_pc_layout.addWidget(pc_title)
        
        pc_info = QLabel(
            "Maestro va configurer votre carte Ethernet avec les paramètres requis pour communiquer avec le Node 2.\n\n"
            "Configuration requise (selon documentation Electroconcept) :\n"
            "• IP PC : 2.0.0.30\n"
            "• Masque : 255.0.0.0\n"
            "• Passerelle : 2.0.0.15 (adresse du Node 2)"
        )
        pc_info.setStyleSheet("padding: 15px; background: #2a2a2a; border-radius: 6px; color: #ccc;")
        pc_info.setWordWrap(True)
        tab_pc_layout.addWidget(pc_info)
        
        tab_pc_layout.addSpacing(10)
        
        # Sélection carte réseau
        pc_adapter_label = QLabel("Carte réseau Ethernet à configurer :")
        tab_pc_layout.addWidget(pc_adapter_label)
        
        self.adapter_combo = QComboBox()
        self.adapter_combo.setStyleSheet("""
            QComboBox {
                padding: 10px;
                background: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                color: white;
                font-size: 12px;
            }
        """)
        adapters = self.get_network_adapters()
        for adapter in adapters:
            self.adapter_combo.addItem(adapter)
        tab_pc_layout.addWidget(self.adapter_combo)
        
        tab_pc_layout.addSpacing(10)
        
        # Boutons configuration PC
        pc_auto_btn = QPushButton("🔧 Configurer automatiquement mon PC (IP: 2.0.0.30)")
        pc_auto_btn.setStyleSheet("""
            QPushButton {
                background: #2a4a5a;
                color: white;
                padding: 15px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #3a5a6a;
            }
        """)
        pc_auto_btn.clicked.connect(lambda: self.configure_pc_network(wizard))
        tab_pc_layout.addWidget(pc_auto_btn)
        
        pc_manual_btn = QPushButton("📖 Ouvrir les paramètres réseau (configuration manuelle)")
        pc_manual_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                padding: 12px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #4a4a4a;
            }
        """)
        pc_manual_btn.clicked.connect(self.open_network_settings)
        tab_pc_layout.addWidget(pc_manual_btn)
        
        self.pc_result_label = QLabel("")
        self.pc_result_label.setWordWrap(True)
        self.pc_result_label.setAlignment(Qt.AlignCenter)
        tab_pc_layout.addWidget(self.pc_result_label)
        
        tab_pc_layout.addStretch()
        
        # TAB 2: Configuration Node 2
        tab_node = QWidget()
        tab_node_layout = QVBoxLayout(tab_node)
        
        node_title = QLabel("🎛️ Étape 2 : Configuration du Node 2 (optionnel)")
        node_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        tab_node_layout.addWidget(node_title)
        
        node_info = QLabel(
            "Le Node 2 doit être configuré via DMX TOOLS (fourni par Electroconcept).\n\n"
            "Si ce n'est pas déjà fait, connectez le Node 2 en USB et configurez :\n"
            "• Protocol : STATIC\n"
            "• Device IP : 2.0.0.15\n"
            "• Device IP Mask : 255.0.0.0\n"
            "• DMX Protocol : ART-NET\n"
            "• DMX 1 : OUT, Univers 0\n\n"
            "Téléchargez DMX TOOLS :\n"
            "www.boutiqueelectroconcept.com/media/Productattachments//d/m/dmx_tools.zip"
        )
        node_info.setStyleSheet("padding: 15px; background: #2a2a2a; border-radius: 6px; color: #ccc;")
        node_info.setWordWrap(True)
        node_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tab_node_layout.addWidget(node_info)
        
        tab_node_layout.addSpacing(10)
        
        node_config_note = QLabel(
            "⚠️ Note : La configuration du Node 2 nécessite DMX TOOLS.\n"
            "Maestro ne peut pas configurer le Node 2 directement via USB."
        )
        node_config_note.setStyleSheet("padding: 10px; background: #3a3a2a; border-radius: 4px; color: #ffa500;")
        node_config_note.setWordWrap(True)
        tab_node_layout.addWidget(node_config_note)
        
        tab_node_layout.addStretch()
        
        # TAB 3: Test de connexion
        tab_test = QWidget()
        tab_test_layout = QVBoxLayout(tab_test)
        
        test_title = QLabel("🧪 Étape 3 : Test de connexion")
        test_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        tab_test_layout.addWidget(test_title)
        
        test_info = QLabel(
            "Une fois votre PC et le Node 2 configurés, testez la connexion.\n\n"
            "Vérifications avant le test :\n"
            "✓ Câble Ethernet branché entre PC et Node 2\n"
            "✓ Node 2 alimenté (voyant allumé)\n"
            "✓ PC configuré avec IP 2.0.0.30\n"
            "✓ Node 2 configuré avec IP 2.0.0.15"
        )
        test_info.setStyleSheet("padding: 15px; background: #2a2a2a; border-radius: 6px; color: #ccc;")
        test_info.setWordWrap(True)
        tab_test_layout.addWidget(test_info)
        
        tab_test_layout.addSpacing(10)
        
        test_btn = QPushButton("🧪 Tester la connexion au Node 2 (2.0.0.15)")
        test_btn.setStyleSheet("""
            QPushButton {
                background: #2a5a2a;
                color: white;
                padding: 15px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #3a6a3a;
            }
        """)
        test_btn.clicked.connect(lambda: self.test_and_connect_dmx_correct_ip("2.0.0.15", self.test_result_label))
        tab_test_layout.addWidget(test_btn)
        
        self.test_result_label = QLabel("")
        self.test_result_label.setWordWrap(True)
        self.test_result_label.setAlignment(Qt.AlignCenter)
        tab_test_layout.addWidget(self.test_result_label)
        
        tab_test_layout.addStretch()
        
        # Ajouter les tabs
        tabs.addTab(tab_pc, "1️⃣ Configuration PC")
        tabs.addTab(tab_node, "2️⃣ Configuration Node 2")
        tabs.addTab(tab_test, "3️⃣ Test Connexion")
        
        layout.addWidget(tabs)
        
        # Bouton fermer
        close_btn = QPushButton("✅ Fermer")
        close_btn.clicked.connect(wizard.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: white;
                padding: 12px;
                border-radius: 6px;
                font-size: 12px;
            }
        """)
        layout.addWidget(close_btn)
        
        wizard.exec()
    
    def configure_pc_network(self, parent):
        """Configure le PC avec les bons paramètres (IP 2.0.0.30, Passerelle 2.0.0.15)"""
        import platform
        import subprocess
        
        if platform.system() != "Windows":
            self.pc_result_label.setText(
                "❌ Configuration automatique disponible uniquement sur Windows\n\n"
                "Sur Mac/Linux, configurez manuellement:\n"
                "• IP: 2.0.0.30\n"
                "• Masque: 255.0.0.0\n"
                "• Passerelle: 2.0.0.15"
            )
            self.pc_result_label.setStyleSheet("color: #ff4a4a; padding: 10px;")
            return
        
        adapter_name = self.adapter_combo.currentText()
        
        reply = QMessageBox.question(
            parent,
            "Configuration réseau",
            f"Maestro va configurer '{adapter_name}' avec:\n\n"
            f"• IP: 2.0.0.30\n"
            f"• Masque: 255.0.0.0\n"
            f"• Passerelle: 2.0.0.15 (Node 2)\n\n"
            f"⚠️ Nécessite les droits administrateur.\n\n"
            f"Continuer?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        self.pc_result_label.setText("⏳ Configuration en cours...")
        self.pc_result_label.setStyleSheet("color: #ffa500;")
        QApplication.processEvents()
        
        try:
            # Commande pour configurer IP + Passerelle
            cmd = f'netsh interface ip set address name="{adapter_name}" static 2.0.0.30 255.0.0.0 2.0.0.15'
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='cp850',
                timeout=5
            )
            
            if result.returncode == 0 or result.stdout.strip() == "":
                self.pc_result_label.setText(
                    f"✅ Configuration réussie !\n\n"
                    f"Carte '{adapter_name}' configurée :\n"
                    f"• IP: 2.0.0.30\n"
                    f"• Masque: 255.0.0.0\n"
                    f"• Passerelle: 2.0.0.15\n\n"
                    f"Passez à l'onglet 'Test Connexion' ➡️"
                )
                self.pc_result_label.setStyleSheet("color: #4aff4a; padding: 15px; background: #2a5a2a; border-radius: 6px;")
            else:
                self.show_network_config_error(parent, adapter_name, result)
        except subprocess.TimeoutExpired:
            self.show_network_config_error(parent, adapter_name, None, "Délai d'attente dépassé")
        except Exception as e:
            self.show_network_config_error(parent, adapter_name, None, str(e))
    
    def test_and_connect_dmx_correct_ip(self, node_ip, result_label):
        """Teste avec la bonne IP (2.0.0.15) et connecte"""
        result_label.setText("⏳ Test de connexion au Node 2...")
        result_label.setStyleSheet("color: #ffa500;")
        QApplication.processEvents()
        
        try:
            import subprocess
            import platform
            
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '1', '-w', '1000', node_ip]
            result = subprocess.run(command, capture_output=True, text=True, timeout=3)
            
            if result.returncode == 0:
                # Connexion réussie
                self.dmx.target_ip = node_ip
                if self.dmx.connect():
                    result_label.setText(
                        f"✅ Connexion réussie au Node 2 !\n\n"
                        f"IP: {node_ip}\n"
                        f"Protocole: Art-Net\n"
                        f"Univers: 0\n\n"
                        f"🎉 Vos lumières sont maintenant contrôlées en temps réel par Maestro !"
                    )
                    result_label.setStyleSheet("color: #4aff4a; padding: 15px; background: #2a5a2a; border-radius: 6px; font-size: 13px;")
                    self.update_connection_indicators()
                else:
                    result_label.setText(
                        "❌ Le Node 2 répond au ping mais la connexion Art-Net a échoué.\n\n"
                        "Vérifiez que le Node 2 est configuré en mode Art-Net."
                    )
                    result_label.setStyleSheet("color: #ff4a4a; padding: 15px; background: #5a2a2a; border-radius: 6px;")
            else:
                result_label.setText(
                    f"❌ Le Node 2 ne répond pas sur {node_ip}\n\n"
                    f"Vérifications :\n"
                    f"• Câble Ethernet branché entre PC et Node 2\n"
                    f"• Node 2 alimenté (voyant allumé)\n"
                    f"• Votre PC a bien l'IP 2.0.0.30\n"
                    f"• Le Node 2 a bien l'IP 2.0.0.15\n\n"
                    f"Astuce : Débranchez/rebranchez le Node 2 et réessayez."
                )
                result_label.setStyleSheet("color: #ffa500; padding: 15px; background: #3a3a2a; border-radius: 6px;")
        except Exception as e:
            result_label.setText(f"❌ Erreur: {str(e)}")
            result_label.setStyleSheet("color: #ff4a4a;")
    
    def get_network_adapters(self):
        """Récupère la liste des cartes réseau Windows"""
        import platform
        
        if platform.system() != "Windows":
            return ["Configuration manuelle requise (non-Windows)"]
        
        try:
            import subprocess
            result = subprocess.run(
                ['netsh', 'interface', 'show', 'interface'],
                capture_output=True,
                text=True,
                encoding='cp850'  # Encoding Windows
            )
            
            adapters = []
            for line in result.stdout.split('\n'):
                if 'Connecté' in line or 'Connected' in line or 'Enabled' in line:
                    # Extraire le nom de l'interface
                    parts = line.split()
                    if len(parts) >= 4:
                        adapter_name = ' '.join(parts[3:])
                        if adapter_name and adapter_name not in adapters:
                            adapters.append(adapter_name)
            
            if not adapters:
                adapters = ["Ethernet", "Wi-Fi", "Connexion au réseau local"]
            
            return adapters
        except Exception as e:
            print(f"Erreur récupération adaptateurs: {e}")
            return ["Ethernet", "Wi-Fi", "Connexion au réseau local"]
    
    def auto_configure_network(self, wizard):
        """Configure automatiquement la carte réseau avec PowerShell"""
        import platform
        import subprocess
        
        if platform.system() != "Windows":
            self.config_result_label.setText(
                "❌ Configuration automatique disponible uniquement sur Windows\n\n"
                "Sur Mac/Linux, configurez manuellement:\n"
                "• IP: 2.0.0.100\n"
                "• Masque: 255.0.0.0"
            )
            self.config_result_label.setStyleSheet("color: #ff4a4a; padding: 10px;")
            return
        
        adapter_name = self.adapter_combo.currentText()
        
        # Confirmation
        reply = QMessageBox.question(
            wizard,
            "Confirmation",
            f"Maestro va configurer la carte '{adapter_name}' avec:\n\n"
            f"• IP: 2.0.0.100\n"
            f"• Masque: 255.0.0.0\n\n"
            f"⚠️ Cette opération nécessite les droits administrateur.\n"
            f"Votre connexion Internet sera interrompue sur cette carte.\n\n"
            f"Continuer?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        self.config_result_label.setText("⏳ Configuration en cours...")
        self.config_result_label.setStyleSheet("color: #ffa500;")
        QApplication.processEvents()
        
        try:
            # Commande PowerShell pour configurer l'IP
            cmd = f'netsh interface ip set address name="{adapter_name}" static 2.0.0.100 255.0.0.0'
            
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='cp850',
                timeout=5
            )
            
            if result.returncode == 0 or "Ok" in result.stdout or result.stdout.strip() == "":
                self.config_result_label.setText(
                    f"✅ Configuration réussie !\n\n"
                    f"Carte '{adapter_name}' configurée avec:\n"
                    f"IP: 2.0.0.100 / Masque: 255.0.0.0\n\n"
                    f"Vous pouvez maintenant tester la connexion au Node 2."
                )
                self.config_result_label.setStyleSheet("color: #4aff4a; padding: 10px; background: #2a5a2a; border-radius: 6px;")
            else:
                # Erreur - Proposer d'ouvrir les paramètres
                self.show_network_config_error(wizard, adapter_name, result)
        except subprocess.TimeoutExpired:
            self.show_network_config_error(wizard, adapter_name, None, "Délai d'attente dépassé")
        except Exception as e:
            self.show_network_config_error(wizard, adapter_name, None, str(e))
    
    def show_network_config_error(self, parent, adapter_name, result=None, custom_error=None):
        """Affiche une erreur de configuration réseau avec option d'ouvrir les paramètres"""
        error_msg = custom_error if custom_error else (result.stderr if result and result.stderr else "Droits insuffisants")
        
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Configuration réseau")
        msg_box.setText("❌ Impossible de configurer automatiquement la carte réseau")
        msg_box.setInformativeText(
            f"Erreur: {error_msg}\n\n"
            f"Solutions:\n"
            f"1. Lancez Maestro en tant qu'administrateur\n"
            f"   (Clic droit > Exécuter en tant qu'administrateur)\n\n"
            f"2. Ou configurez manuellement dans les paramètres Windows"
        )
        
        # Bouton pour ouvrir les paramètres réseau
        open_settings_btn = msg_box.addButton("🔧 Ouvrir Paramètres Réseau", QMessageBox.ActionRole)
        retry_btn = msg_box.addButton("🔄 Réessayer", QMessageBox.ActionRole)
        cancel_btn = msg_box.addButton("❌ Annuler", QMessageBox.RejectRole)
        
        msg_box.exec()
        
        if msg_box.clickedButton() == open_settings_btn:
            self.open_network_settings()
        elif msg_box.clickedButton() == retry_btn:
            # Relancer avec élévation
            import sys
            import os
            try:
                import ctypes
                if ctypes.windll.shell32.IsUserAnAdmin():
                    # Déjà admin, réessayer
                    self.auto_configure_network(parent)
                else:
                    # Pas admin, proposer de relancer
                    reply = QMessageBox.question(
                        parent,
                        "Droits administrateur requis",
                        "Maestro n'a pas les droits administrateur.\n\n"
                        "Voulez-vous relancer Maestro en tant qu'administrateur?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.Yes:
                        # Relancer en admin
                        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
                        sys.exit()
            except:
                pass
    
    def open_network_settings(self):
        """Ouvre les paramètres réseau Windows"""
        import platform
        import subprocess
        
        try:
            if platform.system() == "Windows":
                # Ouvrir directement les paramètres réseau
                subprocess.Popen(['control', 'ncpa.cpl'])
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(['open', '/System/Library/PreferencePanes/Network.prefPane'])
            
            QMessageBox.information(self, "Configuration manuelle",
                "Les paramètres réseau ont été ouverts.\n\n"
                "Configurez votre carte Ethernet avec:\n"
                "• IP: 2.0.0.100\n"
                "• Masque: 255.0.0.0\n"
                "• Passerelle: (vide)")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir les paramètres: {e}")
    
    def test_and_connect_dmx(self, node_ip, result_label):
        """Teste et connecte au Node 2"""
        result_label.setText("⏳ Test de connexion au Node 2...")
        result_label.setStyleSheet("color: #ffa500;")
        QApplication.processEvents()
        
        try:
            import subprocess
            import platform
            
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '1', '-w', '1000', node_ip]
            result = subprocess.run(command, capture_output=True, text=True, timeout=3)
            
            if result.returncode == 0:
                # Ping OK, on connecte
                self.dmx.target_ip = node_ip
                if self.dmx.connect():
                    result_label.setText(f"✅ Connecté au Node 2 sur {node_ip} !\n\nLes lumières sont maintenant contrôlées en temps réel.")
                    result_label.setStyleSheet("color: #4aff4a; padding: 10px; background: #2a5a2a; border-radius: 6px;")
                    self.update_connection_indicators()
                else:
                    result_label.setText("❌ Le Node 2 répond mais la connexion Art-Net a échoué.\n\nVérifiez que le Node 2 est bien configuré en mode Art-Net.")
                    result_label.setStyleSheet("color: #ff4a4a; padding: 10px; background: #5a2a2a; border-radius: 6px;")
            else:
                # Pas de réponse
                result_label.setText(
                    f"❌ Le Node 2 ne répond pas sur {node_ip}\n\n"
                    f"Vérifications à faire:\n"
                    f"• Le câble Ethernet est bien branché entre votre PC et le Node 2\n"
                    f"• Le Node 2 est alimenté (voyant allumé)\n"
                    f"• Votre PC a bien l'IP 2.0.0.100\n"
                    f"• Le Node 2 a bien l'IP 2.0.0.50\n\n"
                    f"Astuce: Débranchez/rebranchez le Node 2 et réessayez."
                )
                result_label.setStyleSheet("color: #ffa500; padding: 10px; background: #3a3a2a; border-radius: 6px;")
        except subprocess.TimeoutExpired:
            result_label.setText(
                f"❌ Délai d'attente dépassé\n\n"
                f"Le Node 2 ne répond pas. Vérifiez:\n"
                f"• Câble Ethernet branché\n"
                f"• Node 2 alimenté\n"
                f"• Configuration réseau correcte"
            )
            result_label.setStyleSheet("color: #ff4a4a; padding: 10px; background: #5a2a2a; border-radius: 6px;")
        except Exception as e:
            result_label.setText(f"❌ Erreur inattendue: {str(e)}")
            result_label.setStyleSheet("color: #ff4a4a;")
    
    def show_connection_status(self):
        """Affiche l'état détaillé des connexions"""
        # AKAI - Vérification réelle
        akai_connected = False
        if MIDI_AVAILABLE and self.midi_handler.midi_in and self.midi_handler.midi_out:
            try:
                in_count = self.midi_handler.midi_in.get_port_count()
                out_count = self.midi_handler.midi_out.get_port_count()
                akai_connected = in_count > 0 and out_count > 0 and self.midi_handler.midi_in.is_port_open() and self.midi_handler.midi_out.is_port_open()
            except:
                akai_connected = False
        
        akai_info = f"🎹 AKAI APC mini\n"
        akai_info += f"Statut: {'✅ Connecté' if akai_connected else '❌ Déconnecté'}\n"
        
        if akai_connected and self.midi_handler.midi_in:
            try:
                if self.midi_handler.midi_in.get_port_count() > 0:
                    akai_info += f"Port In: {self.midi_handler.midi_in.get_port_name(0)}\n"
            except:
                pass
        
        if akai_connected and self.midi_handler.midi_out:
            try:
                if self.midi_handler.midi_out.get_port_count() > 0:
                    akai_info += f"Port Out: {self.midi_handler.midi_out.get_port_name(0)}\n"
            except:
                pass
        
        # DMX
        dmx_info = f"\n🌐 Boîtier DMX (Node 2)\n"
        dmx_info += f"Statut: {'✅ Connecté' if self.dmx.connected else '❌ Déconnecté'}\n"
        dmx_info += f"IP: {self.dmx.target_ip}\n"
        dmx_info += f"Port: {self.dmx.target_port}\n"
        dmx_info += f"Univers: {self.dmx.universe}\n"
        dmx_info += f"Protocole: Art-Net\n"
        dmx_info += f"Fréquence: 25 FPS\n"
        
        QMessageBox.information(self, "📊 État des connexions", akai_info + dmx_info)
    
    def send_dmx_update(self):
        """Envoie les données DMX toutes les 40ms (25 FPS)"""
        if self.dmx.connected:
            self.dmx.update_from_projectors(self.projectors, self.effect_speed)
            self.dmx.send_dmx()
    
    def show_dmx_wizard(self):
        """Redirige vers l'assistant complet"""
        self.show_connection_wizard()
    
    def toggle_dmx_connection(self):
        """Connecte ou déconnecte le DMX"""
        if self.dmx.connected:
            self.dmx.disconnect()
            QMessageBox.information(self, "Déconnexion", "🔌 Boîtier DMX déconnecté")
        else:
            if self.dmx.connect():
                QMessageBox.information(self, "Connexion", 
                    f"✅ Boîtier DMX connecté à {self.dmx.target_ip}")
            else:
                QMessageBox.critical(self, "Erreur", 
                    "❌ Échec de connexion\n\nUtilisez l'assistant de connexion.")
        
        self.update_connection_indicators()
    
    def show_dmx_status(self):
        """Redirige vers l'état complet"""
        self.show_connection_status()
    
    def show_dmx_manual_config(self):
        """Configuration manuelle supprimée - utiliser l'assistant"""
        self.show_connection_wizard()
    
    def save_manual_dmx_config(self, ip, port, dialog):
        """Configuration manuelle supprimée"""
        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())