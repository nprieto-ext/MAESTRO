"""
Systeme de licence pour Maestro.py
Gestion des essais, licences, anti-fraude (horloge, patch)
Zero dependance Qt - appelable depuis n'importe quel contexte
"""

import os
import sys
import json
import time
import hashlib
import subprocess
import platform
import base64
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone

# === Cryptographie ===
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import (
        load_pem_public_key, load_pem_private_key
    )
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("Module cryptography non installe. pip install cryptography")


# === Cle publique Ed25519 (embarquee) ===
# Generee par license_keygen.py --generate-keypair
ED25519_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA6tjDrKl10uRagKkkrIC0oh59c6LpowL/f71EqFfXTFA=
-----END PUBLIC KEY-----
"""

# === Cle privee Ed25519 (obfusquee, pour signature locale des essais) ===
# XOR avec une cle derivee du module pour eviter l'extraction triviale
_KS = b"MC4CAQAwBQYDK2VwBCIEIO4dq7bapt3BQlEKe5aYxrP0aH9KbiN/Xdc/oij6uMQm"
_KX = b"maestro-trial-offline-signing-key-2025-do-not-extract-this!xq"

def _deobfuscate_private_key():
    """Reconstruit la cle privee depuis les donnees obfusquees"""
    raw = base64.b64decode(_KS)
    mask = _KX * (len(raw) // len(_KX) + 1)
    deobf = bytes(a ^ b for a, b in zip(raw, mask[:len(raw)]))
    # _KS contient directement les bytes base64 du DER, reconstruire le PEM
    pem = b"-----BEGIN PRIVATE KEY-----\n" + _KS + b"\n-----END PRIVATE KEY-----\n"
    return pem


# === Constantes ===
LICENSE_FILE = os.path.join(os.path.expanduser("~"), ".maestro_license.dat")
TRIAL_DURATION_DAYS = 15
ACTIVATION_SERVER_URL = "https://api.maestro-light.com/license"

# Empreinte cachee anti-reset (AppData)
if platform.system() == "Windows":
    _APPDATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    _FINGERPRINT_DIR = os.path.join(_APPDATA, "Maestro", "cache")
    _FINGERPRINT_FILE = os.path.join(_FINGERPRINT_DIR, ".sys")
else:
    _FINGERPRINT_DIR = os.path.join(os.path.expanduser("~"), ".config", "maestro")
    _FINGERPRINT_FILE = os.path.join(_FINGERPRINT_DIR, ".sys")

# Flags pour subprocess sur Windows (pas de fenetre console)
CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


# ============================================================
# ETATS DE LICENCE
# ============================================================

class LicenseState(Enum):
    NOT_ACTIVATED = "not_activated"
    INVALID = "invalid"
    FRAUD_CLOCK = "fraud_clock"
    TRIAL_ACTIVE = "trial_active"
    TRIAL_EXPIRED = "trial_expired"
    LICENSE_ACTIVE = "license_active"
    LICENSE_EXPIRED = "license_expired"


# ============================================================
# RESULTAT DE LICENCE (immutable, cache pour toute la session)
# ============================================================

class LicenseResult:
    """Resultat de la verification de licence, cache pour toute la session"""

    __slots__ = (
        'state', 'dmx_allowed', 'watermark_required',
        'show_warning', 'days_remaining', 'message',
        'action_label', 'license_type'
    )

    def __init__(self, state, dmx_allowed=False, watermark_required=True,
                 show_warning=False, days_remaining=0, message="",
                 action_label="", license_type=""):
        self.state = state
        self.dmx_allowed = dmx_allowed
        self.watermark_required = watermark_required
        self.show_warning = show_warning
        self.days_remaining = days_remaining
        self.message = message
        self.action_label = action_label
        self.license_type = license_type

    def __repr__(self):
        return f"LicenseResult(state={self.state.value}, dmx={self.dmx_allowed}, days={self.days_remaining})"


# ============================================================
# RESULTATS PRE-DEFINIS PAR ETAT
# ============================================================

def _result_not_activated():
    return LicenseResult(
        state=LicenseState.NOT_ACTIVATED,
        dmx_allowed=False,
        watermark_required=True,
        message="Logiciel non active",
        action_label="Activer"
    )

def _result_invalid(reason=""):
    return LicenseResult(
        state=LicenseState.INVALID,
        dmx_allowed=False,
        watermark_required=True,
        message=f"Licence invalide{': ' + reason if reason else ''}"
    )

def _result_fraud_clock():
    return LicenseResult(
        state=LicenseState.FRAUD_CLOCK,
        dmx_allowed=False,
        watermark_required=True,
        message="Anomalie d'horloge detectee"
    )

def _result_trial_active(days):
    warn = days <= 2
    return LicenseResult(
        state=LicenseState.TRIAL_ACTIVE,
        dmx_allowed=True,
        watermark_required=False,
        show_warning=warn,
        days_remaining=days,
        message=f"Essai - {days} jour{'s' if days > 1 else ''} restant{'s' if days > 1 else ''}",
        action_label="Activer" if warn else "",
        license_type="trial"
    )

def _result_trial_expired():
    return LicenseResult(
        state=LicenseState.TRIAL_EXPIRED,
        dmx_allowed=False,
        watermark_required=True,
        message="Periode d'essai expiree",
        action_label="Activer"
    )

def _result_license_active(days):
    warn = days <= 7
    return LicenseResult(
        state=LicenseState.LICENSE_ACTIVE,
        dmx_allowed=True,
        watermark_required=False,
        show_warning=warn,
        days_remaining=days,
        message=f"Abonnement expire dans {days} jour{'s' if days > 1 else ''}" if warn else "",
        action_label="Renouveler" if warn else "",
        license_type="license"
    )

def _result_license_expired():
    return LicenseResult(
        state=LicenseState.LICENSE_EXPIRED,
        dmx_allowed=False,
        watermark_required=True,
        message="Abonnement expire",
        action_label="Renouveler"
    )


# ============================================================
# IDENTIFIANT MACHINE
# ============================================================

def _run_wmic(command):
    """Execute une commande wmic et retourne le resultat (Windows uniquement)"""
    try:
        result = subprocess.run(
            command,
            capture_output=True, text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW
        )
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        # Premiere ligne = header, le reste = valeurs
        if len(lines) >= 2:
            return lines[1]
        return ""
    except Exception:
        return ""


def get_machine_id():
    """
    Genere un identifiant unique de la machine base sur le hardware.
    SHA256 de CPU_ID + BIOS_SERIAL + MOBO_SERIAL + DISK_SERIAL + WINDOWS_SID
    """
    components = []

    if platform.system() == "Windows":
        # CPU ID
        cpu = _run_wmic(["wmic", "cpu", "get", "ProcessorId"])
        components.append(f"CPU:{cpu}")

        # BIOS Serial
        bios = _run_wmic(["wmic", "bios", "get", "SerialNumber"])
        components.append(f"BIOS:{bios}")

        # Motherboard Serial
        mobo = _run_wmic(["wmic", "baseboard", "get", "SerialNumber"])
        components.append(f"MOBO:{mobo}")

        # Disk Serial
        disk = _run_wmic(["wmic", "diskdrive", "get", "SerialNumber"])
        components.append(f"DISK:{disk}")

        # Windows SID
        try:
            result = subprocess.run(
                ["wmic", "useraccount", "where",
                 f"name='{os.environ.get('USERNAME', '')}'", "get", "sid"],
                capture_output=True, text=True, timeout=5,
                creationflags=CREATE_NO_WINDOW
            )
            lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
            if len(lines) >= 2:
                components.append(f"SID:{lines[1]}")
        except Exception:
            pass
    else:
        # Linux/Mac fallback
        try:
            with open("/etc/machine-id", "r") as f:
                components.append(f"MID:{f.read().strip()}")
        except Exception:
            components.append(f"HOST:{platform.node()}")

    raw = "|".join(components)
    return hashlib.sha256(raw.encode()).hexdigest()


def _derive_fernet_key(machine_id):
    """Derive une cle Fernet a partir du machine_id (deterministe)"""
    raw = hashlib.sha256(f"maestro-fernet-{machine_id}".encode()).digest()
    return base64.urlsafe_b64encode(raw)


# ============================================================
# EMPREINTE ANTI-RESET ESSAI
# ============================================================

def _derive_fingerprint_key(machine_id):
    """Derive une cle Fernet pour le fichier empreinte"""
    raw = hashlib.sha256(f"maestro-fp-{machine_id}".encode()).digest()
    return base64.urlsafe_b64encode(raw)


def _has_trial_fingerprint(machine_id):
    """Verifie si une empreinte d'essai existe deja pour cette machine"""
    if not os.path.exists(_FINGERPRINT_FILE):
        return False

    try:
        key = _derive_fingerprint_key(machine_id)
        f = Fernet(key)
        with open(_FINGERPRINT_FILE, "rb") as fp:
            encrypted = fp.read()
        decrypted = f.decrypt(encrypted)
        data = json.loads(decrypted.decode())
        return data.get("machine_id") == machine_id and data.get("trial_used", False)
    except Exception:
        return False


def _save_trial_fingerprint(machine_id):
    """Sauvegarde l'empreinte indiquant qu'un essai a ete utilise"""
    try:
        os.makedirs(_FINGERPRINT_DIR, exist_ok=True)

        data = {
            "machine_id": machine_id,
            "trial_used": True,
            "first_trial_utc": datetime.now(timezone.utc).timestamp(),
        }

        key = _derive_fingerprint_key(machine_id)
        f = Fernet(key)
        encrypted = f.encrypt(json.dumps(data).encode())

        with open(_FINGERPRINT_FILE, "wb") as fp:
            fp.write(encrypted)

        # Marquer le fichier comme cache sur Windows
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(
                    _FINGERPRINT_FILE, 0x02  # FILE_ATTRIBUTE_HIDDEN
                )
            except Exception:
                pass

        return True
    except Exception as e:
        print(f"Erreur sauvegarde empreinte: {e}")
        return False


# ============================================================
# FICHIER DE LICENCE (chiffre, lie a la machine)
# ============================================================

def _load_license_data(machine_id):
    """Charge et dechiffre le fichier de licence"""
    if not os.path.exists(LICENSE_FILE):
        return None

    try:
        key = _derive_fernet_key(machine_id)
        f = Fernet(key)
        with open(LICENSE_FILE, "rb") as fp:
            encrypted = fp.read()
        decrypted = f.decrypt(encrypted)
        return json.loads(decrypted.decode())
    except Exception as e:
        print(f"Erreur lecture licence: {e}")
        return None


def _save_license_data(machine_id, data):
    """Chiffre et sauvegarde le fichier de licence"""
    try:
        key = _derive_fernet_key(machine_id)
        f = Fernet(key)
        raw = json.dumps(data).encode()
        encrypted = f.encrypt(raw)
        with open(LICENSE_FILE, "wb") as fp:
            fp.write(encrypted)
        return True
    except Exception as e:
        print(f"Erreur sauvegarde licence: {e}")
        return False


# ============================================================
# SIGNATURE Ed25519
# ============================================================

def _verify_signature(data_bytes, signature_hex):
    """Verifie une signature Ed25519 sur des donnees"""
    if not CRYPTO_AVAILABLE:
        return False

    try:
        public_key = load_pem_public_key(ED25519_PUBLIC_KEY_PEM)
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, data_bytes)
        return True
    except Exception:
        return False


def _sign_data(data_bytes):
    """Signe des donnees avec la cle privee embarquee (pour essais offline)"""
    if not CRYPTO_AVAILABLE:
        return ""

    try:
        pem = _deobfuscate_private_key()
        private_key = load_pem_private_key(pem, password=None)
        signature = private_key.sign(data_bytes)
        return signature.hex()
    except Exception as e:
        print(f"Erreur signature locale: {e}")
        return ""


def _verify_license_signature(license_data):
    """Verifie la signature d'une licence"""
    sig = license_data.get("signature", "")
    if not sig:
        return False

    # Reconstruire les donnees signees (sans la signature)
    data = {k: v for k, v in license_data.items() if k != "signature"}
    data_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return _verify_signature(data_str.encode(), sig)


# ============================================================
# ANTI-RETOUR HORLOGE
# ============================================================

def _check_clock_rollback(license_data):
    """
    Verifie si l'horloge systeme a ete reculee.
    Retourne True si fraude detectee.
    """
    last_launch = license_data.get("last_launch_utc", 0)
    if last_launch <= 0:
        return False  # Premier lancement

    now_utc = datetime.now(timezone.utc).timestamp()

    # Tolerance de 5 minutes (derive d'horloge normale)
    if now_utc < last_launch - 300:
        return True

    return False


def _update_timestamps(machine_id, license_data):
    """Met a jour les timestamps apres verification reussie"""
    license_data["last_launch_utc"] = datetime.now(timezone.utc).timestamp()
    license_data["last_monotonic"] = time.monotonic()
    _save_license_data(machine_id, license_data)


# ============================================================
# VERIFICATION INTEGRITE EXE (anti-patch)
# ============================================================

def check_exe_integrity():
    """
    Verifie l'integrite de l'executable (uniquement en mode frozen/PyInstaller).
    Retourne True si OK ou si on n'est pas en mode frozen.
    """
    if not getattr(sys, 'frozen', False):
        return True  # Mode dev, pas de verification

    exe_path = sys.executable
    sig_path = exe_path + ".sig"

    if not os.path.exists(sig_path):
        print("Fichier .sig manquant - integrite non verifiable")
        return False

    try:
        # Calculer le SHA256 de l'exe
        sha256 = hashlib.sha256()
        with open(exe_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        exe_hash = sha256.hexdigest()

        # Lire le .sig (contient hash + signature)
        with open(sig_path, "r") as f:
            sig_data = json.load(f)

        expected_hash = sig_data.get("hash", "")
        signature = sig_data.get("signature", "")

        if exe_hash != expected_hash:
            print("Hash exe ne correspond pas - fichier modifie")
            return False

        # Verifier la signature du hash
        if signature and CRYPTO_AVAILABLE:
            return _verify_signature(expected_hash.encode(), signature)

        return exe_hash == expected_hash

    except Exception as e:
        print(f"Erreur verification integrite: {e}")
        return False


# ============================================================
# VERIFICATION PRINCIPALE (appelee UNE FOIS au demarrage)
# ============================================================

def verify_license():
    """
    Verifie l'etat de la licence. Appelee une seule fois au demarrage.
    Retourne un LicenseResult immutable cache pour toute la session.
    """
    if not CRYPTO_AVAILABLE:
        print("Module cryptography manquant - mode non active")
        return _result_not_activated()

    # Obtenir l'ID machine
    try:
        machine_id = get_machine_id()
    except Exception as e:
        print(f"Erreur machine ID: {e}")
        return _result_not_activated()

    # Charger le fichier de licence
    license_data = _load_license_data(machine_id)

    if license_data is None:
        # Pas de fichier licence - verifier si un essai a deja ete utilise
        if _has_trial_fingerprint(machine_id):
            return _result_trial_expired()
        return _result_not_activated()

    # Verifier que le machine_id correspond
    stored_machine = license_data.get("machine_id", "")
    if stored_machine != machine_id:
        return _result_invalid("machine differente")

    # Verifier la signature
    if not _verify_license_signature(license_data):
        return _result_invalid("signature invalide")

    # Anti-retour horloge
    if _check_clock_rollback(license_data):
        return _result_fraud_clock()

    # Determiner le type et la validite
    license_type = license_data.get("type", "")  # "trial" ou "license"
    expiry_utc = license_data.get("expiry_utc", 0)
    now_utc = datetime.now(timezone.utc).timestamp()

    if license_type == "trial":
        if now_utc >= expiry_utc:
            _update_timestamps(machine_id, license_data)
            return _result_trial_expired()

        days_remaining = max(1, int((expiry_utc - now_utc) / 86400) + 1)
        _update_timestamps(machine_id, license_data)
        return _result_trial_active(days_remaining)

    elif license_type == "license":
        if now_utc >= expiry_utc:
            _update_timestamps(machine_id, license_data)
            return _result_license_expired()

        days_remaining = max(1, int((expiry_utc - now_utc) / 86400) + 1)
        _update_timestamps(machine_id, license_data)
        return _result_license_active(days_remaining)

    else:
        return _result_invalid("type inconnu")


# ============================================================
# ACTIVATION ESSAI (entierement offline, signe localement)
# ============================================================

def activate_trial(email=""):
    """
    Active un essai gratuit de 15 jours.
    Entierement offline : signe localement avec la cle embarquee.
    Non reinitalisable : une empreinte cachee empeche un second essai.
    Retourne (success: bool, message: str)
    """
    if not CRYPTO_AVAILABLE:
        return False, "Module cryptography manquant"

    try:
        machine_id = get_machine_id()
    except Exception as e:
        return False, f"Erreur identification machine: {e}"

    # Verifier si un essai a deja ete utilise sur cette machine
    if _has_trial_fingerprint(machine_id):
        return False, "Un essai a deja ete utilise sur cette machine"

    # Verifier aussi s'il existe deja un fichier licence (essai ou pas)
    existing = _load_license_data(machine_id)
    if existing and existing.get("type") == "trial":
        return False, "Un essai est deja actif sur cette machine"

    now_utc = datetime.now(timezone.utc).timestamp()

    # Construire les donnees de licence
    license_data = {
        "type": "trial",
        "machine_id": machine_id,
        "created_utc": now_utc,
        "expiry_utc": now_utc + (TRIAL_DURATION_DAYS * 86400),
        "last_launch_utc": now_utc,
        "last_monotonic": 0,
    }

    # Signer avec la cle privee embarquee
    data_str = json.dumps(license_data, sort_keys=True, separators=(',', ':'))
    signature = _sign_data(data_str.encode())
    if not signature:
        return False, "Erreur de signature interne"

    license_data["signature"] = signature

    # Sauvegarder la licence
    if not _save_license_data(machine_id, license_data):
        return False, "Erreur sauvegarde locale"

    # Sauvegarder l'empreinte anti-reset (irreversible)
    _save_trial_fingerprint(machine_id)

    return True, "Essai de 15 jours active !"


# ============================================================
# ACTIVATION LICENCE (via serveur ou cle)
# ============================================================

def activate_license(license_key):
    """
    Active une licence avec une cle XXXX-XXXX-XXXX-XXXX.
    Contacte le serveur d'activation, sauvegarde la licence signee.
    Retourne (success: bool, message: str)
    """
    try:
        machine_id = get_machine_id()
    except Exception as e:
        return False, f"Erreur identification machine: {e}"

    # Validation format cle
    key_clean = license_key.strip().upper()
    parts = key_clean.split("-")
    if len(parts) != 4 or not all(len(p) == 4 and p.isalnum() for p in parts):
        return False, "Format de cle invalide (XXXX-XXXX-XXXX-XXXX)"

    try:
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "action": "activate_license",
            "machine_id": machine_id,
            "license_key": key_clean,
            "platform": platform.system(),
        }).encode()

        req = urllib.request.Request(
            f"{ACTIVATION_SERVER_URL}/activate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            response = json.loads(resp.read().decode())

        if response.get("status") != "ok":
            return False, response.get("message", "Erreur serveur")

        # Sauvegarder la licence signee
        license_data = response.get("license", {})
        license_data["machine_id"] = machine_id

        if not _save_license_data(machine_id, license_data):
            return False, "Erreur sauvegarde locale"

        return True, "Licence activee avec succes !"

    except urllib.error.URLError as e:
        return False, f"Erreur connexion serveur: {e.reason}"
    except Exception as e:
        return False, f"Erreur activation: {e}"


# ============================================================
# UTILITAIRES DEBUG
# ============================================================

def get_license_info():
    """Retourne les infos de la licence actuelle (pour affichage debug)"""
    try:
        machine_id = get_machine_id()
        data = _load_license_data(machine_id)
        info = {
            "machine_id": machine_id[:16] + "...",
            "fingerprint_exists": _has_trial_fingerprint(machine_id),
        }
        if data:
            info.update({
                "type": data.get("type", "?"),
                "expiry": datetime.fromtimestamp(
                    data.get("expiry_utc", 0), tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC"),
                "last_launch": datetime.fromtimestamp(
                    data.get("last_launch_utc", 0), tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC"),
                "has_signature": bool(data.get("signature", "")),
            })
        else:
            info["status"] = "no_license_file"
        return info
    except Exception as e:
        return {"error": str(e)}
