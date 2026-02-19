"""
Interface utilisateur pour le systeme de licence MyStrow (Firebase)
Widgets Qt : banniere, dialogue login/register, avertissement
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QProgressBar, QApplication, QStackedWidget,
    QCheckBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QCursor

from license_manager import (
    LicenseState, LicenseResult,
    login_account, verify_license,
    deactivate_machine, get_license_info,
)


# ============================================================
# STYLE COMMUN
# ============================================================

_DIALOG_STYLE = """
    QDialog { background: #1a1a1a; }
    QLabel { color: white; border: none; }
    QLineEdit {
        background: #2a2a2a; color: white;
        border: 1px solid #3a3a3a; border-radius: 4px;
        padding: 8px; font-size: 12px;
    }
    QLineEdit:focus { border: 1px solid #00d4ff; }
    QCheckBox { color: #aaa; font-size: 10px; }
    QCheckBox::indicator { width: 14px; height: 14px; }
"""

_BTN_PRIMARY = """
    QPushButton {
        background: #00d4ff; color: #000; border: none;
        border-radius: 4px; font-weight: bold; font-size: 12px;
    }
    QPushButton:hover { background: #33e0ff; }
    QPushButton:disabled { background: #555; color: #888; }
"""

_BTN_SECONDARY = """
    QPushButton {
        background: #2a2a2a; color: #aaa; border: 1px solid #444;
        border-radius: 4px; font-size: 11px;
    }
    QPushButton:hover { background: #3a3a3a; color: white; }
    QPushButton:disabled { color: #555; }
"""

_BTN_GREEN = """
    QPushButton {
        background: #2d7a3a; color: white; border: none;
        border-radius: 4px; font-weight: bold; font-size: 12px;
    }
    QPushButton:hover { background: #3a9a4a; }
    QPushButton:disabled { background: #555; color: #888; }
"""


# ============================================================
# BANNIERE DE LICENCE (barre horizontale coloree)
# ============================================================

class LicenseBanner(QWidget):
    """
    Banniere horizontale affichant l'etat du compte/licence.
    Couleurs : vert=actif, orange=avertissement, rouge=bloque.
    """

    activate_clicked = Signal()

    COLORS = {
        "green": "#2d7a3a",
        "orange": "#c47f17",
        "red": "#a83232",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(10)

        self.label = QLabel()
        self.label.setFont(QFont("Segoe UI", 10))
        self.label.setStyleSheet("color: white;")
        layout.addWidget(self.label, 1)

        self.action_btn = QPushButton()
        self.action_btn.setFixedHeight(26)
        self.action_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.action_btn.setStyleSheet("""
            QPushButton {
                color: white; background: rgba(255,255,255,0.2);
                border: 1px solid rgba(255,255,255,0.5);
                border-radius: 4px; padding: 3px 14px;
                font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { background: rgba(255,255,255,0.3); }
        """)
        self.action_btn.clicked.connect(self.activate_clicked)
        self.action_btn.hide()
        layout.addWidget(self.action_btn)

    def apply_license(self, result: LicenseResult):
        """Applique l'etat de licence a la banniere."""
        state = result.state

        if state == LicenseState.LICENSE_ACTIVE and not result.show_warning:
            self.hide()
            return

        if state == LicenseState.TRIAL_ACTIVE and not result.show_warning:
            color = self.COLORS["green"]
        elif state in (LicenseState.TRIAL_ACTIVE, LicenseState.LICENSE_ACTIVE):
            color = self.COLORS["orange"]
        else:
            color = self.COLORS["red"]

        self.setStyleSheet(f"background: {color};")
        self.label.setText(result.message)

        if result.action_label:
            self.action_btn.setText(result.action_label)
            self.action_btn.show()
        else:
            self.action_btn.hide()

        self.show()


# ============================================================
# DIALOGUE LOGIN (essai expire → connexion compte)
# ============================================================

class ActivationDialog(QDialog):
    """
    Dialogue de connexion au compte MyStrow (Firebase).
    Pas d'auto-inscription : l'essai est automatique, le compte est cree par le dev.

    Pages :
      0 — Formulaire login (email + mdp)
      1 — Succes
      2 — Compte connecte (si deja logue)
    """

    activation_success = Signal()

    def __init__(self, parent=None, license_result=None):
        super().__init__(parent)
        self.setWindowTitle("MyStrow — Connexion")
        self.setFixedSize(400, 320)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowContextHelpButtonHint
            | Qt.WindowCloseButtonHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_page_login())    # 0
        self._stack.addWidget(self._build_page_success())  # 1
        self._stack.addWidget(self._build_page_account())  # 2

        already_logged = (
            license_result is not None
            and license_result.state not in (LicenseState.NOT_ACTIVATED, LicenseState.INVALID)
        )
        if already_logged:
            self._refresh_account_page(license_result)
            self._stack.setCurrentIndex(2)
            self.setWindowTitle("MyStrow — Mon compte")
        else:
            self._stack.setCurrentIndex(0)

    # ----------------------------------------------------------
    # Constructeurs de pages
    # ----------------------------------------------------------

    def _page_frame(self, title_text, subtitle=""):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 20)
        layout.setSpacing(12)

        title = QLabel(title_text)
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #00d4ff;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setFont(QFont("Segoe UI", 10))
            sub.setStyleSheet("color: #aaa;")
            sub.setAlignment(Qt.AlignCenter)
            sub.setWordWrap(True)
            layout.addWidget(sub)

        return page, layout

    def _build_page_login(self):
        page, layout = self._page_frame(
            "Connexion",
            "Entrez vos identifiants pour activer MyStrow."
        )

        self._email_edit = QLineEdit()
        self._email_edit.setPlaceholderText("Email")
        self._email_edit.setFixedHeight(36)
        self._email_edit.returnPressed.connect(self._do_login)
        layout.addWidget(self._email_edit)

        self._pwd_edit = QLineEdit()
        self._pwd_edit.setPlaceholderText("Mot de passe")
        self._pwd_edit.setEchoMode(QLineEdit.Password)
        self._pwd_edit.setFixedHeight(36)
        self._pwd_edit.returnPressed.connect(self._do_login)
        layout.addWidget(self._pwd_edit)

        self._login_progress = QProgressBar()
        self._login_progress.setRange(0, 0)
        self._login_progress.setFixedHeight(3)
        self._login_progress.setTextVisible(False)
        self._login_progress.setStyleSheet(
            "QProgressBar{background:#333;border:none;border-radius:1px;}"
            "QProgressBar::chunk{background:#00d4ff;border-radius:1px;}"
        )
        self._login_progress.hide()
        layout.addWidget(self._login_progress)

        self._login_status = QLabel()
        self._login_status.setAlignment(Qt.AlignCenter)
        self._login_status.setFont(QFont("Segoe UI", 10))
        self._login_status.setWordWrap(True)
        layout.addWidget(self._login_status)

        layout.addStretch()

        contact = QLabel(
            'Pas encore de compte ? '
            '<a href="https://mystrow.fr/contact" style="color:#00d4ff;">Contactez-nous</a>'
        )
        contact.setOpenExternalLinks(True)
        contact.setAlignment(Qt.AlignCenter)
        contact.setFont(QFont("Segoe UI", 9))
        layout.addWidget(contact)

        btn_row = QHBoxLayout()

        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(36)
        btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        btn_close.setStyleSheet(_BTN_SECONDARY)
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        self._btn_login = QPushButton("Se connecter")
        self._btn_login.setFixedHeight(36)
        self._btn_login.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_login.setStyleSheet(_BTN_PRIMARY)
        self._btn_login.clicked.connect(self._do_login)
        btn_row.addWidget(self._btn_login)

        layout.addLayout(btn_row)

        return page

    def _build_page_success(self):
        page, layout = self._page_frame("Connexion reussie")

        self._success_label = QLabel()
        self._success_label.setFont(QFont("Segoe UI", 11))
        self._success_label.setStyleSheet("color: #4CAF50;")
        self._success_label.setAlignment(Qt.AlignCenter)
        self._success_label.setWordWrap(True)
        layout.addWidget(self._success_label)

        layout.addStretch()

        btn_ok = QPushButton("Demarrer MyStrow")
        btn_ok.setFixedHeight(36)
        btn_ok.setCursor(QCursor(Qt.PointingHandCursor))
        btn_ok.setStyleSheet(_BTN_PRIMARY)
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)
        return page

    def _build_page_account(self):
        page, layout = self._page_frame("Mon compte")

        self._acct_email = QLabel()
        self._acct_email.setFont(QFont("Segoe UI", 11))
        self._acct_email.setStyleSheet("color: #00d4ff;")
        self._acct_email.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._acct_email)

        self._acct_plan = QLabel()
        self._acct_plan.setFont(QFont("Segoe UI", 11))
        self._acct_plan.setAlignment(Qt.AlignCenter)
        self._acct_plan.setWordWrap(True)
        layout.addWidget(self._acct_plan)

        self._acct_machine = QLabel()
        self._acct_machine.setFont(QFont("Segoe UI", 10))
        self._acct_machine.setStyleSheet("color: #888;")
        self._acct_machine.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._acct_machine)

        layout.addStretch()

        self._acct_logout_status = QLabel()
        self._acct_logout_status.setAlignment(Qt.AlignCenter)
        self._acct_logout_status.setFont(QFont("Segoe UI", 10))
        self._acct_logout_status.setWordWrap(True)
        layout.addWidget(self._acct_logout_status)

        btn_row = QHBoxLayout()

        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(32)
        btn_close.setStyleSheet(_BTN_SECONDARY)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        btn_logout = QPushButton("Se deconnecter")
        btn_logout.setFixedHeight(32)
        btn_logout.setStyleSheet("""
            QPushButton {
                background: #5a1a1a; color: #ff8888; border: 1px solid #8a3a3a;
                border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover { background: #7a2a2a; color: white; }
        """)
        btn_logout.setCursor(QCursor(Qt.PointingHandCursor))
        btn_logout.clicked.connect(self._do_logout)
        self._btn_logout = btn_logout
        btn_row.addWidget(btn_logout)

        layout.addLayout(btn_row)
        return page

    def _refresh_account_page(self, license_result: LicenseResult):
        """Remplit la page compte avec les infos actuelles."""
        info = get_license_info()
        email = info.get("email", "—")
        plan = info.get("plan", "trial")

        self._acct_email.setText(email)

        if license_result.state == LicenseState.LICENSE_ACTIVE:
            plan_text = "Licence active"
            if license_result.days_remaining:
                plan_text += f"  ({license_result.days_remaining} jours restants)"
            self._acct_plan.setStyleSheet("color: #4CAF50;")
        elif license_result.state == LicenseState.TRIAL_ACTIVE:
            plan_text = f"Periode d'essai  ({license_result.days_remaining} jours restants)"
            self._acct_plan.setStyleSheet("color: #c47f17;")
        elif license_result.state == LicenseState.TRIAL_EXPIRED:
            plan_text = "Essai expire"
            self._acct_plan.setStyleSheet("color: #ff5555;")
        elif license_result.state == LicenseState.LICENSE_EXPIRED:
            plan_text = "Licence expiree"
            self._acct_plan.setStyleSheet("color: #ff5555;")
        else:
            plan_text = license_result.message or "Etat inconnu"
            self._acct_plan.setStyleSheet("color: #aaa;")

        self._acct_plan.setText(plan_text)
        self._acct_machine.setText("Cette machine est activee")
        self._acct_logout_status.clear()

    def _do_logout(self):
        """Deconnecte cette machine."""
        self._btn_logout.setEnabled(False)
        self._acct_logout_status.setStyleSheet("color: #aaa;")
        self._acct_logout_status.setText("Deconnexion en cours...")
        QApplication.processEvents()

        success, message = deactivate_machine()

        if success:
            self._acct_logout_status.setStyleSheet("color: #4CAF50;")
            self._acct_logout_status.setText("Deconnecte. Redemarrez l'application.")
            self._btn_logout.hide()
        else:
            self._acct_logout_status.setStyleSheet("color: #ff5555;")
            self._acct_logout_status.setText(message)
            self._btn_logout.setEnabled(True)

    # ----------------------------------------------------------
    # Logique login
    # ----------------------------------------------------------

    def _do_login(self):
        email = self._email_edit.text().strip()
        pwd   = self._pwd_edit.text()

        if not email or "@" not in email:
            self._login_status.setStyleSheet("color: #ff5555;")
            self._login_status.setText("Adresse email invalide.")
            return
        if not pwd:
            self._login_status.setStyleSheet("color: #ff5555;")
            self._login_status.setText("Entrez votre mot de passe.")
            return

        self._btn_login.setEnabled(False)
        self._login_progress.show()
        self._login_status.setStyleSheet("color: #aaa;")
        self._login_status.setText("Connexion en cours...")
        QApplication.processEvents()

        success, message = login_account(email, pwd)

        self._login_progress.hide()
        self._btn_login.setEnabled(True)

        if success:
            self._success_label.setText(f"Bienvenue !\n{message}")
            self._stack.setCurrentIndex(1)
            self.activation_success.emit()
            QTimer.singleShot(2000, self.accept)
        else:
            self._login_status.setStyleSheet("color: #ff5555;")
            self._login_status.setText(message)


# ============================================================
# DIALOGUE D'AVERTISSEMENT (expire bientot)
# ============================================================

class LicenseWarningDialog(QDialog):
    """
    Dialogue affiche au demarrage quand l'essai ou la licence
    arrive bientot a expiration.
    """

    def __init__(self, result: LicenseResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MyStrow — Compte")
        self.setFixedSize(380, 190)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowContextHelpButtonHint
            | Qt.WindowCloseButtonHint
        )

        self.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: white; border: none; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(12)

        if result.state == LicenseState.TRIAL_ACTIVE:
            title_text = "Essai bientot termine"
            color = "#c47f17"
        else:
            title_text = "Licence bientot expiree"
            color = "#c47f17"

        title = QLabel(title_text)
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet(f"color: {color};")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        msg = QLabel(result.message)
        msg.setFont(QFont("Segoe UI", 11))
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        layout.addWidget(msg)

        layout.addStretch()

        btn_layout = QHBoxLayout()

        btn_later = QPushButton("Continuer")
        btn_later.setFixedHeight(32)
        btn_later.setCursor(QCursor(Qt.PointingHandCursor))
        btn_later.setStyleSheet(_BTN_SECONDARY)
        btn_later.clicked.connect(self.accept)
        btn_layout.addWidget(btn_later)

        btn_activate = QPushButton(result.action_label or "Mon compte")
        btn_activate.setFixedHeight(32)
        btn_activate.setCursor(QCursor(Qt.PointingHandCursor))
        btn_activate.setStyleSheet(_BTN_PRIMARY)
        btn_activate.clicked.connect(lambda: self.done(2))
        btn_layout.addWidget(btn_activate)

        layout.addLayout(btn_layout)
