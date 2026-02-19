"""
Systeme de mise a jour et ecran de chargement pour MyStrow
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
from PySide6.QtGui import QFont, QScreen, QPixmap

from core import VERSION, resource_path

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
        self.setFixedSize(420, 380)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.setStyleSheet("""
            SplashScreen {
                background: #1a1a1a;
                border: 2px solid #00d4ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 16)
        layout.setSpacing(8)

        # --- Logo ---
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        logo_path = resource_path("logo.png")
        if os.path.exists(logo_path):
            px = QPixmap(logo_path)
            px = px.scaledToHeight(80, Qt.SmoothTransformation)
            self.logo_label.setPixmap(px)
        layout.addWidget(self.logo_label)

        # --- Titre + version ---
        title = QLabel("MyStrow")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet("color: #00d4ff;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        ver = QLabel(f"v{VERSION}")
        ver.setFont(QFont("Segoe UI", 10))
        ver.setStyleSheet("color: #888888;")
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)

        layout.addSpacing(10)

        # --- Status hardware (AKAI, Node, Licence) ---
        self.status_akai = self._create_status_row("AKAI APC mini", "Recherche...")
        layout.addLayout(self.status_akai["layout"])

        self.status_node = self._create_status_row("Node Art-Net", "Recherche...")
        layout.addLayout(self.status_node["layout"])

        self.status_license = self._create_status_row("Licence", "Verification...")
        layout.addLayout(self.status_license["layout"])

        layout.addSpacing(8)

        # --- Barre de progression ---
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

    def _create_status_row(self, label_text, initial_value):
        """Cree une ligne de statut avec indicateur et texte"""
        row = QHBoxLayout()
        row.setContentsMargins(10, 2, 10, 2)
        row.setSpacing(8)

        indicator = QLabel("\u25CF")  # Cercle plein
        indicator.setFont(QFont("Segoe UI", 10))
        indicator.setStyleSheet("color: #666666;")
        indicator.setFixedWidth(16)
        row.addWidget(indicator)

        label = QLabel(label_text)
        label.setFont(QFont("Segoe UI", 10))
        label.setStyleSheet("color: #cccccc;")
        row.addWidget(label)

        row.addStretch()

        value = QLabel(initial_value)
        value.setFont(QFont("Segoe UI", 10))
        value.setStyleSheet("color: #888888;")
        row.addWidget(value)

        return {"layout": row, "indicator": indicator, "value": value}

    def set_hw_status(self, target, text, ok):
        """Met a jour un statut hardware (akai, node, license)"""
        row = getattr(self, f"status_{target}", None)
        if not row:
            return
        if ok:
            row["indicator"].setStyleSheet("color: #4CAF50;")  # Vert
            row["value"].setStyleSheet("color: #4CAF50;")
        else:
            row["indicator"].setStyleSheet("color: #f44336;")  # Rouge
            row["value"].setStyleSheet("color: #f44336;")
        row["value"].setText(text)

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
                         "User-Agent": "MyStrow-Updater"}
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
                if name.lower() in ("mystrow_setup.exe", "mystrow.exe"):
                    exe_url = url
                elif name.lower() == "sha256.txt":
                    hash_url = url

            if exe_url:
                self.update_available.emit(remote_version, exe_url, hash_url)
                self.check_finished.emit(True, remote_version)
            else:
                # Nouvelle version détectée mais l'exe n'est pas encore disponible
                # (GitHub Actions pas encore terminé ou asset manquant)
                self.check_finished.emit(True, remote_version)
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
    dlg.setFixedSize(460, 200)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    dlg.setStyleSheet("background: #1e1e1e; color: #cccccc;")

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(10)

    # --- Titre ---
    title = QLabel(f"Mise a jour vers v{version}")
    title.setFont(QFont("Segoe UI", 11, QFont.Bold))
    title.setStyleSheet("color: #00d4ff;")
    layout.addWidget(title)

    # --- Etapes visuelles ---
    steps_layout = QHBoxLayout()
    steps_layout.setSpacing(0)

    def _make_step(text):
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", 9))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #555555; padding: 4px 10px;")
        return lbl

    step_dl   = _make_step("⬇  Telechargement")
    step_check = _make_step("🔍  Verification")
    step_inst  = _make_step("⚙  Installation")

    for s in (step_dl, step_check, step_inst):
        steps_layout.addWidget(s, 1)
    layout.addLayout(steps_layout)

    # --- Barre de progression ---
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setFixedHeight(14)
    progress.setTextVisible(False)
    progress.setStyleSheet("""
        QProgressBar {
            background: #333333;
            border: none;
            border-radius: 7px;
        }
        QProgressBar::chunk {
            background: #00d4ff;
            border-radius: 7px;
        }
    """)
    layout.addWidget(progress)

    # --- Label de detail ---
    status_label = QLabel("Preparation...")
    status_label.setFont(QFont("Segoe UI", 9))
    status_label.setStyleSheet("color: #888888;")
    status_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(status_label)

    def _set_step(active_step):
        """Met en evidence l'etape active"""
        for s in (step_dl, step_check, step_inst):
            s.setStyleSheet("color: #555555; padding: 4px 10px;")
        active_step.setStyleSheet(
            "color: #00d4ff; font-weight: bold; padding: 4px 10px; "
            "border-bottom: 2px solid #00d4ff;"
        )

    _set_step(step_dl)
    dlg.show()
    QApplication.processEvents()

    update_dir = Path(tempfile.gettempdir()) / "mystrow_update"
    update_dir.mkdir(exist_ok=True)

    # Détecter si c'est un installeur ou un exe brut
    is_installer = "setup" in exe_url.lower()
    filename = "MyStrow_Setup.exe" if is_installer else "MyStrow.exe"
    new_file = update_dir / filename

    # --- Telechargement ---
    def reporthook(block_num, block_size, total_size):
        if total_size > 0:
            pct = min(int(block_num * block_size * 100 / total_size), 100)
            progress.setValue(pct)
            size_mb = total_size / (1024 * 1024)
            dl_mb = min(block_num * block_size, total_size) / (1024 * 1024)
            status_label.setText(f"{dl_mb:.1f} Mo / {size_mb:.1f} Mo")
        else:
            status_label.setText("Telechargement en cours...")
        QApplication.processEvents()

    try:
        status_label.setText(f"Connexion au serveur...")
        QApplication.processEvents()
        urllib.request.urlretrieve(exe_url, str(new_file), reporthook)
    except Exception as e:
        dlg.close()
        QMessageBox.critical(parent, "Erreur de telechargement",
                             f"Impossible de telecharger la mise a jour.\n\n{e}")
        return

    # --- Verification SHA256 (seulement si sha256.txt dispo) ---
    _set_step(step_check)
    progress.setRange(0, 0)  # indetermine pendant la verif
    status_label.setText("Verification de l'integrite...")
    QApplication.processEvents()

    if hash_url and not is_installer:
        expected_hash = ""
        try:
            with urllib.request.urlopen(hash_url, timeout=10) as resp:
                content = resp.read().decode("utf-8").strip()
                expected_hash = content.split()[0].lower()
        except Exception:
            expected_hash = ""

        if expected_hash:
            sha = hashlib.sha256()
            with open(new_file, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha.update(chunk)
            actual_hash = sha.hexdigest().lower()
            if actual_hash != expected_hash:
                dlg.close()
                try:
                    new_file.unlink()
                except Exception:
                    pass
                QMessageBox.critical(parent, "Erreur de verification",
                                     f"Le fichier telecharge est corrompu.\n\n"
                                     f"Attendu:  {expected_hash[:16]}...\n"
                                     f"Obtenu:   {actual_hash[:16]}...")
                return

    # --- Installation ---
    _set_step(step_inst)
    progress.setRange(0, 0)
    status_label.setText("Lancement de l'installeur...")
    QApplication.processEvents()

    if not getattr(sys, 'frozen', False):
        dlg.close()
        QMessageBox.information(parent, "Mode developpement",
                                f"Mise a jour telechargee dans:\n{new_file}\n\n"
                                f"(Installation automatique desactivee en mode dev)")
        return

    # Petite pause pour que l'utilisateur voit l'etape installation
    QTimer.singleShot(800, dlg.close)
    QTimer.singleShot(800, QApplication.quit)

    if is_installer:
        # Lancer l'installeur Inno Setup et quitter
        QTimer.singleShot(400, lambda: subprocess.Popen(
            [str(new_file), "/SILENT", "/CLOSEAPPLICATIONS"]
        ))
    else:
        # Fallback : batch replace (exe brut)
        batch_path = _create_updater_batch(str(new_file), sys.executable)
        QTimer.singleShot(400, lambda: subprocess.Popen(
            ["cmd.exe", "/c", str(batch_path)],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        ))


def _create_updater_batch(new_exe, current_exe):
    """Cree le script batch de mise a jour"""
    batch_path = Path(tempfile.gettempdir()) / "mystrow_update" / "update_mystrow.bat"
    batch_content = f'''@echo off
echo Mise a jour MyStrow en cours...
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
