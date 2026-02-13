# Maestro.py

Application de controle lumiere professionnel avec controleur AKAI APC mini.

## Lancement

```bash
python maestro_new.py
```

## Technologies

- **PySide6/Qt6** - Interface graphique
- **python-rtmidi / rtmidi2** - Communication MIDI avec AKAI APC mini
- **UDP Sockets** - Protocol Art-Net DMX (port 6454, IP 2.0.0.15)
- **JSON** - Sauvegarde des shows (.tui)

## Structure des modules

```
Boitier AKAI/
├── maestro_new.py      # Point d'entree (lance MainWindow)
├── maestro.py          # Ancien fichier monolithique (backup)
├── __init__.py         # Documentation et exports du package
│
├── config.py           # Constantes, MIDI detection, utilitaires
├── projector.py        # Classe Projector (DMX, couleurs, groupes)
├── midi_handler.py     # MIDIHandler (AKAI APC mini)
├── artnet_dmx.py       # ArtNetDMX (envoi UDP Art-Net)
├── audio_ai.py         # AudioColorAI (mode IA reactive)
│
├── ui_components.py    # Widgets AKAI (DualColorButton, ApcFader...)
├── plan_de_feu.py      # Visualisation des projecteurs
├── recording_waveform.py # Timeline avec blocs editables
│
├── sequencer.py        # Playlist medias + modes DMX
├── light_timeline.py   # LightClip, LightTrack, ColorPalette
├── timeline_editor.py  # Editeur de sequences lumiere
└── main_window.py      # Fenetre principale (~1350 lignes)
```

## Fichiers cles

| Fichier | Contenu | Lignes |
|---------|---------|--------|
| main_window.py | Fenetre principale, gestion projecteurs/effets/MIDI/DMX | ~1350 |
| timeline_editor.py | Editeur timeline lumiere avec zoom/play/IA | ~750 |
| sequencer.py | Playlist medias avec 4 modes DMX | ~400 |
| light_timeline.py | Clips, pistes, palette couleurs | ~350 |

## Concepts importants

### Projecteurs
- 6 groupes: `face`, `douche1`, `douche2`, `douche3`, `lat`, `contre`
- Modes DMX: 3CH, 4CH, 5CH, 6CH (5CH par defaut)
- Patch automatique: adresses 1, 11, 21, 31... (10 canaux/projecteur)

### Modes du sequenceur
1. **Manuel** - Controle direct via AKAI/UI
2. **IA Lumiere** - Eclairage reactif au son (AudioColorAI)
3. **Programme** - Keyframes pre-enregistres
4. **Play Lumiere** - Timeline complete avec clips

### Interface AKAI
- Grille 8x8 pads (couleurs LED)
- 9 faders verticaux (niveau projecteurs + master)
- Boutons mute sous chaque fader

## Flux de donnees

```
AKAI physique ─┬─> MIDIHandler ─> MainWindow.on_midi_*
               │
Simulateur UI ─┴─> MainWindow ─> Projector.set_color/level
                                      │
AudioColorAI (mode IA) ───────────────┤
Sequencer (mode Programme) ───────────┘
                                      │
                                      v
                   ArtNetDMX.update_from_projectors()
                                      │
                                      v
                         UDP 2.0.0.15:6454 (DMX)
```

## Format de sauvegarde (.tui)

```json
[
  {"type": "media", "p": "path/file.mp3", "v": "80", "d": "Manuel"},
  {"type": "pause", "p": "PAUSE", "v": "--"},
  {"type": "tempo", "duration": "10", "d": "Manuel"},
  {"type": "media", "p": "...", "sequence": {"clips": [...], "duration": 180000}}
]
```

## Conventions de code

- Classes principales heritent de QWidget ou QMainWindow
- Signaux Qt pour communication inter-composants
- Timer 25 fps pour envoi DMX continu
- Couleurs en QColor, converties en velocite AKAI (0-127)

## Raccourcis clavier

- `Espace` - Play/Pause
- `PageUp/PageDown` - Media precedent/suivant
- Menu REC Lumiere - Ouvre l'editeur timeline
