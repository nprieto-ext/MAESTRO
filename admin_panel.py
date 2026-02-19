"""
Panneau d'administration MyStrow — interface graphique autonome.
Lancer avec : python admin_panel.py
"""

import os
import sys
import json
import secrets
import string
import urllib.request
from datetime import datetime, timezone
import subprocess
import shutil
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDialog, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QAbstractItemView, QFrame, QMessageBox, QTextEdit,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QColor

import firebase_client as fc
from core import FIREBASE_PROJECT_ID
import email_sender

try:
    from release import (
        get_current_version, bump_version, update_version,
        generate_sig_file, GITHUB_REPO,
        BASE_DIR as _RELEASE_DIR,
        _gh_api as _release_gh_api,
    )
    _RELEASE_OK = True
except Exception:
    _RELEASE_OK = False

# Firebase Admin SDK (suppression compte Auth)
try:
    import firebase_admin
    from firebase_admin import credentials as fa_credentials
    from firebase_admin import auth as fa_auth
    _ADMIN_SDK_AVAILABLE = True
except ImportError:
    _ADMIN_SDK_AVAILABLE = False

SERVICE_ACCOUNT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_account.json")
_fa_app = None


def _init_firebase_admin() -> bool:
    """Initialise le SDK Admin Firebase (une seule fois). Retourne True si OK."""
    global _fa_app
    if _fa_app is not None:
        return True
    if not _ADMIN_SDK_AVAILABLE or not os.path.exists(SERVICE_ACCOUNT_PATH):
        return False
    try:
        try:
            _fa_app = firebase_admin.get_app()
        except ValueError:
            cred   = fa_credentials.Certificate(SERVICE_ACCOUNT_PATH)
            _fa_app = firebase_admin.initialize_app(cred)
        return True
    except Exception as e:
        print(f"[Firebase Admin] ERREUR init : {e}")
        return False


def _delete_auth_user(uid: str) -> bool:
    """Supprime un compte Firebase Auth via le SDK Admin."""
    if not _init_firebase_admin():
        raise Exception(
            f"SDK Admin non disponible.\n"
            f"Chemin : {SERVICE_ACCOUNT_PATH}\n"
            f"Fichier présent : {os.path.exists(SERVICE_ACCOUNT_PATH)}"
        )
    fa_auth.delete_user(uid)
    return True

# ---------------------------------------------------------------
# Constantes / Palette
# ---------------------------------------------------------------

ADMIN_CACHE = os.path.join(os.path.expanduser("~"), ".maestro_admin.json")

_FS_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
    f"/databases/(default)/documents"
)

BG_MAIN  = "#1a1a1a"
BG_PANEL = "#111111"
BG_INPUT = "#2a2a2a"
ACCENT   = "#00d4ff"
GREEN    = "#2d7a3a"
ORANGE   = "#c47f17"
RED      = "#a83232"
TEXT     = "#ffffff"
TEXT_DIM = "#aaaaaa"

STYLE_APP = f"""
    QMainWindow, QDialog {{ background: {BG_MAIN}; }}
    QWidget {{ background: {BG_MAIN}; color: {TEXT}; font-family: 'Segoe UI', sans-serif; }}
    QLabel {{ color: {TEXT}; border: none; background: transparent; }}
    QLineEdit {{
        background: {BG_INPUT}; color: {TEXT};
        border: 1px solid #3a3a3a; border-radius: 4px;
        padding: 8px; font-size: 12px;
    }}
    QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
    QComboBox {{
        background: {BG_INPUT}; color: {TEXT};
        border: 1px solid #3a3a3a; border-radius: 4px;
        padding: 6px 8px; font-size: 12px; min-width: 120px;
    }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {BG_INPUT}; color: {TEXT};
        selection-background-color: {ACCENT}; selection-color: #000;
    }}
    QTableWidget {{
        background: {BG_INPUT}; color: {TEXT};
        gridline-color: #333; border: none; font-size: 12px;
        alternate-background-color: #222222;
    }}
    QTableWidget::item {{ padding: 6px; }}
    QTableWidget::item:selected {{ background: #2a4a5a; color: {TEXT}; }}
    QHeaderView::section {{
        background: {BG_PANEL}; color: {TEXT_DIM};
        border: none; border-bottom: 1px solid #333;
        padding: 6px; font-size: 11px; font-weight: bold;
    }}
    QScrollBar:vertical {{
        background: {BG_INPUT}; width: 8px; border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: #444; border-radius: 4px; min-height: 20px;
    }}
    QMessageBox {{ background: {BG_MAIN}; }}
"""

_BTN_PRIMARY = f"""
    QPushButton {{
        background: {ACCENT}; color: #000; border: none;
        border-radius: 4px; font-weight: bold; font-size: 12px; padding: 8px 16px;
    }}
    QPushButton:hover {{ background: #33e0ff; }}
    QPushButton:disabled {{ background: #555; color: #888; }}
"""
_BTN_GREEN = f"""
    QPushButton {{
        background: {GREEN}; color: white; border: none;
        border-radius: 4px; font-weight: bold; font-size: 12px; padding: 8px 16px;
    }}
    QPushButton:hover {{ background: #3a9a4a; }}
    QPushButton:disabled {{ background: #555; color: #888; }}
"""
_BTN_SECONDARY = f"""
    QPushButton {{
        background: {BG_INPUT}; color: {TEXT_DIM}; border: 1px solid #444;
        border-radius: 4px; font-size: 11px; padding: 8px 14px;
    }}
    QPushButton:hover {{ background: #3a3a3a; color: white; }}
    QPushButton:disabled {{ color: #555; }}
"""
_BTN_RED = f"""
    QPushButton {{
        background: {RED}; color: white; border: none;
        border-radius: 4px; font-size: 11px; padding: 5px 10px;
    }}
    QPushButton:hover {{ background: #cc3333; }}
    QPushButton:disabled {{ background: #555; color: #888; }}
"""
_BTN_ORANGE = f"""
    QPushButton {{
        background: {ORANGE}; color: white; border: none;
        border-radius: 4px; font-weight: bold; font-size: 12px; padding: 8px 16px;
    }}
    QPushButton:hover {{ background: #d4901e; }}
    QPushButton:disabled {{ background: #555; color: #888; }}
"""


# ---------------------------------------------------------------
# Helpers (portés depuis create_client.py)
# ---------------------------------------------------------------

def _generate_temp_password(length: int = 20) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(chars) for _ in range(length))


def _fmt_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m/%Y")


def _expiry_from_months(months: int, base: float = None) -> float:
    if base is None:
        base = datetime.now(timezone.utc).timestamp()
    return base + months * 30 * 86400


def _delete_firestore_doc(path: str, id_token: str) -> bool:
    url = f"{_FS_BASE}/{path}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {id_token}"},
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()
    return True


def _patch_firestore(path: str, fields: dict, id_token: str, mask: list = None):
    url = f"{_FS_BASE}/{path}"
    if mask:
        url += "?" + "&".join(f"updateMask.fieldPaths={f}" for f in mask)
    payload = json.dumps({"fields": fields}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {id_token}",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _query_all_licenses(id_token: str) -> list:
    url = f"{_FS_BASE}/licenses"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {id_token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    docs = data.get("documents", [])
    results = []
    for doc in docs:
        uid = doc["name"].split("/")[-1]
        fields = {k: fc._from_firestore(v) for k, v in doc.get("fields", {}).items()}
        fields["_uid"] = uid
        results.append(fields)
    return results


def _fetch_license_doc(uid: str, id_token: str) -> dict:
    url = f"{_FS_BASE}/licenses/{uid}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {id_token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        doc = json.loads(resp.read().decode())
    fields = {k: fc._from_firestore(v) for k, v in doc.get("fields", {}).items()}
    fields["_uid"] = uid
    return fields


# ---------------------------------------------------------------
# Cache admin
# ---------------------------------------------------------------

def _load_admin_cache() -> dict:
    if os.path.exists(ADMIN_CACHE):
        try:
            with open(ADMIN_CACHE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_admin_cache(email: str, refresh_token: str):
    try:
        with open(ADMIN_CACHE, "w") as f:
            json.dump({"email": email, "refresh_token": refresh_token}, f)
    except Exception:
        pass


def _clear_admin_cache():
    try:
        os.remove(ADMIN_CACHE)
    except Exception:
        pass


# ---------------------------------------------------------------
# Worker thread générique
# ---------------------------------------------------------------

class _Worker(QObject):
    success = Signal(object)
    error   = Signal(str)

    def __init__(self, fn, args, kwargs):
        super().__init__()
        self._fn     = fn
        self._args   = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.success.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


def _run_async(parent, fn, *args, on_success=None, on_error=None, **kwargs):
    """Lance fn(*args) dans un QThread séparé pour ne pas bloquer l'UI."""
    thread = QThread()  # Pas de parent Qt — évite le warning cross-thread
    worker = _Worker(fn, args, kwargs)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    if on_success:
        worker.success.connect(on_success)
    if on_error:
        worker.error.connect(on_error)
    worker.success.connect(thread.quit)
    worker.error.connect(thread.quit)
    if not hasattr(parent, "_async_threads"):
        parent._async_threads = []
    parent._async_threads.append((thread, worker))
    thread.finished.connect(lambda: _gc_thread(parent, thread))
    thread.start()


def _gc_thread(parent, thread):
    if hasattr(parent, "_async_threads"):
        parent._async_threads = [(t, w) for t, w in parent._async_threads if t is not thread]


# ---------------------------------------------------------------
# LoginDialog
# ---------------------------------------------------------------

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MyStrow Admin — Connexion")
        self.setFixedSize(360, 290)
        self.id_token      = None
        self.refresh_token = None
        self.email         = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 32, 32, 32)
        lay.setSpacing(14)

        title = QLabel("MyStrow — Admin")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT};")
        lay.addWidget(title)

        sub = QLabel("Connexion administrateur")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        lay.addWidget(sub)
        lay.addSpacing(4)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Email admin")
        self.email_edit.setMinimumHeight(38)
        lay.addWidget(self.email_edit)

        self.pwd_edit = QLineEdit()
        self.pwd_edit.setPlaceholderText("Mot de passe")
        self.pwd_edit.setEchoMode(QLineEdit.Password)
        self.pwd_edit.setMinimumHeight(38)
        self.pwd_edit.returnPressed.connect(self._on_login)
        lay.addWidget(self.pwd_edit)

        self.err_label = QLabel("")
        self.err_label.setStyleSheet(f"color: {RED}; font-size: 11px;")
        self.err_label.setAlignment(Qt.AlignCenter)
        self.err_label.setWordWrap(True)
        self.err_label.setMinimumHeight(16)
        lay.addWidget(self.err_label)

        self.btn_login = QPushButton("Se connecter")
        self.btn_login.setMinimumHeight(40)
        self.btn_login.setStyleSheet(_BTN_PRIMARY)
        self.btn_login.clicked.connect(self._on_login)
        lay.addWidget(self.btn_login)

    def _on_login(self):
        email = self.email_edit.text().strip()
        pwd   = self.pwd_edit.text()
        if not email or not pwd:
            self.err_label.setText("Veuillez remplir tous les champs.")
            return
        self.btn_login.setEnabled(False)
        self.btn_login.setText("Connexion…")
        self.err_label.setText("")
        _run_async(
            self, fc.sign_in, email, pwd,
            on_success=self._on_ok,
            on_error=self._on_err,
        )

    def _on_ok(self, auth):
        _save_admin_cache(auth["email"], auth["refresh_token"])
        self.id_token      = auth["id_token"]
        self.refresh_token = auth["refresh_token"]
        self.email         = auth["email"]
        self.accept()

    def _on_err(self, msg):
        self.err_label.setText(msg)
        self.btn_login.setEnabled(True)
        self.btn_login.setText("Se connecter")


# ---------------------------------------------------------------
# CreateClientDialog
# ---------------------------------------------------------------

class CreateClientDialog(QDialog):
    client_created = Signal()

    def __init__(self, id_token: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nouveau client")
        self.setFixedSize(420, 310)
        self._id_token = id_token
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(14)

        title = QLabel("Créer un nouveau client")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lay.addWidget(title)

        lay.addWidget(QLabel("Email du client :"))
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("client@example.com")
        self.email_edit.setMinimumHeight(36)
        self.email_edit.textChanged.connect(self._update_summary)
        lay.addWidget(self.email_edit)

        dur_lay = QHBoxLayout()
        dur_lay.addWidget(QLabel("Durée de la licence :"))
        self.months_combo = QComboBox()
        for months, label in [(1, "1 mois"), (3, "3 mois"), (6, "6 mois (défaut)"), (12, "12 mois")]:
            self.months_combo.addItem(label, months)
        self.months_combo.setCurrentIndex(2)
        self.months_combo.currentIndexChanged.connect(self._update_summary)
        dur_lay.addWidget(self.months_combo)
        lay.addLayout(dur_lay)

        self.summary_lbl = QLabel("")
        self.summary_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        self.summary_lbl.setWordWrap(True)
        lay.addWidget(self.summary_lbl)
        self._update_summary()

        self.err_label = QLabel("")
        self.err_label.setStyleSheet(f"color: {RED}; font-size: 11px;")
        self.err_label.setWordWrap(True)
        self.err_label.setMinimumHeight(16)
        lay.addWidget(self.err_label)

        btns = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setStyleSheet(_BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("Créer le client")
        self.btn_ok.setStyleSheet(_BTN_PRIMARY)
        self.btn_ok.clicked.connect(self._on_create)
        btns.addWidget(btn_cancel)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

    def _update_summary(self):
        months = self.months_combo.currentData()
        expiry = _expiry_from_months(months)
        self.summary_lbl.setText(
            f"Licence {months} mois — expire le {_fmt_date(expiry)}\n"
            "Un email de définition de mot de passe sera envoyé automatiquement."
        )

    def _on_create(self):
        email  = self.email_edit.text().strip()
        months = self.months_combo.currentData()
        if not email or "@" not in email:
            self.err_label.setText("Adresse email invalide.")
            return
        self.btn_ok.setEnabled(False)
        self.btn_ok.setText("Création en cours…")
        self.err_label.setText("")
        _run_async(
            self, self._do_create, email, months,
            on_success=self._on_ok,
            on_error=self._on_err,
        )

    def _do_create(self, email: str, months: int) -> str:
        expiry   = _expiry_from_months(months)
        temp_pwd = _generate_temp_password()
        auth     = fc.sign_up(email, temp_pwd)
        uid      = auth["uid"]
        fields   = {k: fc._to_firestore(v) for k, v in {
            "email":       email,
            "plan":        "license",
            "expiry_utc":  expiry,
            "created_utc": datetime.now(timezone.utc).timestamp(),
            "machines":    [],
        }.items()}
        _patch_firestore(f"licenses/{uid}", fields, self._id_token)  # token admin
        email_sender.send_welcome(email, expiry, temp_pwd)
        return email

    def _on_ok(self, email: str):
        self.client_created.emit()
        QMessageBox.information(
            self, "Client créé",
            f"Compte créé pour {email}.\n"
            "Un email de définition de mot de passe a été envoyé."
        )
        self.accept()

    def _on_err(self, msg: str):
        self.err_label.setText(msg)
        self.btn_ok.setEnabled(True)
        self.btn_ok.setText("Créer le client")


# ---------------------------------------------------------------
# RenewDialog
# ---------------------------------------------------------------

class RenewDialog(QDialog):
    renewed = Signal()

    def __init__(self, client: dict, id_token: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Renouveler la licence")
        self.setFixedSize(420, 280)
        self._client   = client
        self._id_token = id_token
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(14)

        title = QLabel("Renouveler la licence")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lay.addWidget(title)

        email       = self._client.get("email", "?")
        current_exp = self._client.get("expiry_utc", 0)
        now         = datetime.now(timezone.utc).timestamp()
        if current_exp > now:
            days_left = int((current_exp - now) / 86400)
            exp_str   = f"{_fmt_date(current_exp)} ({days_left}j restants)"
        else:
            exp_str   = f"{_fmt_date(current_exp)} (EXPIRÉ)"

        info = QLabel(f"Client : <b>{email}</b><br>Expiration actuelle : {exp_str}")
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet(f"color: {TEXT_DIM};")
        lay.addWidget(info)

        dur_lay = QHBoxLayout()
        dur_lay.addWidget(QLabel("Prolonger de :"))
        self.months_combo = QComboBox()
        for months, label in [(1, "1 mois"), (3, "3 mois"), (6, "6 mois"), (12, "12 mois")]:
            self.months_combo.addItem(label, months)
        self.months_combo.setCurrentIndex(2)
        self.months_combo.currentIndexChanged.connect(self._update_summary)
        dur_lay.addWidget(self.months_combo)
        dur_lay.addStretch()
        lay.addLayout(dur_lay)

        self.summary_lbl = QLabel("")
        self.summary_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        lay.addWidget(self.summary_lbl)
        self._update_summary()

        self.err_label = QLabel("")
        self.err_label.setStyleSheet(f"color: {RED}; font-size: 11px;")
        self.err_label.setMinimumHeight(16)
        lay.addWidget(self.err_label)

        btns = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setStyleSheet(_BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("Renouveler")
        self.btn_ok.setStyleSheet(_BTN_GREEN)
        self.btn_ok.clicked.connect(self._on_renew)
        btns.addWidget(btn_cancel)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

    def _update_summary(self):
        months      = self.months_combo.currentData()
        current_exp = self._client.get("expiry_utc", 0)
        now         = datetime.now(timezone.utc).timestamp()
        base        = max(current_exp, now)
        new_expiry  = _expiry_from_months(months, base)
        self.summary_lbl.setText(f"Nouvelle expiration : {_fmt_date(new_expiry)}")

    def _on_renew(self):
        months = self.months_combo.currentData()
        self.btn_ok.setEnabled(False)
        self.btn_ok.setText("Renouvellement…")
        self.err_label.setText("")
        _run_async(
            self, self._do_renew, months,
            on_success=self._on_ok,
            on_error=self._on_err,
        )

    def _do_renew(self, months: int) -> float:
        uid         = self._client["_uid"]
        current_exp = self._client.get("expiry_utc", 0)
        now         = datetime.now(timezone.utc).timestamp()
        base        = max(current_exp, now)
        expiry      = _expiry_from_months(months, base)
        fields = {
            "plan":       fc._to_firestore("license"),
            "expiry_utc": fc._to_firestore(expiry),
        }
        _patch_firestore(
            f"licenses/{uid}", fields, self._id_token,
            mask=["plan", "expiry_utc"],
        )
        return expiry

    def _on_ok(self, expiry: float):
        self.renewed.emit()
        try:
            email_sender.send_renewal(self._client.get("email", ""), expiry)
        except Exception:
            pass
        QMessageBox.information(
            self, "Renouvellement effectué",
            f"Licence renouvelée jusqu'au {_fmt_date(expiry)}."
        )
        self.accept()

    def _on_err(self, msg: str):
        self.err_label.setText(msg)
        self.btn_ok.setEnabled(True)
        self.btn_ok.setText("Renouveler")


# ---------------------------------------------------------------
# MachinesDialog
# ---------------------------------------------------------------

class MachinesDialog(QDialog):
    revoked = Signal()

    def __init__(self, client: dict, id_token: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Machines enregistrées")
        self.setFixedSize(500, 300)
        self._client   = client
        self._id_token = id_token
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        email = self._client.get("email", "?")
        title = QLabel(f"Machines — {email}")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lay.addWidget(title)

        self.err_label = QLabel("")
        self.err_label.setStyleSheet(f"color: {RED}; font-size: 11px;")
        self.err_label.setMinimumHeight(16)
        lay.addWidget(self.err_label)

        self.machines_container = QWidget()
        self.machines_lay = QVBoxLayout(self.machines_container)
        self.machines_lay.setContentsMargins(0, 0, 0, 0)
        self.machines_lay.setSpacing(8)
        lay.addWidget(self.machines_container)

        lay.addStretch()

        btn_close = QPushButton("Fermer")
        btn_close.setStyleSheet(_BTN_SECONDARY)
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close, alignment=Qt.AlignRight)

        self._populate_machines()

    def _populate_machines(self):
        # Clear existing widgets
        while self.machines_lay.count():
            item = self.machines_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            else:
                # Layout item — clean up sub-widgets
                pass

        machines = self._client.get("machines", [])
        if not machines:
            no_mach = QLabel("Aucune machine enregistrée.")
            no_mach.setStyleSheet(f"color: {TEXT_DIM};")
            self.machines_lay.addWidget(no_mach)
            return

        for m in machines:
            if not isinstance(m, dict):
                continue
            mid      = m.get("id", "?")
            act_at   = m.get("activated_at", 0)
            act_str  = _fmt_date(act_at) if act_at else "?"
            short_id = mid[:8] + "…"

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel(f"<b>{short_id}</b>&nbsp;&nbsp;—&nbsp;&nbsp;activée le {act_str}")
            lbl.setTextFormat(Qt.RichText)
            lbl.setStyleSheet(f"color: {TEXT_DIM};")
            row_layout.addWidget(lbl)
            row_layout.addStretch()

            btn_rev = QPushButton("Révoquer")
            btn_rev.setStyleSheet(_BTN_RED)
            btn_rev.setFixedWidth(90)
            btn_rev.clicked.connect(lambda checked, machine_id=mid: self._on_revoke(machine_id))
            row_layout.addWidget(btn_rev)

            self.machines_lay.addWidget(row_widget)

    def _on_revoke(self, machine_id: str):
        reply = QMessageBox.question(
            self, "Confirmer la révocation",
            f"Révoquer la machine {machine_id[:8]}… ?\n\n"
            "L'utilisateur devra se reconnecter sur cet appareil.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.err_label.setText("")
        _run_async(
            self, fc.remove_machine,
            self._client["_uid"], self._id_token, machine_id,
            on_success=lambda _: self._after_revoke(),
            on_error=self._on_revoke_err,
        )

    def _after_revoke(self):
        self.revoked.emit()
        _run_async(
            self, _fetch_license_doc,
            self._client["_uid"], self._id_token,
            on_success=self._on_client_refreshed,
            on_error=lambda e: self.err_label.setText(f"Rafraîchissement impossible : {e}"),
        )

    def _on_client_refreshed(self, updated_client: dict):
        self._client = updated_client
        self._populate_machines()

    def _on_revoke_err(self, msg: str):
        self.err_label.setText(f"Erreur : {msg}")


# ---------------------------------------------------------------
# AdminPanel — fenêtre principale
# ---------------------------------------------------------------

class AdminPanel(QMainWindow):
    def __init__(self, id_token: str, refresh_token: str, admin_email: str):
        super().__init__()
        self._id_token      = id_token
        self._refresh_token = refresh_token
        self._admin_email   = admin_email
        self._clients: list = []

        self.setWindowTitle("MyStrow — Admin")
        self.setMinimumSize(900, 580)
        self._build_ui()
        self._load_clients()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # --- Header ---
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(f"background: {BG_PANEL}; border-bottom: 1px solid #333;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)
        h_lay.setSpacing(8)

        title_lbl = QLabel("MyStrow — Admin")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title_lbl.setStyleSheet(f"color: {ACCENT}; background: transparent;")
        h_lay.addWidget(title_lbl)
        h_lay.addStretch()

        self.status_lbl = QLabel(f"Connecté : {self._admin_email}")
        self.status_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent;")
        h_lay.addWidget(self.status_lbl)
        h_lay.addSpacing(12)

        self.btn_refresh = QPushButton("↻  Actualiser")
        self.btn_refresh.setStyleSheet(_BTN_SECONDARY)
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(self._load_clients)
        h_lay.addWidget(self.btn_refresh)
        h_lay.addSpacing(6)

        btn_logout = QPushButton("Déconnexion")
        btn_logout.setStyleSheet(_BTN_RED)
        btn_logout.setFixedHeight(32)
        btn_logout.clicked.connect(self._on_logout)
        h_lay.addWidget(btn_logout)

        main_lay.addWidget(header)

        # --- Chargement ---
        self.loading_lbl = QLabel("Chargement…")
        self.loading_lbl.setAlignment(Qt.AlignCenter)
        self.loading_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px; padding: 20px;")
        self.loading_lbl.hide()
        main_lay.addWidget(self.loading_lbl)

        # --- Tableau ---
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Email", "Plan", "Expiration", "Statut", "Machines"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        main_lay.addWidget(self.table)

        # --- Footer ---
        footer = QFrame()
        footer.setFixedHeight(52)
        footer.setStyleSheet(f"background: {BG_PANEL}; border-top: 1px solid #333;")
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(16, 0, 16, 0)
        f_lay.setSpacing(10)

        self.btn_new = QPushButton("+ Nouveau client")
        self.btn_new.setStyleSheet(_BTN_PRIMARY)
        self.btn_new.setFixedHeight(36)
        self.btn_new.clicked.connect(self._on_new_client)
        f_lay.addWidget(self.btn_new)

        self.btn_renew = QPushButton("Renouveler")
        self.btn_renew.setStyleSheet(_BTN_GREEN)
        self.btn_renew.setFixedHeight(36)
        self.btn_renew.setEnabled(False)
        self.btn_renew.clicked.connect(self._on_renew)
        f_lay.addWidget(self.btn_renew)

        self.btn_machines = QPushButton("Machines")
        self.btn_machines.setStyleSheet(_BTN_SECONDARY)
        self.btn_machines.setFixedHeight(36)
        self.btn_machines.setEnabled(False)
        self.btn_machines.clicked.connect(self._on_machines)
        f_lay.addWidget(self.btn_machines)

        self.btn_delete = QPushButton("Supprimer")
        self.btn_delete.setStyleSheet(_BTN_RED)
        self.btn_delete.setFixedHeight(36)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete)
        f_lay.addWidget(self.btn_delete)

        f_lay.addSpacing(12)
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("QFrame { color: #333; }")
        f_lay.addWidget(sep)
        f_lay.addSpacing(12)

        self.btn_release = QPushButton("⚙  Release…")
        self.btn_release.setStyleSheet(_BTN_ORANGE)
        self.btn_release.setFixedHeight(36)
        self.btn_release.setEnabled(_RELEASE_OK)
        self.btn_release.setToolTip("" if _RELEASE_OK else "release.py introuvable")
        self.btn_release.clicked.connect(self._on_release)
        f_lay.addWidget(self.btn_release)

        f_lay.addStretch()

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; background: transparent;")
        f_lay.addWidget(self.count_lbl)

        main_lay.addWidget(footer)

    # ------------------------------------------------------------------

    def _on_selection_changed(self):
        has_sel = self.table.currentRow() >= 0
        self.btn_renew.setEnabled(has_sel)
        self.btn_machines.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _get_selected_client(self) -> dict | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._clients):
            return self._clients[row]
        return None

    # ------------------------------------------------------------------

    def _load_clients(self):
        self.btn_refresh.setEnabled(False)
        self.loading_lbl.setText("Chargement…")
        self.loading_lbl.show()
        self.table.hide()
        _run_async(
            self, _query_all_licenses, self._id_token,
            on_success=self._on_clients_loaded,
            on_error=self._on_load_error,
        )

    def _on_clients_loaded(self, clients: list):
        clients.sort(key=lambda d: d.get("expiry_utc", 0), reverse=True)
        self._clients = clients
        self._populate_table(clients)
        self.loading_lbl.hide()
        self.table.show()
        self.btn_refresh.setEnabled(True)
        self.count_lbl.setText(f"{len(clients)} compte(s)")

    def _on_load_error(self, msg: str):
        self.loading_lbl.setText(f"Erreur de chargement : {msg}")
        self.table.show()
        self.btn_refresh.setEnabled(True)

    def _populate_table(self, clients: list):
        now = datetime.now(timezone.utc).timestamp()
        self.table.setRowCount(len(clients))
        for row, c in enumerate(clients):
            email    = c.get("email", "?")
            plan     = c.get("plan", "?")
            expiry   = c.get("expiry_utc", 0)
            machines = c.get("machines", [])

            exp_str  = _fmt_date(expiry) if expiry else "?"
            mach_str = f"{len(machines)}/2"
            days_left = int((expiry - now) / 86400) if expiry else -1

            if days_left > 30:
                statut_str   = f"Actif ({days_left}j)"
                statut_color = GREEN
            elif days_left >= 0:
                statut_str   = f"Expire dans {days_left}j"
                statut_color = ORANGE
            else:
                statut_str   = "EXPIRÉ"
                statut_color = RED

            items = [
                QTableWidgetItem(email),
                QTableWidgetItem(plan),
                QTableWidgetItem(exp_str),
                QTableWidgetItem(statut_str),
                QTableWidgetItem(mach_str),
            ]
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                if col == 3:
                    item.setForeground(QColor(statut_color))
                self.table.setItem(row, col, item)

        self.table.resizeRowsToContents()

    # ------------------------------------------------------------------

    def _on_new_client(self):
        dlg = CreateClientDialog(self._id_token, self)
        dlg.client_created.connect(self._load_clients)
        dlg.exec()

    def _on_renew(self):
        client = self._get_selected_client()
        if client is None:
            return
        dlg = RenewDialog(client, self._id_token, self)
        dlg.renewed.connect(self._load_clients)
        dlg.exec()

    def _on_machines(self):
        client = self._get_selected_client()
        if client is None:
            return
        dlg = MachinesDialog(client, self._id_token, self)
        dlg.revoked.connect(self._load_clients)
        dlg.exec()

    def _on_delete(self):
        client = self._get_selected_client()
        if client is None:
            return
        email    = client.get("email", "?")
        uid      = client.get("_uid", "")
        has_sdk  = _init_firebase_admin()
        auth_msg = "Le compte Auth Firebase sera également supprimé." if has_sdk else (
            "⚠️ service_account.json absent — le compte Auth Firebase devra être "
            "supprimé manuellement depuis la console Firebase."
        )
        reply = QMessageBox.warning(
            self, "Supprimer le client",
            f"Supprimer définitivement <b>{email}</b> ?<br><br>{auth_msg}",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return
        self.btn_delete.setEnabled(False)
        _run_async(
            self, self._do_delete, uid,
            on_success=lambda _: self._on_deleted(email, uid),
            on_error=self._on_delete_error,
        )

    def _do_delete(self, uid: str):
        """Supprime le doc Firestore puis le compte Auth (si SDK disponible)."""
        _delete_firestore_doc(f"licenses/{uid}", self._id_token)
        if _init_firebase_admin():
            _delete_auth_user(uid)

    def _on_deleted(self, email: str, uid: str):
        self._load_clients()
        QMessageBox.information(
            self, "Compte supprimé",
            f"{email} a été supprimé (licence + compte Auth)."
        )

    def _on_delete_error(self, msg: str):
        self.btn_delete.setEnabled(True)
        QMessageBox.critical(self, "Erreur suppression", msg)

    def _on_logout(self):
        _clear_admin_cache()
        self.close()
        _show_login_then_panel()

    def _on_release(self):
        dlg = ReleaseDialog(self)
        dlg.exec()


# ---------------------------------------------------------------
# Release Worker & Dialog
# ---------------------------------------------------------------

class ReleaseWorker(QObject):
    """Exécute le pipeline de release dans un QThread séparé."""
    log      = Signal(str)
    finished = Signal(bool, str)   # succès, message

    def __init__(self, version: str, action: str, parent=None):
        super().__init__(parent)
        self._version = version
        self._action  = action   # "local" | "github" | "both"

    def _p(self, msg: str):
        self.log.emit(msg)

    def _run_cmd(self, cmd: str, allow_fail: bool = False, cwd=None) -> int:
        self._p(f">>> {cmd}")
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            cwd=str(cwd or _RELEASE_DIR),
        )
        for line in iter(proc.stdout.readline, ""):
            stripped = line.rstrip()
            if stripped:
                self._p(stripped)
        proc.wait()
        if proc.returncode != 0 and not allow_fail:
            raise RuntimeError(f"Commande échouée (code {proc.returncode}) : {cmd}")
        return proc.returncode

    def run(self):
        try:
            v = self._version
            self._p(f"=== RELEASE MYSTROW v{v} ===\n")
            self._p("Mise à jour des fichiers de version...")
            update_version(v)
            self._p(f"  core.py + maestro.iss → v{v}\n")

            if self._action in ("local", "both"):
                self._build_local(v)

            if self._action in ("github", "both"):
                self._push_github(v)
                self._watch_actions(v)

            self.finished.emit(True, f"Release v{v} terminée avec succès !")
        except Exception as exc:
            self.finished.emit(False, str(exc))

    def _build_local(self, version: str):
        self._p("\n========== BUILD INSTALLEUR LOCAL ==========")
        dist_exe      = _RELEASE_DIR / "dist" / "MyStrow.exe"
        installer_out = _RELEASE_DIR / "installer" / "installer_output" / "MyStrow_Setup.exe"

        # Nettoyage
        self._p("Nettoyage dist/ et build/...")
        for d in ("dist", "build"):
            p = _RELEASE_DIR / d
            if p.exists():
                shutil.rmtree(p)

        # PyInstaller via .bat (contourne MINGW)
        self._p("\n--- PyInstaller ---")
        python_win = sys.executable.replace("/", "\\")
        base_win   = str(_RELEASE_DIR).replace("/", "\\")
        bat_path   = _RELEASE_DIR / "_build_tmp.bat"
        bat_path.write_text(
            f"@echo off\r\n"
            f"cd /d \"{base_win}\"\r\n"
            f"\"{python_win}\" -m PyInstaller "
            f"--onefile --windowed "
            f"--icon=mystrow.ico "
            f"--add-data \"logo.png;.\" "
            f"--add-data \"mystrow.ico;.\" "
            f"--name=MyStrow "
            f"--paths=\"{base_win}\" "
            f"--noconfirm main.py\r\n",
            encoding="utf-8",
        )
        bat_win = str(bat_path).replace("/", "\\")
        try:
            self._run_cmd(f'cmd.exe /c "{bat_win}"', cwd=_RELEASE_DIR)
        finally:
            bat_path.unlink(missing_ok=True)

        if not dist_exe.exists():
            raise RuntimeError("MyStrow.exe introuvable après PyInstaller.")

        self._p("\nGénération du fichier .sig...")
        generate_sig_file(dist_exe)

        # Inno Setup
        self._p("\n--- Inno Setup ---")
        iscc_candidates = [
            Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
            Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
            Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
        ]
        iscc = next((p for p in iscc_candidates if p.exists()), None)
        if iscc is None:
            raise RuntimeError("Inno Setup (ISCC.exe) introuvable.")

        self._run_cmd(f'"{iscc}" installer\\maestro.iss', cwd=_RELEASE_DIR)

        if not installer_out.exists():
            raise RuntimeError("MyStrow_Setup.exe introuvable après Inno Setup.")

        desktop = Path.home() / "Desktop"
        dest    = desktop / f"MyStrow_Setup_{version}.exe"
        shutil.copy2(installer_out, dest)
        self._p(f"\nInstalleur copié sur le bureau : {dest}")

    def _push_github(self, version: str):
        self._p("\n========== PUSH GITHUB ==========")
        self._run_cmd("git add -A",                                       cwd=_RELEASE_DIR)
        self._run_cmd(f'git commit -m "Release {version}"', allow_fail=True, cwd=_RELEASE_DIR)
        self._run_cmd(f"git tag v{version}",                              cwd=_RELEASE_DIR)
        self._run_cmd("git push origin main",                             cwd=_RELEASE_DIR)
        self._run_cmd(f"git push origin v{version}",                      cwd=_RELEASE_DIR)
        self._p(f"\n=== TAG v{version} POUSSÉ ===")

    def _watch_actions(self, version: str):
        from datetime import datetime as _dt
        self._p("\nSuivi GitHub Actions (attente démarrage)...")
        run_id = None
        for _ in range(30):
            time.sleep(2)
            data = _release_gh_api("/actions/runs?event=push&per_page=10")
            if data:
                for wr in data.get("workflow_runs", []):
                    if (wr.get("name") == "Build & Release" and
                            version in wr.get("head_commit", {}).get("message", "")):
                        run_id = wr["id"]
                        break
                if not run_id:
                    for wr in data.get("workflow_runs", []):
                        if (wr.get("name") == "Build & Release" and
                                wr.get("status") in ("queued", "in_progress")):
                            run_id = wr["id"]
                            break
            if run_id:
                break
            self._p("  ...")

        if not run_id:
            self._p(f"⚠️  Workflow introuvable. Suivi manuel :\n  https://github.com/{GITHUB_REPO}/actions")
            return

        self._p(f"  Workflow : https://github.com/{GITHUB_REPO}/actions/runs/{run_id}")
        last_state: dict = {}
        ICONS   = {"queued": "⏳", "in_progress": "↻"}
        C_ICONS = {"success": "✅", "failure": "❌", "cancelled": "⚠️", "skipped": "⏭️", None: "↻"}

        while True:
            time.sleep(5)
            run_data = _release_gh_api(f"/actions/runs/{run_id}")
            if not run_data:
                continue
            status     = run_data.get("status", "")
            conclusion = run_data.get("conclusion")
            jobs_data  = _release_gh_api(f"/actions/runs/{run_id}/jobs")
            jobs       = (jobs_data or {}).get("jobs", [])
            cur_state  = {j["name"]: (j["status"], j.get("conclusion")) for j in jobs}

            if cur_state != last_state:
                lines = []
                for job in jobs:
                    js   = job["status"]
                    jc   = job.get("conclusion")
                    icon = C_ICONS.get(jc, "❓") if js == "completed" else ICONS.get(js, "⏳")
                    dur  = ""
                    if js == "completed" and job.get("started_at") and job.get("completed_at"):
                        t1   = _dt.fromisoformat(job["started_at"].replace("Z", "+00:00"))
                        t2   = _dt.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
                        secs = int((t2 - t1).total_seconds())
                        dur  = f"  ({secs // 60}m{secs % 60:02d}s)"
                    lines.append(f"  {icon}  {job['name']}{dur}")
                self._p("\n".join(lines))
                last_state = cur_state

            if status == "completed":
                if conclusion == "success":
                    self._p(f"\n✅  Release v{version} créée !")
                    self._p(f"    https://github.com/{GITHUB_REPO}/releases/tag/v{version}")
                else:
                    self._p(f"\n❌  Build échoué ({conclusion})")
                    self._p(f"    https://github.com/{GITHUB_REPO}/actions/runs/{run_id}")
                break


class ReleaseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Release MyStrow")
        self.setMinimumSize(720, 540)
        self._thread = None
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(12)

        title = QLabel("Release MyStrow")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet(f"color: {ACCENT};")
        lay.addWidget(title)

        # Version
        v_lay = QHBoxLayout()
        current = get_current_version() or "?"
        v_lay.addWidget(QLabel(f"Version actuelle :  <b>{current}</b>", textFormat=Qt.RichText))
        v_lay.addSpacing(24)
        v_lay.addWidget(QLabel("Nouvelle version :"))
        self.version_edit = QLineEdit(bump_version(current) if current != "?" else "")
        self.version_edit.setFixedWidth(110)
        self.version_edit.setMinimumHeight(32)
        v_lay.addWidget(self.version_edit)
        v_lay.addStretch()
        lay.addLayout(v_lay)

        # Action
        a_lay = QHBoxLayout()
        a_lay.addWidget(QLabel("Action :"))
        self.action_combo = QComboBox()
        self.action_combo.addItem("Installeur local + Push GitHub", "both")
        self.action_combo.addItem("Installeur local seulement (Bureau)", "local")
        self.action_combo.addItem("Push GitHub seulement (CI)", "github")
        self.action_combo.setMinimumWidth(300)
        a_lay.addWidget(self.action_combo)
        a_lay.addStretch()
        lay.addLayout(a_lay)

        # Boutons
        btns = QHBoxLayout()
        self.btn_start = QPushButton("Lancer la release")
        self.btn_start.setStyleSheet(_BTN_PRIMARY)
        self.btn_start.setFixedHeight(36)
        self.btn_start.clicked.connect(self._on_start)
        btns.addWidget(self.btn_start)
        self.btn_close = QPushButton("Fermer")
        self.btn_close.setStyleSheet(_BTN_SECONDARY)
        self.btn_close.setFixedHeight(36)
        self.btn_close.clicked.connect(self.accept)
        btns.addWidget(self.btn_close)
        btns.addStretch()
        lay.addLayout(btns)

        # Log
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        self.log_edit.setStyleSheet(
            "QTextEdit {"
            f"  background: #0d0d0d; color: #cccccc;"
            f"  border: 1px solid #333; border-radius: 4px;"
            "}"
        )
        lay.addWidget(self.log_edit)

    def _on_start(self):
        version = self.version_edit.text().strip()
        if not version:
            QMessageBox.warning(self, "Version manquante", "Veuillez saisir un numéro de version.")
            return
        action = self.action_combo.currentData()
        self.btn_start.setEnabled(False)
        self.btn_start.setText("En cours…")
        self.log_edit.clear()

        self._thread = QThread(self)
        self._worker = ReleaseWorker(version, action)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _append_log(self, text: str):
        self.log_edit.append(text)
        sb = self.log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, success: bool, msg: str):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("Lancer la release")
        if success:
            self._append_log(f"\n{msg}")
        else:
            self._append_log(f"\nERREUR : {msg}")
            QMessageBox.critical(self, "Erreur release", msg)


# ---------------------------------------------------------------
# Démarrage / login flow
# ---------------------------------------------------------------

def _show_login_then_panel():
    """Affiche LoginDialog puis AdminPanel. Quitte si annulé."""
    app = QApplication.instance()
    if app:
        app.setQuitOnLastWindowClosed(False)

    dlg = LoginDialog()
    result = dlg.exec()

    if app:
        app.setQuitOnLastWindowClosed(True)

    if result != QDialog.Accepted:
        if app:
            app.quit()
        return

    panel = AdminPanel(dlg.id_token, dlg.refresh_token, dlg.email)
    panel.show()
    if app:
        app._admin_panel = panel  # Prevent garbage collection


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MyStrow Admin")
    app.setStyleSheet(STYLE_APP)

    # Tenter de restaurer la session depuis le cache
    id_token = refresh_token = admin_email = None
    cache = _load_admin_cache()
    if cache.get("refresh_token"):
        try:
            tok          = fc.refresh_id_token(cache["refresh_token"])
            id_token     = tok["id_token"]
            refresh_token = tok.get("refresh_token", cache["refresh_token"])
            admin_email  = cache.get("email", "")
            _save_admin_cache(admin_email, refresh_token)
        except Exception:
            pass

    if id_token:
        panel = AdminPanel(id_token, refresh_token, admin_email)
        panel.show()
        app._admin_panel = panel
    else:
        _show_login_then_panel()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
