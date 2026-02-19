#!/usr/bin/env python3
"""
Maestro - Controleur Lumiere DMX
Point d'entree principal de l'application

Structure des modules:
- config.py            : Imports, constantes, utilitaires
- projector.py         : Classe Projector
- midi_handler.py      : Classe MIDIHandler
- artnet_dmx.py        : Classe ArtNetDMX
- audio_ai.py          : Classe AudioColorAI
- ui_components.py     : Widgets UI
- plan_de_feu.py       : Plan de feu
- recording_waveform.py: Analyse audio
- sequencer.py         : Sequencer
- light_timeline.py    : Timeline lumiere
- timeline_editor.py   : Editeur de timeline
- main_window.py       : Fenetre principale
- updater.py           : Splash screen et mise a jour
- license_manager.py   : Systeme de licence
- license_ui.py        : Interface licence
"""

# ------------------------------------------------------------------
# FIX PYINSTALLER / IMPORTS
# ------------------------------------------------------------------
import sys
import os
import time

# ------------------------------------------------------------------
# IMPORTS APPLICATION
# ------------------------------------------------------------------

import socket

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QIcon

from core import APP_NAME, VERSION, MIDI_AVAILABLE, resource_path
from updater import SplashScreen, UpdateChecker
from main_window import MainWindow
from license_manager import (
    verify_license,
    check_exe_integrity,
    LicenseState,
)

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    """Point d'entree principal de Maestro"""
    print(f"Demarrage de {APP_NAME} v{VERSION}")
    print("Mode modulaire active")
    print("-" * 40)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    icon_path = resource_path("mystrow.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Splash screen
    splash = SplashScreen()
    splash.show()
    app.processEvents()
    start_time = time.time()

    # Lancer la verification des mises a jour en arriere-plan
    update_checker = UpdateChecker()
    update_checker.start()

    # ------------------------------------------------------------------
    # VERIFICATION INTEGRITE (anti-patch, uniquement en mode frozen)
    # ------------------------------------------------------------------
    splash.set_status("Verification de l'integrite...")
    app.processEvents()

    if not check_exe_integrity():
        splash.close()
        QMessageBox.critical(None, "MyStrow",
            "L'integrite de l'application n'a pas pu etre verifiee.\n\n"
            "Le fichier executable semble avoir ete modifie.\n"
            "Veuillez retelecharger l'application depuis le site officiel.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # DETECTION AKAI APC mini
    # ------------------------------------------------------------------
    splash.set_status("Detection AKAI...")
    app.processEvents()

    akai_found = False
    if MIDI_AVAILABLE:
        try:
            import rtmidi as _rt
        except ImportError:
            try:
                import rtmidi2 as _rt
            except ImportError:
                _rt = None
        if _rt:
            try:
                _mi = _rt.MidiIn()
                for name in _mi.get_ports():
                    if 'APC' in name.upper() or 'MINI' in name.upper():
                        akai_found = True
                        break
                del _mi
            except Exception:
                pass

    if akai_found:
        splash.set_hw_status("akai", "Connecte", True)
    else:
        splash.set_hw_status("akai", "Non detecte", False)
    app.processEvents()

    # ------------------------------------------------------------------
    # VERIFICATION NODE ART-NET (ping UDP 2.0.0.15)
    # ------------------------------------------------------------------
    splash.set_status("Verification Node Art-Net...")
    app.processEvents()

    node_ok = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        # Envoyer un ArtPoll pour detecter le node
        art_poll = bytearray(b'Art-Net\x00')
        art_poll.extend(b'\x00\x20')  # OpCode ArtPoll (0x2000 little-endian)
        art_poll.extend(b'\x00\x0e')  # Protocol version 14
        art_poll.extend(b'\x00\x00')  # TalkToMe + Priority
        sock.sendto(art_poll, ("2.0.0.15", 6454))
        try:
            data, addr = sock.recvfrom(1024)
            if data[:8] == b'Art-Net\x00':
                node_ok = True
        except socket.timeout:
            pass
        sock.close()
    except Exception:
        pass

    if node_ok:
        splash.set_hw_status("node", "2.0.0.15 - OK", True)
    else:
        splash.set_hw_status("node", "2.0.0.15 - Hors ligne", False)
    app.processEvents()

    # ------------------------------------------------------------------
    # VERIFICATION DE LA LICENCE (une seule fois, resultat cache)
    # ------------------------------------------------------------------
    splash.set_status("Verification de la licence...")
    app.processEvents()

    license_result = verify_license()
    print(f"Licence: {license_result}")

    # Afficher le statut licence sur le splash
    _license_labels = {
        LicenseState.LICENSE_ACTIVE: ("Compte actif", True),
        LicenseState.TRIAL_ACTIVE: (f"Essai - {license_result.days_remaining}j restants", True),
        LicenseState.NOT_ACTIVATED: ("—", True),
        LicenseState.TRIAL_EXPIRED: ("Essai expire", False),
        LicenseState.LICENSE_EXPIRED: ("Licence expiree", False),
        LicenseState.INVALID: ("Compte invalide", False),
        LicenseState.FRAUD_CLOCK: ("Erreur horloge", False),
    }
    lic_text, lic_ok = _license_labels.get(license_result.state, ("Inconnue", False))
    splash.set_hw_status("license", lic_text, lic_ok)
    app.processEvents()

    # Initialiser la fenetre principale avec le resultat de licence
    splash.set_status("Initialisation...")
    app.processEvents()
    window = MainWindow(license_result=license_result)

    # Connecter le signal de mise a jour
    update_checker.update_available.connect(window.on_update_available)
    window._update_checker = update_checker

    # Garantir un affichage minimum de 3 secondes
    elapsed = time.time() - start_time
    remaining_ms = max(0, int((5.0 - elapsed) * 1000))
    if remaining_ms > 0:
        splash.set_status("Pret !")
        app.processEvents()
        loop = QEventLoop()
        QTimer.singleShot(remaining_ms, loop.quit)
        loop.exec()

    # Fermer le splash et afficher la fenetre
    splash.close()
    window.showMaximized()

    # Afficher le dialogue d'avertissement licence si necessaire
    # (apres que la fenetre soit visible)
    QTimer.singleShot(500, window.show_license_warning_if_needed)

    sys.exit(app.exec())

# ------------------------------------------------------------------
# ENTRY POINT
# ------------------------------------------------------------------
if __name__ == "__main__":
    main()
