"""
Interface utilisateur pour le systeme de licence Maestro.py
Widgets Qt : banniere, dialogue d'activation, avertissement
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QDialog, QTabWidget, QLineEdit, QMessageBox, QProgressBar,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QCursor

from license_manager import (
    LicenseState, LicenseResult,
    activate_trial, activate_license, verify_license
)


# ============================================================
# BANNIERE DE LICENCE (barre horizontale coloree)
# ============================================================

class LicenseBanner(QWidget):
    """
    Banniere horizontale affichant l'etat de la licence.
    Meme pattern que UpdateBar dans updater.py.
    Couleurs : vert=actif, orange=avertissement, rouge=bloque.
    """

    activate_clicked = Signal()

    # Couleurs par etat
    COLORS = {
        "green": "#2d7a3a",
        "orange": "#c47f17",
        "red": "#a83232",
        "hidden": None,
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
                color: white;
                background: rgba(255,255,255,0.2);
                border: 1px solid rgba(255,255,255,0.5);
                border-radius: 4px;
                padding: 3px 14px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.3);
            }
        """)
        self.action_btn.clicked.connect(self.activate_clicked)
        self.action_btn.hide()
        layout.addWidget(self.action_btn)

    def apply_license(self, result: LicenseResult):
        """Applique l'etat de licence a la banniere"""
        state = result.state

        # LICENSE_ACTIVE sans avertissement = banniere cachee
        if state == LicenseState.LICENSE_ACTIVE and not result.show_warning:
            self.hide()
            return

        # Determiner la couleur
        if state == LicenseState.TRIAL_ACTIVE and not result.show_warning:
            color = self.COLORS["green"]
        elif state in (LicenseState.TRIAL_ACTIVE, LicenseState.LICENSE_ACTIVE):
            # show_warning=True
            color = self.COLORS["orange"]
        else:
            # NOT_ACTIVATED, INVALID, FRAUD_CLOCK, TRIAL_EXPIRED, LICENSE_EXPIRED
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
# DIALOGUE D'ACTIVATION
# ============================================================

class ActivationDialog(QDialog):
    """
    Dialogue modal avec 2 onglets : Essai gratuit / Licence.
    Style sombre coherent avec l'application.
    """

    activation_success = Signal()  # Emis apres activation reussie

    def __init__(self, parent=None, license_result=None):
        super().__init__(parent)
        self.setWindowTitle("Activation - Maestro.py")
        self.setFixedSize(420, 340)

        self.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: white; border: none; }
            QLineEdit {
                background: #2a2a2a; color: white;
                border: 1px solid #3a3a3a; border-radius: 4px;
                padding: 8px; font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #00d4ff;
            }
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                background: #1a1a1a;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #2a2a2a; color: #aaa;
                padding: 8px 20px; border: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #1a1a1a; color: white;
                border-bottom: 2px solid #00d4ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        title = QLabel("Activer Maestro.py")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #00d4ff;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Afficher les jours restants si periode d'essai active
        if license_result and license_result.state == LicenseState.TRIAL_ACTIVE:
            days = license_result.days_remaining
            days_label = QLabel(f"Periode d'essai : {days} jour{'s' if days > 1 else ''} restant{'s' if days > 1 else ''}")
            days_label.setFont(QFont("Segoe UI", 11))
            days_label.setStyleSheet("color: #00d4ff; font-weight: bold;")
            days_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(days_label)

        # Onglets
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # === Onglet Essai ===
        trial_page = QWidget()
        trial_layout = QVBoxLayout(trial_page)
        trial_layout.setContentsMargins(15, 15, 15, 10)
        trial_layout.setSpacing(10)

        trial_layout.addWidget(QLabel("Essai gratuit de 15 jours (toutes fonctionnalites)"))

        self.trial_btn = QPushButton("Demarrer l'essai gratuit")
        self.trial_btn.setFixedHeight(36)
        self.trial_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.trial_btn.setStyleSheet("""
            QPushButton {
                background: #2d7a3a; color: white; border: none;
                border-radius: 4px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #3a9a4a; }
            QPushButton:disabled { background: #555; color: #888; }
        """)
        self.trial_btn.clicked.connect(self._activate_trial)
        trial_layout.addWidget(self.trial_btn)
        trial_layout.addStretch()

        self.tabs.addTab(trial_page, "Essai gratuit")

        # === Onglet Licence ===
        license_page = QWidget()
        license_layout = QVBoxLayout(license_page)
        license_layout.setContentsMargins(15, 15, 15, 10)
        license_layout.setSpacing(10)

        license_layout.addWidget(QLabel("Entrez votre cle de licence :"))

        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.key_edit.setFont(QFont("Consolas", 14))
        self.key_edit.setAlignment(Qt.AlignCenter)
        license_layout.addWidget(self.key_edit)

        self.license_btn = QPushButton("Activer la licence")
        self.license_btn.setFixedHeight(36)
        self.license_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.license_btn.setStyleSheet("""
            QPushButton {
                background: #00d4ff; color: #000; border: none;
                border-radius: 4px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #33e0ff; }
            QPushButton:disabled { background: #555; color: #888; }
        """)
        self.license_btn.clicked.connect(self._activate_license)
        license_layout.addWidget(self.license_btn)

        # Lien vers le site d'achat
        buy_link = QLabel('<a href="https://mystrow.fr/" style="color: #00d4ff;">Acheter une licence sur mystrow.fr</a>')
        buy_link.setOpenExternalLinks(True)
        buy_link.setAlignment(Qt.AlignCenter)
        buy_link.setFont(QFont("Segoe UI", 10))
        license_layout.addWidget(buy_link)

        license_layout.addStretch()

        self.tabs.addTab(license_page, "Cle de licence")

        # Barre de progression (cachee par defaut)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar { background: #333; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #00d4ff; border-radius: 2px; }
        """)
        self.progress.hide()
        layout.addWidget(self.progress)

        # Label status
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.status_label)

        # Bouton Fermer
        close_btn = QPushButton("Fermer")
        close_btn.setFixedHeight(30)
        close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        close_btn.setStyleSheet("""
            QPushButton {
                color: #aaa; background: #333; border: 1px solid #555;
                border-radius: 4px; padding: 4px 20px; font-size: 10px;
            }
            QPushButton:hover { background: #444; color: white; }
        """)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

    def _set_busy(self, busy):
        """Active/desactive le mode chargement"""
        self.trial_btn.setEnabled(not busy)
        self.license_btn.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            self.status_label.setStyleSheet("color: #aaa; font-size: 11px;")
            self.status_label.setText("Activation en cours...")
        QApplication.processEvents()

    def _show_result(self, success, message):
        """Affiche le resultat de l'activation"""
        if success:
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        else:
            self.status_label.setStyleSheet("color: #ff5555; font-size: 11px;")
        self.status_label.setText(message)

    def _activate_trial(self):
        """Lance l'activation d'essai"""
        self._set_busy(True)

        success, message = activate_trial()

        self._set_busy(False)
        self._show_result(success, message)

        if success:
            self.activation_success.emit()
            QTimer.singleShot(1500, self.accept)

    def _activate_license(self):
        """Lance l'activation de licence"""
        key = self.key_edit.text().strip()
        if not key:
            self._show_result(False, "Entrez une cle de licence")
            return

        self._set_busy(True)

        success, message = activate_license(key)

        self._set_busy(False)
        self._show_result(success, message)

        if success:
            self.activation_success.emit()
            QTimer.singleShot(1500, self.accept)


# ============================================================
# DIALOGUE D'AVERTISSEMENT (expire bientot)
# ============================================================

class LicenseWarningDialog(QDialog):
    """
    Dialogue affiche une fois au demarrage quand l'essai ou la licence
    arrive bientot a expiration.
    """

    def __init__(self, result: LicenseResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Maestro.py - Licence")
        self.setFixedSize(380, 180)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: white; border: none; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(12)

        # Icone + titre
        if result.state == LicenseState.TRIAL_ACTIVE:
            title_text = "Essai gratuit bientot termine"
            color = "#c47f17"
        else:
            title_text = "Abonnement bientot expire"
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

        # Boutons
        btn_layout = QHBoxLayout()

        btn_later = QPushButton("Continuer")
        btn_later.setFixedHeight(32)
        btn_later.setCursor(QCursor(Qt.PointingHandCursor))
        btn_later.setStyleSheet("""
            QPushButton {
                color: white; background: #333; border: 1px solid #555;
                border-radius: 4px; padding: 4px 20px; font-size: 11px;
            }
            QPushButton:hover { background: #444; }
        """)
        btn_later.clicked.connect(self.accept)
        btn_layout.addWidget(btn_later)

        btn_activate = QPushButton(result.action_label or "Activer")
        btn_activate.setFixedHeight(32)
        btn_activate.setCursor(QCursor(Qt.PointingHandCursor))
        btn_activate.setStyleSheet("""
            QPushButton {
                color: white; background: #00d4ff; color: #000;
                border: none; border-radius: 4px; padding: 4px 20px;
                font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background: #33e0ff; }
        """)
        btn_activate.clicked.connect(lambda: self.done(2))  # Code 2 = ouvrir activation
        btn_layout.addWidget(btn_activate)

        layout.addLayout(btn_layout)
