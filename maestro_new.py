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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ------------------------------------------------------------------
# IMPORTS APPLICATION
# ------------------------------------------------------------------
from config import APP_NAME, VERSION
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEventLoop, QTimer
from updater import SplashScreen, UpdateChecker
from main_window import MainWindow
from license_manager import verify_license, check_exe_integrity

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
        QMessageBox.critical(None, "Maestro.py",
            "L'integrite de l'application n'a pas pu etre verifiee.\n\n"
            "Le fichier executable semble avoir ete modifie.\n"
            "Veuillez retelecharger l'application depuis le site officiel.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # VERIFICATION DE LA LICENCE (une seule fois, resultat cache)
    # ------------------------------------------------------------------
    splash.set_status("Verification de la licence...")
    app.processEvents()

    license_result = verify_license()
    print(f"Licence: {license_result}")

    # Initialiser la fenetre principale avec le resultat de licence
    splash.set_status("Initialisation...")
    app.processEvents()
    window = MainWindow(license_result=license_result)

    # Connecter le signal de mise a jour
    update_checker.update_available.connect(window.on_update_available)
    window._update_checker = update_checker

    # Garantir un affichage minimum de 2 secondes
    elapsed = time.time() - start_time
    remaining_ms = max(0, int((2.0 - elapsed) * 1000))
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
