"""
Systeme de mise a jour et ecran de chargement pour Maestro.py
- SplashScreen : ecran de demarrage
- UpdateChecker : verification async des releases GitHub
- UpdateBar : barre de notification de mise a jour
- download_update : telechargement + verification SHA256 + batch updater
"""
import os
import sys
import json
import hashlib
import tempfile
import subprocess
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QDialog, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QScreen

from config import VERSION

# === CONSTANTES ===
GITHUB_API_URL = "https://api.github.com/repos/nprieto-ext/MAESTRO/releases/latest"
REMINDER_FILE = Path.home() / ".maestro_update_reminder.json"


def _version_tuple(v):
    """Convertit '2.5.0' en (2, 5, 0) pour comparaison"""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def version_gt(remote, local):
    """True si remote > local"""
    return _version_tuple(remote) > _version_tuple(local)


# ============================================================
# SPLASH SCREEN
# ============================================================
class SplashScreen(QWidget):
    """Ecran de chargement au demarrage"""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(400, 250)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.setStyleSheet("""
            SplashScreen {
                background: #1a1a1a;
                border: 2px solid #00d4ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 20)
        layout.setSpacing(12)

        layout.addStretch()

        title = QLabel("Maestro.py")
        title.setFont(QFont("Segoe UI", 28, QFont.Bold))
        title.setStyleSheet("color: #00d4ff;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        ver = QLabel(f"v{VERSION}")
        ver.setFont(QFont("Segoe UI", 12))
        ver.setStyleSheet("color: #888888;")
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)

        layout.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminee
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background: #333333;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: #00d4ff;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress)

        self.status_label = QLabel("Demarrage...")
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet("color: #666666;")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)

    def set_status(self, text):
        self.status_label.setText(text)


# ============================================================
# UPDATE CHECKER (QThread)
# ============================================================
class UpdateChecker(QThread):
    """Verifie les releases GitHub en arriere-plan"""

    update_available = Signal(str, str, str)  # version, exe_url, hash_url
    check_finished = Signal(bool, str)        # found, version (pour check manuel)

    def __init__(self, force=False):
        super().__init__()
        self.force = force

    def run(self):
        if self._reminder_active() and not self.force:
            self.check_finished.emit(False, "")
            return
        try:
            req = urllib.request.Request(
                GITHUB_API_URL,
                headers={"Accept": "application/vnd.github.v3+json",
                         "User-Agent": "Maestro-Updater"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            tag = data.get("tag_name", "")
            remote_version = tag.lstrip("v")

            if not version_gt(remote_version, VERSION):
                self.check_finished.emit(False, remote_version)
                return

            exe_url = ""
            hash_url = ""
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                url = asset.get("browser_download_url", "")
                if name.lower() == "maestro.exe":
                    exe_url = url
                elif name.lower() == "sha256.txt":
                    hash_url = url

            if exe_url:
                self.update_available.emit(remote_version, exe_url, hash_url)
                self.check_finished.emit(True, remote_version)
            else:
                self.check_finished.emit(False, remote_version)
        except Exception:
            self.check_finished.emit(False, "")

    def _reminder_active(self):
        try:
            data = json.loads(REMINDER_FILE.read_text(encoding="utf-8"))
            remind_after = datetime.fromisoformat(data["remind_after"])
            stored_version = data.get("version", "")
            return datetime.now() < remind_after and stored_version != ""
        except Exception:
            return False

    @staticmethod
    def save_reminder(version):
        try:
            data = {
                "remind_after": (datetime.now() + timedelta(hours=24)).isoformat(),
                "version": version,
            }
            REMINDER_FILE.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass


# ============================================================
# UPDATE BAR
# ============================================================
class UpdateBar(QWidget):
    """Barre de notification verte pour les mises a jour"""

    later_clicked = Signal()
    update_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.version = ""
        self.exe_url = ""
        self.hash_url = ""

        self.setFixedHeight(40)
        self.setStyleSheet("background: #2d7a3a;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(10)

        self.label = QLabel()
        self.label.setFont(QFont("Segoe UI", 10))
        self.label.setStyleSheet("color: white;")
        layout.addWidget(self.label, 1)

        btn_later = QPushButton("Plus tard")
        btn_later.setFixedHeight(28)
        btn_later.setCursor(Qt.PointingHandCursor)
        btn_later.setStyleSheet("""
            QPushButton {
                color: white;
                background: transparent;
                border: 1px solid rgba(255,255,255,0.5);
                border-radius: 4px;
                padding: 4px 14px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.15);
            }
        """)
        btn_later.clicked.connect(self.later_clicked)
        layout.addWidget(btn_later)

        btn_update = QPushButton("Mettre a jour")
        btn_update.setFixedHeight(28)
        btn_update.setCursor(Qt.PointingHandCursor)
        btn_update.setStyleSheet("""
            QPushButton {
                color: white;
                background: #4CAF50;
                border: none;
                border-radius: 4px;
                padding: 4px 14px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #66BB6A;
            }
        """)
        btn_update.clicked.connect(self.update_clicked)
        layout.addWidget(btn_update)

    def set_info(self, version, exe_url, hash_url):
        self.version = version
        self.exe_url = exe_url
        self.hash_url = hash_url
        self.label.setText(f"Nouvelle version disponible (v{version})")


# ============================================================
# DOWNLOAD + INSTALL
# ============================================================
def download_update(parent, version, exe_url, hash_url):
    """Telecharge la mise a jour avec verification SHA256 et lance le batch updater"""

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Mise a jour v{version}")
    dlg.setFixedSize(420, 130)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(20, 15, 20, 15)

    status_label = QLabel("Preparation du telechargement...")
    status_label.setFont(QFont("Segoe UI", 10))
    layout.addWidget(status_label)

    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setFixedHeight(20)
    layout.addWidget(progress)

    dlg.show()
    QApplication.processEvents()

    update_dir = Path(tempfile.gettempdir()) / "maestro_update"
    update_dir.mkdir(exist_ok=True)
    new_exe = update_dir / "Maestro.exe"

    # --- Telechargement SHA256 ---
    expected_hash = ""
    if hash_url:
        try:
            status_label.setText("Verification de l'integrite...")
            QApplication.processEvents()
            with urllib.request.urlopen(hash_url, timeout=10) as resp:
                content = resp.read().decode("utf-8").strip()
                # Format: "hash  filename" ou juste "hash"
                expected_hash = content.split()[0].lower()
        except Exception:
            expected_hash = ""

    # --- Telechargement EXE ---
    def reporthook(block_num, block_size, total_size):
        if total_size > 0:
            pct = min(int(block_num * block_size * 100 / total_size), 100)
            progress.setValue(pct)
            size_mb = total_size / (1024 * 1024)
            dl_mb = min(block_num * block_size, total_size) / (1024 * 1024)
            status_label.setText(f"Telechargement... {dl_mb:.1f} / {size_mb:.1f} Mo")
        else:
            status_label.setText(f"Telechargement en cours...")
        QApplication.processEvents()

    try:
        status_label.setText("Telechargement de Maestro.exe...")
        QApplication.processEvents()
        urllib.request.urlretrieve(exe_url, str(new_exe), reporthook)
    except Exception as e:
        dlg.close()
        QMessageBox.critical(parent, "Erreur de telechargement",
                             f"Impossible de telecharger la mise a jour.\n\n{e}")
        return

    # --- Verification SHA256 ---
    if expected_hash:
        status_label.setText("Verification SHA256...")
        progress.setValue(100)
        QApplication.processEvents()

        sha = hashlib.sha256()
        with open(new_exe, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        actual_hash = sha.hexdigest().lower()

        if actual_hash != expected_hash:
            dlg.close()
            try:
                new_exe.unlink()
            except Exception:
                pass
            QMessageBox.critical(parent, "Erreur de verification",
                                 f"Le fichier telecharge est corrompu.\n\n"
                                 f"Attendu:  {expected_hash[:16]}...\n"
                                 f"Obtenu:   {actual_hash[:16]}...")
            return

    # --- Batch updater ---
    status_label.setText("Installation de la mise a jour...")
    QApplication.processEvents()

    current_exe = sys.executable
    if getattr(sys, 'frozen', False):
        current_exe = sys.executable
    else:
        # Mode dev: ne pas ecraser python.exe
        dlg.close()
        QMessageBox.information(parent, "Mode developpement",
                                f"Mise a jour telechargee dans:\n{new_exe}\n\n"
                                f"(Installation automatique desactivee en mode dev)")
        return

    batch_path = _create_updater_batch(str(new_exe), current_exe)

    dlg.close()

    # Lancer le batch et quitter
    subprocess.Popen(
        ["cmd.exe", "/c", str(batch_path)],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    QApplication.quit()


def _create_updater_batch(new_exe, current_exe):
    """Cree le script batch de mise a jour"""
    batch_path = Path(tempfile.gettempdir()) / "maestro_update" / "update_maestro.bat"
    batch_content = f'''@echo off
echo Mise a jour Maestro en cours...
timeout /t 2 /nobreak >nul
:retry
copy /y "{new_exe}" "{current_exe}" >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto retry
)
del "{new_exe}"
start "" "{current_exe}"
del "%~f0"
'''
    batch_path.write_text(batch_content, encoding="utf-8")
    return batch_path
