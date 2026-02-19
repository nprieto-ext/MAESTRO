"""
Assistant de connexion et configuration du Node DMX
- Détection rapide au démarrage (ArtPoll 0.5 s sur l'IP cible)
- Sélection explicite de la carte réseau (jamais automatique)
- Configuration IPv4 2.0.0.1 automatique ou manuelle
- Guide MA Lighting (grandMA2)
- Guide Electroconcept : câbles RJ45 + USB, configuration TCP/IP, recherche node
"""

import re
import socket
import time
import subprocess
import platform
from typing import List, Tuple, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QFont, QDesktopServices, QCursor

# ============================================================
# CONSTANTES
# ============================================================

TARGET_IP   = "2.0.0.15"
TARGET_PORT = 6454

GRANDMA2_URL = "https://www.malighting.com/downloads/products/grandma2/"

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0

# Mots-clés pour ignorer les adaptateurs non-Ethernet physiques
_SKIP_ADAPTERS = [
    "wi-fi", "wifi", "wireless", "loopback", "vmware", "virtual",
    "bluetooth", "tunnel", "teredo", "isatap", "6to4", "miniport",
    "local*",       # Connexion au réseau local* = Wi-Fi Direct virtuel
    "vethernet",    # Hyper-V virtual switch
]

# IPs à scanner pour MA Lighting (scan large)
MA_SCAN_IPS = [
    "2.0.0.15", "2.0.0.1", "2.0.0.2",
    "192.168.1.1", "192.168.1.100", "192.168.0.1",
    "10.0.0.1", "10.0.0.2",
]

# Index des pages
P_DETECTING   = 0
P_CONNECTED   = 1
P_CHOOSE      = 2
P_MA          = 3
P_EC_CABLES   = 4
P_WORKING     = 5
P_NET_MANUAL  = 6
P_SUCCESS     = 7
P_MA_RETRY    = 8
P_NET_SELECT  = 9   # Sélection de la carte réseau Node
P_NET_METHOD  = 10  # Choix auto / manuel


# ============================================================
# UTILITAIRES RÉSEAU (module-level, réutilisables par les threads)
# ============================================================

def _artpoll_packet() -> bytes:
    p = bytearray(b'Art-Net\x00')
    p.extend(b'\x00\x20')  # OpCode ArtPoll
    p.extend(b'\x00\x0e')  # Protocol version 14
    p.extend(b'\x00\x00')  # TalkToMe + Priority
    return bytes(p)


def _open_network_connections():
    """Ouvre le panneau Connexions réseau Windows."""
    try:
        subprocess.Popen(["control", "ncpa.cpl"],
                         creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass


def _get_ethernet_adapters() -> List[Tuple[str, str]]:
    """
    Retourne [(nom_interface, ipv4)] pour tous les adaptateurs réseau actifs.
    Parse ipconfig /all — robuste quelle que soit la locale Windows.
    """
    try:
        r = subprocess.run(
            ["ipconfig", "/all"],
            capture_output=True, text=True,
            encoding="cp1252", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        return []

    adapters     = []
    current_name = None
    current_ip   = ""
    skip_current = False

    for line in r.stdout.splitlines():
        # Ligne de section : ne commence pas par un espace, se termine par ":"
        # (avec possible \xa0 ou espace insécable avant le ":")
        stripped_line = line.strip()
        is_section = (
            line
            and not line.startswith("\t")
            and not line.startswith(" ")
            and stripped_line.endswith(":")
        )

        if is_section:
            # Enregistrer l'adaptateur précédent si valide
            if current_name and not skip_current:
                adapters.append((current_name, current_ip))

            # Extraire le nom : retirer le préfixe de catégorie
            raw = stripped_line.rstrip(":").strip()
            for prefix in (
                "Carte Ethernet ", "Ethernet adapter ",
                "Carte réseau sans fil ", "Wireless LAN adapter ",
                "Adaptateur ", "Adapter ",
            ):
                if raw.lower().startswith(prefix.lower()):
                    raw = raw[len(prefix):]
                    break

            current_name = raw.strip()
            current_ip   = ""
            # Filtrer Wi-Fi, Bluetooth, Virtual, Tunnel, Loopback…
            skip_current = any(kw in current_name.lower() for kw in _SKIP_ADAPTERS)
            continue

        if not current_name or skip_current:
            continue

        stripped = line.strip()

        low = stripped.lower()
        # Tunnel = jamais pertinent
        if "tunnel" in low:
            skip_current = True
            continue

        # Adresse IPv4 — regex pour ignorer "(Préféré)"/"(Preferred)" collé à l'IP
        if "ipv4" in low:
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", stripped)
            if m:
                ip = m.group(1)
                if not ip.startswith("127."):
                    current_ip = ip

    # Dernier adaptateur
    if current_name and not skip_current:
        adapters.append((current_name, current_ip))

    return adapters


def _set_static_ip(adapter_name: str) -> bool:
    """Configure l'IP statique 2.0.0.1/255.0.0.0 via netsh. Requiert les droits admin."""
    try:
        r = subprocess.run(
            [
                "netsh", "interface", "ip", "set", "address",
                f"name={adapter_name}",
                "static", "2.0.0.1", "255.0.0.0",
            ],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )
        return r.returncode == 0
    except Exception:
        return False


# ============================================================
# THREADS
# ============================================================

class QuickDetector(QThread):
    """ArtPoll sur TARGET_IP avec timeout court (0.5 s). Pas de scan large."""
    finished = Signal(bool)

    def run(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.sendto(_artpoll_packet(), (TARGET_IP, TARGET_PORT))
            data, _ = s.recvfrom(256)
            s.close()
            self.finished.emit(data[:8] == b'Art-Net\x00')
        except Exception:
            self.finished.emit(False)


class AdapterScanner(QThread):
    """Scanne les adaptateurs Ethernet connectés de façon asynchrone."""
    done = Signal(list)   # list of (name, ip)

    def run(self):
        self.done.emit(_get_ethernet_adapters())


class NetworkSetup(QThread):
    """
    Configure l'IP statique 2.0.0.1/255.0.0.0 sur l'adaptateur choisi.
    Émet : ('ok'|'manual', adapter_name)
    """
    done = Signal(str, str)

    def __init__(self, adapter_name: str):
        super().__init__()
        self.adapter_name = adapter_name

    def run(self):
        if _set_static_ip(self.adapter_name):
            time.sleep(1.5)
            self.done.emit("ok", self.adapter_name)
        else:
            self.done.emit("manual", self.adapter_name)


class NodeSearcher(QThread):
    """ArtPoll sur TARGET_IP avec timeout 2 s, après stabilisation réseau."""
    finished = Signal(bool)

    def run(self):
        time.sleep(0.5)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2.0)
            s.sendto(_artpoll_packet(), (TARGET_IP, TARGET_PORT))
            data, _ = s.recvfrom(256)
            s.close()
            self.finished.emit(data[:8] == b'Art-Net\x00')
        except Exception:
            self.finished.emit(False)


class FullScanner(QThread):
    """Scan ArtPoll broadcast + liste d'IPs connues (MA Lighting)."""
    finished = Signal(bool, str)   # found, ip

    def run(self):
        pkt = _artpoll_packet()
        for ip in MA_SCAN_IPS:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.6)
                s.sendto(pkt, (ip, TARGET_PORT))
                data, addr = s.recvfrom(256)
                s.close()
                if data[:8] == b'Art-Net\x00':
                    self.finished.emit(True, addr[0])
                    return
            except Exception:
                pass
        for bcast in ["2.255.255.255", "255.255.255.255",
                      "192.168.1.255", "192.168.0.255", "10.255.255.255"]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.settimeout(1.5)
                s.sendto(pkt, (bcast, TARGET_PORT))
                data, addr = s.recvfrom(256)
                s.close()
                if data[:8] == b'Art-Net\x00':
                    self.finished.emit(True, addr[0])
                    return
            except Exception:
                pass
        self.finished.emit(False, "")


# ============================================================
# STYLES
# ============================================================

_S_DIALOG = "QDialog { background: #1a1a1a; } QLabel { color: #cccccc; border: none; } QFrame { border: none; }"

_BTN_PRIMARY = """
QPushButton {
    background: #00d4ff; color: #000; font-weight: bold;
    font-size: 12px; padding: 0 24px; border-radius: 4px; border: none;
}
QPushButton:hover    { background: #33e0ff; }
QPushButton:disabled { background: #333; color: #666; }
"""

_BTN_SECONDARY = """
QPushButton {
    background: #2a2a2a; color: #cccccc; font-size: 11px;
    border: 1px solid #3a3a3a; padding: 0 18px; border-radius: 4px;
}
QPushButton:hover { background: #333; color: white; }
"""

_BTN_SUCCESS = """
QPushButton {
    background: #2d7a3a; color: white; font-weight: bold;
    font-size: 12px; padding: 0 24px; border-radius: 4px; border: none;
}
QPushButton:hover { background: #3a9a4a; }
"""

_BTN_BRAND = """
QPushButton {
    background: #222222; color: white; font-size: 14px; font-weight: bold;
    border: 2px solid #333333; border-radius: 6px; padding: 0; text-align: center;
}
QPushButton:hover { border-color: #00d4ff; background: #272727; }
"""

_BTN_ADAPTER = """
QPushButton {
    background: #222222; color: #cccccc; font-size: 10px;
    border: 1px solid #333333; border-radius: 5px;
    text-align: left; padding: 8px 14px;
}
QPushButton:hover { background: #2a2a2a; border-color: #00d4ff; color: white; }
"""

_BTN_ADAPTER_OK = """
QPushButton {
    background: #192619; color: #4CAF50; font-size: 10px;
    border: 1px solid #2a4a2a; border-radius: 5px;
    text-align: left; padding: 8px 14px;
}
QPushButton:hover { background: #1e331e; color: #66bb6a; }
"""

_BOX_STYLE = """
QLabel {
    color: #cccccc; background: #222222;
    border: 1px solid #333333; border-radius: 6px; padding: 14px 16px;
}
"""

_BOX_WARN = """
QLabel {
    color: #ffcc44; background: #2a2200;
    border: 1px solid #554400; border-radius: 6px; padding: 12px 16px;
}
"""

_BOX_INFO = """
QLabel {
    color: #aaaaaa; background: #1e2030;
    border: 1px solid #2a2e44; border-radius: 6px; padding: 10px 14px;
}
"""


# ============================================================
# DIALOG
# ============================================================

class NodeConnectionDialog(QDialog):
    """Assistant de connexion et configuration du Node DMX."""

    _PAGE_HEADERS = {
        P_DETECTING:  ("Sortie Node DMX",    "Vérification de la connexion..."),
        P_CONNECTED:  ("Connexion réussie",  "Votre boîtier est opérationnel"),
        P_CHOOSE:     ("Configuration",      "Identification de votre boîtier"),
        P_MA:         ("MA Lighting",        "Installation du logiciel requis"),
        P_EC_CABLES:  ("Electroconcept",     "Connexion des câbles"),
        P_WORKING:    ("Electroconcept",     "Configuration en cours..."),
        P_NET_MANUAL: ("Electroconcept",     "Configuration réseau manuelle"),
        P_SUCCESS:    ("Connexion réussie",  "Votre boîtier est opérationnel"),
        P_MA_RETRY:   ("MA Lighting",        "Boîtier introuvable"),
        P_NET_SELECT: ("Electroconcept",     "Sélection de la carte réseau"),
        P_NET_METHOD: ("Electroconcept",     "Configuration de l'adresse IP"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connexion – Sortie Node")
        self.setFixedSize(500, 460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(_S_DIALOG)

        self._adapter_name: str = ""
        self._net_came_from_method: bool = False

        # Threads (un seul actif à la fois)
        self._q_detect:     Optional[QuickDetector]  = None
        self._adapter_scan: Optional[AdapterScanner] = None
        self._net_setup:    Optional[NetworkSetup]   = None
        self._node_srch:    Optional[NodeSearcher]   = None
        self._full_scan:    Optional[FullScanner]    = None

        # Spinner
        self._spin_frames = ["◐", "◓", "◑", "◒"]
        self._spin_idx = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick)

        self._build_ui()
        QTimer.singleShot(150, self._start_quick_detection)

    # ──────────────────────────────────────────────────────
    # CONSTRUCTION
    # ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(68)
        hdr.setStyleSheet("QFrame { background: #111111; border-bottom: 1px solid #2a2a2a; }")
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(28, 8, 28, 8)
        hl.setSpacing(2)
        self._lbl_title = QLabel("Sortie Node DMX")
        self._lbl_title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self._lbl_title.setStyleSheet("color: #00d4ff; background: transparent;")
        hl.addWidget(self._lbl_title)
        self._lbl_sub = QLabel("Vérification de la connexion...")
        self._lbl_sub.setFont(QFont("Segoe UI", 9))
        self._lbl_sub.setStyleSheet("color: #555555; background: transparent;")
        hl.addWidget(self._lbl_sub)
        root.addWidget(hdr)

        # Stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: #1a1a1a;")
        root.addWidget(self._stack, 1)

        self._stack.addWidget(self._pg_detecting())    # 0
        self._stack.addWidget(self._pg_connected())    # 1
        self._stack.addWidget(self._pg_choose())       # 2
        self._stack.addWidget(self._pg_ma())           # 3
        self._stack.addWidget(self._pg_ec_cables())    # 4
        self._stack.addWidget(self._pg_working())      # 5
        self._stack.addWidget(self._pg_net_manual())   # 6
        self._stack.addWidget(self._pg_success())      # 7
        self._stack.addWidget(self._pg_ma_retry())     # 8
        self._stack.addWidget(self._pg_net_select())   # 9
        self._stack.addWidget(self._pg_net_method())   # 10

        # Footer
        ftr = QFrame()
        ftr.setFixedHeight(58)
        ftr.setStyleSheet("QFrame { background: #111111; border-top: 1px solid #2a2a2a; }")
        fl = QHBoxLayout(ftr)
        fl.setContentsMargins(28, 0, 28, 0)

        self._btn_back = QPushButton("← Retour")
        self._btn_back.setStyleSheet(_BTN_SECONDARY)
        self._btn_back.setFixedHeight(32)
        self._btn_back.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_back.clicked.connect(self._on_back)
        self._btn_back.hide()
        fl.addWidget(self._btn_back)
        fl.addStretch()

        self._btn_close = QPushButton("Fermer")
        self._btn_close.setStyleSheet(_BTN_SECONDARY)
        self._btn_close.setFixedHeight(32)
        self._btn_close.setCursor(QCursor(Qt.PointingHandCursor))
        self._btn_close.clicked.connect(self.accept)
        fl.addWidget(self._btn_close)

        root.addWidget(ftr)

    # ──────────────────────────────────────────────────────
    # PAGES
    # ──────────────────────────────────────────────────────

    def _page(self, align=Qt.AlignTop, spacing=12, m=(44, 28, 44, 28)):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(align)
        lay.setSpacing(spacing)
        lay.setContentsMargins(*m)
        return w, lay

    # 0 — Détection initiale
    def _pg_detecting(self):
        w, lay = self._page(Qt.AlignCenter, 14)
        self._spin_lbl = QLabel("◐")
        self._spin_lbl.setFont(QFont("Segoe UI", 40))
        self._spin_lbl.setStyleSheet("color: #00d4ff;")
        self._spin_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._spin_lbl)
        lbl = QLabel("Vérification de la connexion...")
        lbl.setFont(QFont("Segoe UI", 11))
        lbl.setStyleSheet("color: #777777;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)
        return w

    # 1 — Boîtier déjà connecté
    def _pg_connected(self):
        w, lay = self._page(Qt.AlignCenter, 10)
        ok = QLabel("✓")
        ok.setFont(QFont("Segoe UI", 44))
        ok.setStyleSheet("color: #4CAF50;")
        ok.setAlignment(Qt.AlignCenter)
        lay.addWidget(ok)
        lbl = QLabel("Votre boîtier DMX est connecté avec succès.")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl.setStyleSheet("color: white;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self._connected_ip_lbl = QLabel()
        self._connected_ip_lbl.setFont(QFont("Segoe UI", 10))
        self._connected_ip_lbl.setStyleSheet("color: #555555;")
        self._connected_ip_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._connected_ip_lbl)
        return w

    # 2 — Choix de la marque
    def _pg_choose(self):
        w, lay = self._page(Qt.AlignTop, 14, (50, 32, 50, 32))
        lbl = QLabel("Quel est votre boîtier DMX ?")
        lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl.setStyleSheet("color: white;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)
        lay.addSpacing(6)
        for text, page in [("MA Lighting", P_MA), ("Electroconcept", P_EC_CABLES)]:
            btn = QPushButton(text)
            btn.setStyleSheet(_BTN_BRAND)
            btn.setFixedHeight(58)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.clicked.connect(lambda _, p=page: self._go_to(p))
            lay.addWidget(btn)
        return w

    # 3 — MA Lighting
    def _pg_ma(self):
        w, lay = self._page(Qt.AlignTop, 10, (44, 20, 44, 20))
        icon = QLabel("💻")
        icon.setFont(QFont("Segoe UI", 28))
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        lbl = QLabel("Votre boîtier nécessite l'installation\ndu logiciel grandMA2.")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl.setStyleSheet("color: white;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        note = QLabel("Cette manipulation est à faire une seule fois.")
        note.setFont(QFont("Segoe UI", 10))
        note.setStyleSheet("color: #666666;")
        note.setAlignment(Qt.AlignCenter)
        lay.addWidget(note)
        lay.addSpacing(4)
        btn_dl = QPushButton("Télécharger grandMA2")
        btn_dl.setStyleSheet(_BTN_PRIMARY)
        btn_dl.setFixedHeight(40)
        btn_dl.setCursor(QCursor(Qt.PointingHandCursor))
        btn_dl.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GRANDMA2_URL)))
        lay.addWidget(btn_dl)
        lay.addSpacing(4)
        btn_done = QPushButton("J'ai terminé  →")
        btn_done.setStyleSheet(_BTN_SUCCESS)
        btn_done.setFixedHeight(40)
        btn_done.setCursor(QCursor(Qt.PointingHandCursor))
        btn_done.clicked.connect(self._start_ma_search)
        lay.addWidget(btn_done)
        return w

    # 4 — Electroconcept : brancher les 2 câbles
    def _pg_ec_cables(self):
        w, lay = self._page(Qt.AlignTop, 10, (44, 16, 44, 16))
        lbl = QLabel("Avant de continuer, vérifiez que votre\nboîtier est bien branché sur les 2 ports :")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lbl.setStyleSheet("color: white;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        rj45 = QLabel(
            "🔵  Câble RJ45 (Ethernet)\n"
            "       Branché entre le boîtier et votre ordinateur\n"
            "       → C'est par là que passent les données DMX"
        )
        rj45.setFont(QFont("Segoe UI", 10))
        rj45.setStyleSheet(_BOX_STYLE)
        rj45.setWordWrap(True)
        lay.addWidget(rj45)
        usb = QLabel(
            "🔴  Câble USB carré (USB-B)\n"
            "       Branché sur une prise secteur OU sur un port USB de l'ordinateur\n"
            "       → Alimentation électrique du boîtier uniquement"
        )
        usb.setFont(QFont("Segoe UI", 10))
        usb.setStyleSheet(_BOX_STYLE)
        usb.setWordWrap(True)
        lay.addWidget(usb)
        btn = QPushButton("Les 2 câbles sont branchés  →")
        btn.setStyleSheet(_BTN_PRIMARY)
        btn.setFixedHeight(40)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.clicked.connect(self._start_adapter_scan)
        lay.addWidget(btn)
        return w

    # 5 — Spinner générique
    def _pg_working(self):
        w, lay = self._page(Qt.AlignCenter, 14)
        self._work_spin_lbl = QLabel("◐")
        self._work_spin_lbl.setFont(QFont("Segoe UI", 40))
        self._work_spin_lbl.setStyleSheet("color: #00d4ff;")
        self._work_spin_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._work_spin_lbl)
        self._work_status_lbl = QLabel("")
        self._work_status_lbl.setFont(QFont("Segoe UI", 11))
        self._work_status_lbl.setStyleSheet("color: #888888;")
        self._work_status_lbl.setAlignment(Qt.AlignCenter)
        self._work_status_lbl.setWordWrap(True)
        lay.addWidget(self._work_status_lbl)
        self._work_detail_lbl = QLabel("")
        self._work_detail_lbl.setFont(QFont("Segoe UI", 10))
        self._work_detail_lbl.setStyleSheet("color: #555555;")
        self._work_detail_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._work_detail_lbl)
        return w

    # 6 — Configuration réseau manuelle
    def _pg_net_manual(self):
        w, lay = self._page(Qt.AlignTop, 8, (40, 12, 40, 12))
        title = QLabel("Configuration réseau requise")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        self._manual_ctx_lbl = QLabel()
        self._manual_ctx_lbl.setFont(QFont("Segoe UI", 10))
        self._manual_ctx_lbl.setStyleSheet("color: #777777;")
        self._manual_ctx_lbl.setAlignment(Qt.AlignCenter)
        self._manual_ctx_lbl.setWordWrap(True)
        lay.addWidget(self._manual_ctx_lbl)
        self._manual_steps_lbl = QLabel()
        self._manual_steps_lbl.setFont(QFont("Segoe UI", 10))
        self._manual_steps_lbl.setStyleSheet(_BOX_STYLE)
        self._manual_steps_lbl.setWordWrap(True)
        lay.addWidget(self._manual_steps_lbl)
        btn_net = QPushButton("Ouvrir les connexions réseau")
        btn_net.setStyleSheet(_BTN_SECONDARY)
        btn_net.setFixedHeight(32)
        btn_net.setCursor(QCursor(Qt.PointingHandCursor))
        btn_net.clicked.connect(_open_network_connections)
        lay.addWidget(btn_net)
        sep_row = QHBoxLayout()
        sep_row.setContentsMargins(0, 2, 0, 2)
        line1 = QFrame(); line1.setFrameShape(QFrame.HLine); line1.setStyleSheet("color: #333333;")
        sep_row.addWidget(line1, 1)
        sep_lbl = QLabel("  ou  "); sep_lbl.setFont(QFont("Segoe UI", 9)); sep_lbl.setStyleSheet("color: #555555;")
        sep_row.addWidget(sep_lbl)
        line2 = QFrame(); line2.setFrameShape(QFrame.HLine); line2.setStyleSheet("color: #333333;")
        sep_row.addWidget(line2, 1)
        lay.addLayout(sep_row)
        btn_admin = QPushButton("Relancer MyStrow en administrateur")
        btn_admin.setStyleSheet(_BTN_SECONDARY)
        btn_admin.setFixedHeight(32)
        btn_admin.setCursor(QCursor(Qt.PointingHandCursor))
        btn_admin.clicked.connect(self._restart_as_admin)
        lay.addWidget(btn_admin)
        admin_note = QLabel("MyStrow configurera l'IP automatiquement au démarrage.")
        admin_note.setFont(QFont("Segoe UI", 9))
        admin_note.setStyleSheet("color: #555555;")
        admin_note.setAlignment(Qt.AlignCenter)
        lay.addWidget(admin_note)
        btn_done = QPushButton("J'ai configuré  →  Rechercher le boîtier")
        btn_done.setStyleSheet(_BTN_SUCCESS)
        btn_done.setFixedHeight(36)
        btn_done.setCursor(QCursor(Qt.PointingHandCursor))
        btn_done.clicked.connect(self._start_node_search)
        lay.addWidget(btn_done)
        return w

    # 7 — Succès
    def _pg_success(self):
        w, lay = self._page(Qt.AlignCenter, 12)
        ok = QLabel("✓")
        ok.setFont(QFont("Segoe UI", 44))
        ok.setStyleSheet("color: #4CAF50;")
        ok.setAlignment(Qt.AlignCenter)
        lay.addWidget(ok)
        lbl = QLabel("Connexion établie !")
        lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl.setStyleSheet("color: white;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)
        self._success_sub_lbl = QLabel("Votre boîtier est prêt\nà recevoir les données DMX.")
        self._success_sub_lbl.setFont(QFont("Segoe UI", 10))
        self._success_sub_lbl.setStyleSheet("color: #666666;")
        self._success_sub_lbl.setAlignment(Qt.AlignCenter)
        self._success_sub_lbl.setWordWrap(True)
        lay.addWidget(self._success_sub_lbl)
        return w

    # 8 — MA Lighting : boîtier non trouvé
    def _pg_ma_retry(self):
        w, lay = self._page(Qt.AlignCenter, 14)
        icon = QLabel("✗")
        icon.setFont(QFont("Segoe UI", 44))
        icon.setStyleSheet("color: #e05050;")
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        lbl = QLabel("Boîtier MA Lighting introuvable")
        lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl.setStyleSheet("color: white;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        hint = QLabel(
            "Vérifiez que le câble RJ45 est branché\n"
            "et que grandMA2 est bien installé et lancé."
        )
        hint.setFont(QFont("Segoe UI", 10))
        hint.setStyleSheet("color: #777777;")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addSpacing(6)
        btn_retry = QPushButton("Réessayer")
        btn_retry.setStyleSheet(_BTN_PRIMARY)
        btn_retry.setFixedHeight(40)
        btn_retry.setCursor(QCursor(Qt.PointingHandCursor))
        btn_retry.clicked.connect(self._start_ma_search)
        lay.addWidget(btn_retry)
        return w

    # 9 — Sélection de la carte réseau (contenu dynamique)
    def _pg_net_select(self):
        w, lay = self._page(Qt.AlignTop, 10, (28, 18, 28, 18))

        title = QLabel("Sélectionnez la carte réseau du Node DMX")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        lay.addWidget(title)

        warn = QLabel(
            "⚠   Choisissez uniquement la carte RJ45 dédiée au Node.\n"
            "      Ne pas sélectionner la carte Wi-Fi ou la carte Internet."
        )
        warn.setFont(QFont("Segoe UI", 10))
        warn.setStyleSheet(_BOX_WARN)
        warn.setWordWrap(True)
        lay.addWidget(warn)

        # Zone de défilement pour les cartes (nombre variable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { background: #222; width: 6px; border-radius: 3px; }"
            "QScrollBar::handle:vertical { background: #444; border-radius: 3px; }"
        )
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._adapters_layout = QVBoxLayout(inner)
        self._adapters_layout.setSpacing(6)
        self._adapters_layout.setContentsMargins(0, 0, 0, 0)
        self._adapters_layout.addStretch()

        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        return w

    # 10 — Choix de la méthode de configuration
    def _pg_net_method(self):
        w, lay = self._page(Qt.AlignTop, 10, (44, 24, 44, 24))

        title = QLabel("Souhaitez-vous configurer l'IP automatiquement ?")
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        lay.addWidget(title)

        self._net_method_adapter_lbl = QLabel()
        self._net_method_adapter_lbl.setFont(QFont("Segoe UI", 10))
        self._net_method_adapter_lbl.setStyleSheet("color: #888888;")
        self._net_method_adapter_lbl.setAlignment(Qt.AlignCenter)
        self._net_method_adapter_lbl.setWordWrap(True)
        lay.addWidget(self._net_method_adapter_lbl)

        target = QLabel(
            "Adresse IP à configurer :    2 . 0 . 0 . 1\n"
            "Masque de sous-réseau :  255 . 0 . 0 . 0"
        )
        target.setFont(QFont("Segoe UI", 10))
        target.setStyleSheet(_BOX_STYLE)
        target.setAlignment(Qt.AlignCenter)
        lay.addWidget(target)

        admin_note = QLabel(
            "ⓘ  Si Maestro ne dispose pas des droits administrateur,\n"
            "      un redémarrage en mode admin sera proposé."
        )
        admin_note.setFont(QFont("Segoe UI", 9))
        admin_note.setStyleSheet(_BOX_INFO)
        admin_note.setWordWrap(True)
        admin_note.setAlignment(Qt.AlignCenter)
        lay.addWidget(admin_note)

        lay.addSpacing(4)

        btn_auto = QPushButton("Oui, configurer automatiquement  →")
        btn_auto.setStyleSheet(_BTN_PRIMARY)
        btn_auto.setFixedHeight(40)
        btn_auto.setCursor(QCursor(Qt.PointingHandCursor))
        btn_auto.clicked.connect(self._do_auto_config)
        lay.addWidget(btn_auto)

        btn_manual = QPushButton("Non, je configure moi-même")
        btn_manual.setStyleSheet(_BTN_SECONDARY)
        btn_manual.setFixedHeight(36)
        btn_manual.setCursor(QCursor(Qt.PointingHandCursor))
        btn_manual.clicked.connect(self._show_manual_from_method)
        lay.addWidget(btn_manual)

        return w

    # ──────────────────────────────────────────────────────
    # NAVIGATION
    # ──────────────────────────────────────────────────────

    def _go_to(self, page: int):
        self._stack.setCurrentIndex(page)
        back_pages = {P_MA, P_EC_CABLES, P_NET_MANUAL, P_MA_RETRY,
                      P_NET_SELECT, P_NET_METHOD}
        self._btn_back.setVisible(page in back_pages)
        title, sub = self._PAGE_HEADERS.get(page, ("Sortie Node DMX", ""))
        self._lbl_title.setText(title)
        self._lbl_sub.setText(sub)

    def _on_back(self):
        page = self._stack.currentIndex()
        if page in (P_MA, P_EC_CABLES):
            self._go_to(P_CHOOSE)
        elif page == P_NET_SELECT:
            self._go_to(P_EC_CABLES)
        elif page == P_NET_METHOD:
            self._go_to(P_NET_SELECT)
        elif page == P_NET_MANUAL:
            if self._net_came_from_method:
                self._go_to(P_NET_METHOD)
            else:
                self._go_to(P_NET_SELECT)
        elif page == P_MA_RETRY:
            self._go_to(P_MA)

    # ──────────────────────────────────────────────────────
    # SPINNER
    # ──────────────────────────────────────────────────────

    def _tick(self):
        self._spin_idx = (self._spin_idx + 1) % len(self._spin_frames)
        f = self._spin_frames[self._spin_idx]
        p = self._stack.currentIndex()
        if p == P_DETECTING:
            self._spin_lbl.setText(f)
        elif p == P_WORKING:
            self._work_spin_lbl.setText(f)

    def _set_working(self, status: str, detail: str = ""):
        self._work_status_lbl.setText(status)
        self._work_detail_lbl.setText(detail)
        self._go_to(P_WORKING)
        self._spin_timer.start(180)

    def _stop_spinner(self):
        self._spin_timer.stop()

    # ──────────────────────────────────────────────────────
    # ÉTAPE 1 — DÉTECTION RAPIDE
    # ──────────────────────────────────────────────────────

    def _start_quick_detection(self):
        self._go_to(P_DETECTING)
        self._spin_timer.start(180)
        self._q_detect = QuickDetector()
        self._q_detect.finished.connect(self._on_quick_done)
        self._q_detect.start()

    def _on_quick_done(self, found: bool):
        self._stop_spinner()
        if found:
            self._connected_ip_lbl.setText(f"Adresse IP : {TARGET_IP}")
            self._go_to(P_CONNECTED)
        else:
            self._go_to(P_CHOOSE)

    # ──────────────────────────────────────────────────────
    # MA LIGHTING — SCAN LARGE
    # ──────────────────────────────────────────────────────

    def _start_ma_search(self):
        self._set_working(
            "Recherche du boîtier MA Lighting...",
            "Scan en cours sur plusieurs adresses IP"
        )
        self._full_scan = FullScanner()
        self._full_scan.finished.connect(self._on_ma_search_done)
        self._full_scan.start()

    def _on_ma_search_done(self, found: bool, ip: str):
        self._stop_spinner()
        if found:
            self._success_sub_lbl.setText(
                f"Votre boîtier MA Lighting est prêt\nà recevoir les données DMX.\nAdresse : {ip}"
            )
            self._go_to(P_SUCCESS)
        else:
            self._go_to(P_MA_RETRY)

    # ──────────────────────────────────────────────────────
    # ÉTAPE 2 — SCAN DES CARTES RÉSEAU
    # ──────────────────────────────────────────────────────

    def _start_adapter_scan(self):
        self._set_working(
            "Scan des cartes réseau...",
            "Recherche des adaptateurs Ethernet connectés"
        )
        self._adapter_scan = AdapterScanner()
        self._adapter_scan.done.connect(self._on_adapters_scanned)
        self._adapter_scan.start()

    def _on_adapters_scanned(self, adapters: list):
        """Reçoit la liste des adaptateurs et peuple la page de sélection."""
        # Vider l'ancien contenu (sauf le stretch final)
        while self._adapters_layout.count() > 1:
            item = self._adapters_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if not adapters:
            lbl = QLabel(
                "Aucune carte Ethernet active détectée.\n\n"
                "Vérifiez que le câble RJ45 est bien branché\n"
                "puis fermez et rouvrez cet assistant."
            )
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet(_BOX_WARN)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignCenter)
            self._adapters_layout.insertWidget(0, lbl)
        else:
            for i, (name, ip) in enumerate(adapters):
                already_ok = ip.startswith("2.")
                ip_display = ip if ip else "IP non configurée"

                if already_ok:
                    txt = f"  {name}\n  {ip_display}   ✓  déjà sur le réseau 2.x.x.x"
                    style = _BTN_ADAPTER_OK
                else:
                    txt = f"  {name}\n  IP actuelle : {ip_display}"
                    style = _BTN_ADAPTER

                btn = QPushButton(txt)
                btn.setStyleSheet(style)
                btn.setFixedHeight(56)
                btn.setCursor(QCursor(Qt.PointingHandCursor))
                btn.clicked.connect(
                    lambda _, n=name, curr_ip=ip: self._on_adapter_selected(n, curr_ip)
                )
                self._adapters_layout.insertWidget(i, btn)

        self._stop_spinner()
        self._go_to(P_NET_SELECT)

    # ──────────────────────────────────────────────────────
    # ÉTAPE 3 — SÉLECTION CARTE + VÉRIFICATION IP
    # ──────────────────────────────────────────────────────

    def _on_adapter_selected(self, adapter_name: str, current_ip: str):
        """L'utilisateur a choisi une carte réseau."""
        self._adapter_name = adapter_name

        if current_ip.startswith("2."):
            # IP déjà correcte → aller directement à la recherche du node
            self._set_working(
                "IP déjà configurée correctement",
                f"Recherche du boîtier DMX sur {TARGET_IP}..."
            )
            self._start_node_search()
        else:
            # Proposer la configuration
            ip_display = current_ip if current_ip else "non configurée"
            self._net_method_adapter_lbl.setText(
                f"Carte sélectionnée :  « {adapter_name} »\n"
                f"Adresse IP actuelle :  {ip_display}"
            )
            self._net_came_from_method = False
            self._go_to(P_NET_METHOD)

    # ──────────────────────────────────────────────────────
    # ÉTAPE 4A — CONFIGURATION AUTOMATIQUE
    # ──────────────────────────────────────────────────────

    def _do_auto_config(self):
        self._set_working(
            "Configuration en cours...",
            f"Application de l'IP 2.0.0.1 sur « {self._adapter_name} »..."
        )
        self._net_setup = NetworkSetup(self._adapter_name)
        self._net_setup.done.connect(self._on_network_done)
        self._net_setup.start()

    def _on_network_done(self, status: str, adapter: str):
        self._adapter_name = adapter
        if status == "ok":
            self._start_node_search()
            return
        self._stop_spinner()
        self._net_came_from_method = True
        self._show_net_manual(adapter, status)

    # ──────────────────────────────────────────────────────
    # ÉTAPE 4B — CONFIGURATION MANUELLE
    # ──────────────────────────────────────────────────────

    def _show_manual_from_method(self):
        """Depuis P_NET_METHOD → configuration manuelle."""
        self._net_came_from_method = True
        self._show_net_manual(self._adapter_name, "manual")

    def _show_net_manual(self, adapter: str, status: str = "manual"):
        """Affiche la page de configuration manuelle."""
        adapter_label = f"« {adapter} »" if adapter else "votre carte Ethernet"

        if status == "no_adapter":
            ctx = (
                "Aucune carte Ethernet active détectée.\n"
                "Vérifiez que le câble RJ45 est bien branché et réessayez."
            )
        elif status == "manual":
            ctx = (
                f"Carte : {adapter_label}\n"
                "Droits insuffisants pour configurer l'IP automatiquement.\n"
                "Configurez manuellement ou relancez en administrateur."
            )
        else:
            ctx = f"Carte : {adapter_label}"

        self._manual_ctx_lbl.setText(ctx)
        self._manual_steps_lbl.setText(
            f"1.  Clic droit sur {adapter_label}\n"
            "2.  Propriétés\n"
            "3.  Protocole Internet version 4 (TCP/IPv4)  →  Propriétés\n"
            "4.  Utiliser l'adresse IP suivante :\n"
            "       Adresse IP :              2 . 0 . 0 . 1\n"
            "       Masque de sous-réseau :  255 . 0 . 0 . 0\n"
            "5.  OK  →  OK  →  Fermer"
        )
        self._go_to(P_NET_MANUAL)

    # ──────────────────────────────────────────────────────
    # ÉTAPE 5 — RECHERCHE DU NODE
    # ──────────────────────────────────────────────────────

    def _start_node_search(self):
        self._set_working(
            "Recherche du boîtier DMX...",
            f"Envoi ArtPoll sur {TARGET_IP}..."
        )
        self._node_srch = NodeSearcher()
        self._node_srch.finished.connect(self._on_search_done)
        self._node_srch.start()

    def _on_search_done(self, found: bool):
        self._stop_spinner()
        if found:
            self._go_to(P_SUCCESS)
        else:
            adapter_label = f"« {self._adapter_name} »" if self._adapter_name else "votre carte Ethernet"
            self._manual_ctx_lbl.setText(
                f"Le boîtier n'a pas répondu sur {TARGET_IP}.\n"
                "Vérifiez la configuration réseau et réessayez."
            )
            self._manual_steps_lbl.setText(
                f"1.  Clic droit sur {adapter_label}\n"
                "2.  Propriétés\n"
                "3.  Protocole Internet version 4 (TCP/IPv4)  →  Propriétés\n"
                "4.  Utiliser l'adresse IP suivante :\n"
                "       Adresse IP :              2 . 0 . 0 . 1\n"
                "       Masque de sous-réseau :  255 . 0 . 0 . 0\n"
                "5.  OK  →  OK  →  Fermer"
            )
            self._net_came_from_method = True
            self._go_to(P_NET_MANUAL)

    # ──────────────────────────────────────────────────────
    # RELANCE EN ADMIN
    # ──────────────────────────────────────────────────────

    def _restart_as_admin(self):
        """Relance MyStrow avec les droits administrateur (UAC)."""
        import sys
        import ctypes
        try:
            exe = sys.executable
            args = " ".join(f'"{a}"' for a in sys.argv)
            ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────
    # NETTOYAGE
    # ──────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._spin_timer.stop()
        for t in (self._q_detect, self._adapter_scan, self._net_setup,
                  self._node_srch, self._full_scan):
            if t and t.isRunning():
                t.quit()
                t.wait(300)
        super().closeEvent(event)
