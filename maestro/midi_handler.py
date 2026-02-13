"""
Gestionnaire MIDI pour l'AKAI APC mini
"""

from PySide6.QtCore import QObject, Signal, QTimer

# Import MIDI (optionnel - fonctionne sans pour utiliser le simulateur uniquement)
MIDI_AVAILABLE = False
midi_lib = None
rtmidi = None

# Essayer rtmidi en premier
try:
    import rtmidi as _rtmidi
    rtmidi = _rtmidi
    MIDI_AVAILABLE = True
    midi_lib = "rtmidi"
    print("✅ Support MIDI activé (python-rtmidi) - AKAI physique disponible")
except ImportError:
    # Essayer rtmidi2 en alternative
    try:
        import rtmidi2 as _rtmidi
        rtmidi = _rtmidi
        MIDI_AVAILABLE = True
        midi_lib = "rtmidi2"
        print("✅ Support MIDI activé (rtmidi2) - AKAI physique disponible")
    except ImportError:
        MIDI_AVAILABLE = False
        print("ℹ️  Mode SIMULATEUR uniquement (MIDI non disponible)")
        print("   Le logiciel fonctionne parfaitement avec le simulateur AKAI virtuel !")
        print("   Pour connecter un AKAI physique : py -m pip install rtmidi2")
        print()


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
