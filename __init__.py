"""
================================================================================
Maestro.py
================================================================================

Application de controle lumiere professionnel avec:
- Controleur AKAI APC mini (MIDI)
- Sortie DMX via Art-Net (UDP)
- Sequenceur de medias audio/video
- Timeline d'edition lumiere
- Mode IA Lumiere (reactive au son)

================================================================================
ARCHITECTURE DES MODULES
================================================================================

config.py
---------
Configuration globale et constantes.
- APP_NAME, VERSION : Identification de l'application
- MIDI_AVAILABLE, midi_lib : Detection du support MIDI (rtmidi/rtmidi2)
- AKAI_COLOR_MAP, HEX_COLOR_MAP : Mapping couleurs RGB -> velocite AKAI
- rgb_to_akai_velocity(qcolor) : Convertit QColor en velocite AKAI
- fmt_time(ms) : Formate millisecondes en "MM:SS"
- media_icon(path) : Retourne type de media (audio/video/image)
- create_icon(type, color) : Cree icones transport (play/pause/prev/next)

projector.py
------------
Classe Projector : Represente un projecteur DMX.
Attributs: group, level, color, base_color, muted, dmx_mode
Methodes: set_color(), set_level(), toggle_mute(), get_dmx_rgb()
Groupes: face, douche1, douche2, douche3, lat, contre

midi_handler.py
---------------
Classe MIDIHandler(QObject) : Communication MIDI avec AKAI APC mini.
Signaux: fader_changed(int, int), pad_pressed(int, int)
Methodes: connect_akai(), poll_midi(), set_pad_led(), close()
Note: Detecte automatiquement les ports MIDI "APC"

artnet_dmx.py
-------------
Classe ArtNetDMX : Envoi DMX via protocole Art-Net (UDP port 6454).
Attributs: target_ip (2.0.0.15), universe (0), dmx_data[512]
Methodes: connect(), send_dmx(), update_from_projectors(), set_rgb()
projector_channels : Dict mapping projecteur -> canaux DMX
projector_modes : Dict mapping projecteur -> mode (3CH/4CH/5CH/6CH)

audio_ai.py
-----------
Classe AudioColorAI : Mode IA Lumiere - Eclairage reactif.
Attributs: scenes (palettes couleurs), current_scene, beat_counter
Methodes: update(), get_colors_for_groups(), next_scene()
Groupes geres: face, contre, lat, douche

ui_components.py
----------------
Widgets personnalises pour le simulateur AKAI:
- DualColorButton(QWidget) : Pad bicolore avec gradient diagonal
- EffectButton(QWidget) : Carre rouge pour effets (toggle)
- FaderButton(QWidget) : Bouton mute sous les faders
- ApcFader(QWidget) : Fader vertical/horizontal cliquable

plan_de_feu.py
--------------
Visualisation graphique des projecteurs:
- PlanDeFeu(QWidget) : Vue complete avec scene/public
- PlanDeFeuPreview(QWidget) : Version miniature pour timeline
Disposition: Face (haut), Douches (milieu), Lat+Contre (bas)

recording_waveform.py
---------------------
Classe RecordingWaveform(QWidget) : Timeline editable avec blocs.
Attributs: blocks[], duration, current_position
Methodes: add_block(), set_position(), clear(), get_blocks_data()
Blocs: {start_ms, end_ms, color, level}

sequencer.py
------------
Classe Sequencer(QWidget) : Playlist de medias avec controle DMX.
Composants: QTableWidget (6 colonnes), boutons +/-/clear
Colonnes: Numero, Nom, Duree, Volume, Mode DMX, Actions
Modes DMX: Manuel, IA Lumiere, Programme, Play Lumiere
Methodes: add_files(), add_pause(), add_tempo(), play_row()
Sequences: Dict[row] -> {keyframes, clips, duration}

light_timeline.py
-----------------
Composants pour l'editeur de timeline lumiere:
- LightClip(QWidget) : Clip colore draggable/resizable
  Attributs: start_time, duration, color, color2, intensity, effect
  Fades: fade_in_duration, fade_out_duration
- ColorPalette(QWidget) : Palette drag-and-drop (8 couleurs)
- LightTrack(QWidget) : Piste horizontale contenant des clips
  Methodes: add_clip(), update_clips(), update_zoom(), generate_waveform()

timeline_editor.py
------------------
Classe LightTimelineEditor(QDialog) : Editeur de sequences lumiere.
Pistes: Face, Douche 1-3, Contres, Audio (waveform)
Fonctions: Zoom, Play/Pause, Generation IA, Undo, Cut
Palette de couleurs drag-and-drop
Sauvegarde en mode "Play Lumiere"

main_window.py
--------------
Classe MainWindow(QMainWindow) : Fenetre principale.
Panneaux: AKAI (gauche), Sequenceur+Transport (centre), Plan+Video (droite)
Menus: Fichier, Patch DMX, REC Lumiere, Connexion, A propos
Gestion: Projecteurs, Effets (8 types), MIDI, DMX, Sauvegarde .tui
Raccourcis: Espace=Play, PageUp/Down=Media precedent/suivant

================================================================================
FLUX DE DONNEES
================================================================================

1. ENTREE UTILISATEUR
   AKAI physique -> MIDIHandler -> MainWindow.on_midi_fader/pad
   Simulateur UI -> MainWindow.activate_pad / set_proj_level

2. TRAITEMENT
   MainWindow -> Projector.set_color/level
   AudioColorAI.update() -> Projector (mode IA)
   Sequencer.play_sequence() -> Projector (mode Programme)

3. SORTIE DMX
   Timer 25fps -> ArtNetDMX.update_from_projectors()
   ArtNetDMX.send_dmx() -> UDP 2.0.0.15:6454

================================================================================
FORMATS DE FICHIERS
================================================================================

Show (.tui) - JSON:
[
  {"type": "media", "p": "path/file.mp3", "v": "80", "d": "Manuel"},
  {"type": "pause", "p": "PAUSE", "v": "--"},
  {"type": "tempo", "duration": "10", "d": "Manuel"},
  {"type": "media", "p": "...", "sequence": {"clips": [...], "duration": 180000}}
]

Patch DMX (~/.maestro_dmx_patch.json):
{
  "channels": {"face_0": [1,2,3,4,5], ...},
  "modes": {"face_0": "5CH", ...}
}

================================================================================
LANCEMENT
================================================================================

Version modulaire:  python maestro_new.py
Version originale:  python maestro.py (backup)

================================================================================
"""

# === IMPORTS PRINCIPAUX ===

# Configuration et constantes
from config import (
    APP_NAME, VERSION, MIDI_AVAILABLE, midi_lib,
    AKAI_COLOR_MAP, HEX_COLOR_MAP,
    rgb_to_akai_velocity, fmt_time, media_icon, create_icon
)

# Classes de base
from projector import Projector
from artnet_dmx import ArtNetDMX
from audio_ai import AudioColorAI
from midi_handler import MIDIHandler

# Composants UI
from ui_components import (
    DualColorButton, EffectButton, FaderButton, ApcFader
)

# Visualisation
from plan_de_feu import PlanDeFeu, PlanDeFeuPreview
from recording_waveform import RecordingWaveform

# Sequenceur et Timeline
from sequencer import Sequencer
from light_timeline import LightClip, ColorPalette, LightTrack
from timeline_editor import LightTimelineEditor

# Fenetre principale
from main_window import MainWindow


# === EXPORTS ===

__all__ = [
    # Config
    'APP_NAME', 'VERSION', 'MIDI_AVAILABLE', 'midi_lib',
    'AKAI_COLOR_MAP', 'HEX_COLOR_MAP',
    'rgb_to_akai_velocity', 'fmt_time', 'media_icon', 'create_icon',
    # Classes de base
    'Projector', 'ArtNetDMX', 'AudioColorAI', 'MIDIHandler',
    # UI
    'DualColorButton', 'EffectButton', 'FaderButton', 'ApcFader',
    # Visualisation
    'PlanDeFeu', 'PlanDeFeuPreview', 'RecordingWaveform',
    # Sequenceur
    'Sequencer',
    # Timeline
    'LightClip', 'ColorPalette', 'LightTrack', 'LightTimelineEditor',
    # MainWindow
    'MainWindow',
]

__version__ = VERSION
__author__ = "Nicolas PRIETO"
