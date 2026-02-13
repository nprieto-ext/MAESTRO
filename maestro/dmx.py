"""
Gestion DMX et Art-Net pour Maestro.py
"""

import socket
import struct

from PySide6.QtGui import QColor


class Projector:
    """Représente un projecteur DMX"""
    def __init__(self, group):
        self.group = group
        self.level = 0
        self.base_color = QColor("white")
        self.color = QColor("black")
        self.dmx_mode = "Manuel"
        self.muted = False


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
        import time

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
