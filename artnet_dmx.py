"""
Gestion de l'envoi DMX via Art-Net vers le Node 2
"""
import socket
import struct
import time

# Profils DMX pre-definis : nom -> liste ordonnee de types de canaux
DMX_PROFILES = {
    "RGB":         ["R", "G", "B"],
    "RGBD":        ["R", "G", "B", "Dim"],
    "RGBDS":       ["R", "G", "B", "Dim", "Strobe"],
    "RGBSD":       ["R", "G", "B", "Strobe", "Dim"],
    "DRGB":        ["Dim", "R", "G", "B"],
    "DRGBS":       ["Dim", "R", "G", "B", "Strobe"],
    "RGBW":        ["R", "G", "B", "W"],
    "RGBWD":       ["R", "G", "B", "W", "Dim"],
    "RGBWDS":      ["R", "G", "B", "W", "Dim", "Strobe"],
    "RGBWZ":       ["R", "G", "B", "W", "Zoom"],
    "RGBWA":       ["R", "G", "B", "W", "Ambre"],
    "RGBWAD":      ["R", "G", "B", "W", "Ambre", "Dim"],
    "RGBWOUV":     ["R", "G", "B", "W", "Orange", "UV"],
    "2CH_FUMEE":   ["Smoke", "Fan"],
    # Moving Head
    "MOVING_5CH":  ["Shutter", "Dim", "ColorWheel", "Gobo1", "Speed"],
    "MOVING_8CH":  ["Pan", "Tilt", "Shutter", "Dim", "ColorWheel", "Gobo1", "Speed", "Mode"],
    "MOVING_RGB":  ["Pan", "Tilt", "R", "G", "B", "Dim", "Shutter", "Speed"],
    "MOVING_RGBW": ["Pan", "Tilt", "R", "G", "B", "W", "Dim", "Shutter", "Speed"],
    # Barre LED
    "LED_BAR_RGB": ["R", "G", "B", "Dim", "Strobe"],
    # Stroboscope
    "STROBE_2CH":  ["Shutter", "Dim"],
}

# Types de canaux disponibles pour les profils custom
CHANNEL_TYPES = [
    "R", "G", "B", "W", "Dim", "Strobe", "UV", "Ambre", "Orange", "Zoom",
    "Smoke", "Fan",
    "Pan", "PanFine", "Tilt", "TiltFine", "Gobo1", "Gobo2",
    "Prism", "Focus", "ColorWheel", "Shutter", "Speed", "Mode",
]

# Noms courts pour l'affichage dans les combos
CHANNEL_DISPLAY = {
    "R": "R", "G": "G", "B": "B", "W": "W",
    "Dim": "Dim", "Strobe": "Strob", "UV": "UV",
    "Ambre": "Ambre", "Orange": "Orange", "Zoom": "Zoom",
    "Smoke": "Smoke", "Fan": "Fan",
    "Pan": "Pan", "PanFine": "PanF", "Tilt": "Tilt", "TiltFine": "TiltF",
    "Gobo1": "Gobo1", "Gobo2": "Gobo2", "Prism": "Prism", "Focus": "Focus",
    "ColorWheel": "CWheel", "Shutter": "Shut", "Speed": "Speed", "Mode": "Mode",
}


def profile_display_text(channels):
    """Formate une liste de canaux en texte lisible (R G B Dim Strob)"""
    return " ".join(CHANNEL_DISPLAY.get(ch, ch) for ch in channels)

# Retro-compatibilite : anciens modes -> nom de profil
_LEGACY_MODE_MAP = {
    "3CH": "RGB",
    "4CH": "RGBD",
    "5CH": "RGBDS",
    "6CH": "RGBDS",  # 6CH = RGBDS + 1 canal inutilise
    "2CH_FUMEE": "2CH_FUMEE",
}


def profile_for_mode(mode):
    """Convertit un ancien mode (3CH, 5CH...) en liste de types de canaux (profil)"""
    name = _LEGACY_MODE_MAP.get(mode, mode)
    if name in DMX_PROFILES:
        return list(DMX_PROFILES[name])
    # Si c'est deja une liste (profil custom), la retourner telle quelle
    if isinstance(mode, list):
        return mode
    # Fallback
    return list(DMX_PROFILES["RGBDS"])


def profile_name(profile):
    """Retrouve le nom d'un profil a partir de sa liste de canaux, ou None si custom"""
    for name, channels in DMX_PROFILES.items():
        if channels == profile:
            return name
    return None


class ArtNetDMX:
    """Gestion de l'envoi DMX via Art-Net vers le Node 2"""

    def __init__(self):
        self.target_ip = "2.0.0.15"  # IP du Node 2 selon documentation Electroconcept
        self.target_port = 6454  # Port Art-Net standard
        self.universe = 0  # Univers 0 par defaut
        self.sequence = 0
        self.dmx_data = [0] * 512  # 512 canaux DMX
        self.socket = None
        self.connected = False

        # Mapping des projecteurs vers les canaux DMX
        # Format: {"face_0": [1, 2, 3, 4, 5], ...}
        self.projector_channels = {}

        # Profils des projecteurs : proj_key -> liste de types ["R","G","B","Dim","Strobe"]
        self.projector_profiles = {}

        # Retro-compat : garde projector_modes comme alias lecture
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
            print(f"Erreur connexion Art-Net: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Ferme la connexion"""
        if self.socket:
            self.socket.close()
            self.socket = None
        self.connected = False

    def set_channel(self, channel, value):
        """Definit la valeur d'un canal DMX (1-512)"""
        if 1 <= channel <= 512:
            self.dmx_data[channel - 1] = max(0, min(255, value))

    def get_channel(self, channel):
        """Retourne la valeur d'un canal DMX (1-512)"""
        if 1 <= channel <= 512:
            return self.dmx_data[channel - 1]
        return 0

    def set_rgb(self, start_channel, r, g, b):
        """Definit RGB sur 3 canaux consecutifs"""
        self.set_channel(start_channel, r)
        self.set_channel(start_channel + 1, g)
        self.set_channel(start_channel + 2, b)

    def blackout(self):
        """Met tous les canaux a 0"""
        self.dmx_data = [0] * 512

    def send_dmx(self):
        """Envoie les donnees DMX via Art-Net"""
        if not self.connected or not self.socket:
            return False

        try:
            # En-tete Art-Net
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

            # Incrementer la sequence
            self.sequence = (self.sequence + 1) % 256
            return True
        except Exception as e:
            print(f"Erreur envoi DMX: {e}")
            return False

    def _get_profile(self, proj_key):
        """Retourne le profil d'un projecteur (liste de types de canaux)"""
        if proj_key in self.projector_profiles:
            return self.projector_profiles[proj_key]
        # Retro-compat : convertir depuis projector_modes
        mode = self.projector_modes.get(proj_key, "5CH")
        return profile_for_mode(mode)

    def _channel_index(self, profile, channel_type):
        """Retourne l'index d'un type de canal dans le profil, ou -1 si absent"""
        try:
            return profile.index(channel_type)
        except ValueError:
            return -1

    def update_from_projectors(self, projectors, effect_speed=0):
        """Met a jour les canaux DMX depuis la liste des projecteurs en utilisant le patch"""
        for i, proj in enumerate(projectors):
            proj_key = f"{proj.group}_{i}"

            if proj_key not in self.projector_channels:
                continue

            channels = self.projector_channels[proj_key]
            profile = self._get_profile(proj_key)

            # Traitement special fumee
            if "Smoke" in profile:
                is_muted = hasattr(proj, 'muted') and proj.muted
                smoke_idx = self._channel_index(profile, "Smoke")
                fan_idx = self._channel_index(profile, "Fan")
                if smoke_idx >= 0 and smoke_idx < len(channels):
                    smoke = int((proj.level / 100.0) * 255) if not is_muted else 0
                    self.set_channel(channels[smoke_idx], smoke)
                if fan_idx >= 0 and fan_idx < len(channels):
                    fan = getattr(proj, 'fan_speed', 0) if not is_muted else 0
                    self.set_channel(channels[fan_idx], fan)
                continue

            # Si le projecteur est mute, envoyer des 0
            if hasattr(proj, 'muted') and proj.muted:
                for ch in channels:
                    if ch > 0:
                        self.set_channel(ch, 0)
                continue

            # Recuperer RGB depuis proj.color
            r = proj.color.red() if hasattr(proj, 'color') else 0
            g = proj.color.green() if hasattr(proj, 'color') else 0
            b = proj.color.blue() if hasattr(proj, 'color') else 0

            # Dimmer : convertir de 0-100 vers 0-255
            level = proj.level if hasattr(proj, 'level') else 0
            dimmer = int((level / 100.0) * 255)

            # Verifier presence de Dim dans le profil
            dim_idx = self._channel_index(profile, "Dim")
            has_dimmer = dim_idx >= 0 and dim_idx < len(channels)

            # Si pas de dimmer hardware, appliquer le dimmer sur RGB
            if not has_dimmer:
                dimmer_factor = level / 100.0
                r = int(r * dimmer_factor)
                g = int(g * dimmer_factor)
                b = int(b * dimmer_factor)

            # Verifier presence de Strobe
            strobe_idx = self._channel_index(profile, "Strobe")
            has_strobe = strobe_idx >= 0 and strobe_idx < len(channels)

            # Si pas de strobe hardware mais strobe actif, creer strobe logiciel
            if not has_strobe and hasattr(proj, 'dmx_mode') and proj.dmx_mode == "Strobe":
                if int(time.time() * 10) % 2 == 0:
                    r, g, b = 0, 0, 0

            # Envoyer chaque canal selon son type dans le profil
            for idx, ch_type in enumerate(profile):
                if idx >= len(channels):
                    break
                ch = channels[idx]
                if ch <= 0:
                    continue

                if ch_type == "R":
                    self.set_channel(ch, r)
                elif ch_type == "G":
                    self.set_channel(ch, g)
                elif ch_type == "B":
                    self.set_channel(ch, b)
                elif ch_type == "W":
                    # Blanc = minimum des RGB (composante blanche commune)
                    w = min(r, g, b)
                    self.set_channel(ch, w)
                elif ch_type == "Ambre":
                    # Ambre = approximation ton chaud
                    ambre = int(min(r, g * 0.5) * 0.8) if r > 0 else 0
                    self.set_channel(ch, ambre)
                elif ch_type == "Orange":
                    # Orange = approximation ton chaud (R fort, un peu de G)
                    orange = int(min(r, g * 0.6) * 0.9) if r > 0 else 0
                    self.set_channel(ch, orange)
                elif ch_type == "UV":
                    self.set_channel(ch, 0)
                elif ch_type == "Zoom":
                    zoom = getattr(proj, 'zoom', 0)
                    self.set_channel(ch, zoom)
                elif ch_type == "Dim":
                    self.set_channel(ch, dimmer)
                elif ch_type == "Strobe":
                    strobe_value = 0
                    if hasattr(proj, 'dmx_mode') and proj.dmx_mode == "Strobe":
                        if effect_speed > 0:
                            strobe_value = int(16 + (effect_speed / 100.0) * (250 - 16))
                        else:
                            strobe_value = 100
                    self.set_channel(ch, strobe_value)
                elif ch_type == "Pan":
                    self.set_channel(ch, getattr(proj, 'pan', 128))
                elif ch_type == "PanFine":
                    pan = getattr(proj, 'pan', 128)
                    self.set_channel(ch, (pan * 256) % 256)
                elif ch_type == "Tilt":
                    self.set_channel(ch, getattr(proj, 'tilt', 128))
                elif ch_type == "TiltFine":
                    tilt = getattr(proj, 'tilt', 128)
                    self.set_channel(ch, (tilt * 256) % 256)
                elif ch_type == "Gobo1":
                    self.set_channel(ch, getattr(proj, 'gobo', 0))
                elif ch_type == "ColorWheel":
                    self.set_channel(ch, getattr(proj, 'color_wheel', 0))
                elif ch_type == "Shutter":
                    shutter = getattr(proj, 'shutter', 255)
                    self.set_channel(ch, shutter if not proj.muted else 0)
                elif ch_type in ("Gobo2", "Prism", "Focus", "Speed", "Mode"):
                    self.set_channel(ch, 0)

    def set_projector_patch(self, proj_key, channels, profile=None, mode=None):
        """Configure le patch d'un projecteur"""
        self.projector_channels[proj_key] = channels
        if profile is not None:
            self.projector_profiles[proj_key] = profile
            # Garder projector_modes synchronise pour retro-compat
            name = profile_name(profile)
            self.projector_modes[proj_key] = name if name else "CUSTOM"
        elif mode is not None:
            self.projector_modes[proj_key] = mode
            self.projector_profiles[proj_key] = profile_for_mode(mode)

    def clear_patch(self):
        """Efface tout le patch"""
        self.projector_channels.clear()
        self.projector_modes.clear()
        self.projector_profiles.clear()
