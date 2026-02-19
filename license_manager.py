"""
Systeme de licence Firebase pour MyStrow.
Comptes utilisateurs (email + mdp) — 2 machines max par compte.
Zero dependance Qt — appelable depuis n'importe quel contexte.
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

# === Cryptographie (chiffrement local uniquement) ===
try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("Module cryptography non installe. pip install cryptography")


# ============================================================
# CONSTANTES
# ============================================================

ACCOUNT_FILE    = os.path.join(os.path.expanduser("~"), ".maestro_account.dat")
TRIAL_FILE      = os.path.join(os.path.expanduser("~"), ".maestro_trial.dat")
TRIAL_DAYS      = 15
OFFLINE_GRACE_DAYS = 7  # jours sans connexion avant blocage (licence payante uniquement)

# Empreinte anti-reset essai (AppData, cachee)
if platform.system() == "Windows":
    _APPDATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    _FINGERPRINT_DIR  = os.path.join(_APPDATA, "MyStrow", "cache")
    _FINGERPRINT_FILE = os.path.join(_FINGERPRINT_DIR, ".sys")
else:
    _FINGERPRINT_DIR  = os.path.join(os.path.expanduser("~"), ".config", "mystrow")
    _FINGERPRINT_FILE = os.path.join(_FINGERPRINT_DIR, ".sys")

# Flags subprocess (pas de fenetre console sur Windows)
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
    """Resultat de la verification de licence, cache pour toute la session."""

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
        message="Connectez-vous a votre compte MyStrow",
        action_label="Connexion"
    )

def _result_invalid(reason=""):
    return LicenseResult(
        state=LicenseState.INVALID,
        dmx_allowed=False,
        watermark_required=True,
        message=f"Compte invalide{': ' + reason if reason else ''}"
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
        action_label="Mon compte" if warn else "",
        license_type="trial"
    )

def _result_trial_expired():
    return LicenseResult(
        state=LicenseState.TRIAL_EXPIRED,
        dmx_allowed=False,
        watermark_required=True,
        message="Periode d'essai expiree",
        action_label="Mon compte"
    )

def _result_license_active(days):
    warn = days <= 7
    return LicenseResult(
        state=LicenseState.LICENSE_ACTIVE,
        dmx_allowed=True,
        watermark_required=False,
        show_warning=warn,
        days_remaining=days,
        message=f"Licence expire dans {days} jour{'s' if days > 1 else ''}" if warn else "",
        action_label="Renouveler" if warn else "",
        license_type="license"
    )

def _result_license_expired():
    return LicenseResult(
        state=LicenseState.LICENSE_EXPIRED,
        dmx_allowed=False,
        watermark_required=True,
        message="Licence expiree",
        action_label="Renouveler"
    )

def _result_offline(cached_plan, cached_expiry_utc, days_offline):
    """Resultat construit depuis le cache local (mode hors-ligne)."""
    now = datetime.now(timezone.utc).timestamp()
    days_remaining = max(0, int((cached_expiry_utc - now) / 86400))

    suffix = f" (hors-ligne, {days_offline}j)"
    if cached_plan == "license":
        if now >= cached_expiry_utc:
            return _result_license_expired()
        r = _result_license_active(days_remaining)
        # Ajouter note hors-ligne sans casser la logique
        object.__setattr__ if False else None
        return LicenseResult(
            state=r.state, dmx_allowed=r.dmx_allowed,
            watermark_required=r.watermark_required,
            show_warning=r.show_warning, days_remaining=r.days_remaining,
            message=(r.message or "Licence active") + suffix,
            action_label=r.action_label, license_type=r.license_type
        )
    else:  # trial
        if now >= cached_expiry_utc:
            return _result_trial_expired()
        r = _result_trial_active(max(1, days_remaining))
        return LicenseResult(
            state=r.state, dmx_allowed=r.dmx_allowed,
            watermark_required=r.watermark_required,
            show_warning=r.show_warning, days_remaining=r.days_remaining,
            message=(r.message or "Essai actif") + suffix,
            action_label=r.action_label, license_type=r.license_type
        )


# ============================================================
# IDENTIFIANT MACHINE
# ============================================================

def _run_wmic(command):
    """Execute une commande wmic (Windows uniquement)."""
    try:
        result = subprocess.run(
            command,
            capture_output=True, text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW
        )
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        if len(lines) >= 2:
            return lines[1]
        return ""
    except Exception:
        return ""


def get_machine_id() -> str:
    """
    Genere un identifiant unique de la machine base sur le hardware.
    SHA256 de CPU_ID + BIOS_SERIAL + MOBO_SERIAL + DISK_SERIAL + WINDOWS_SID.
    """
    components = []

    if platform.system() == "Windows":
        cpu = _run_wmic(["wmic", "cpu", "get", "ProcessorId"])
        components.append(f"CPU:{cpu}")

        bios = _run_wmic(["wmic", "bios", "get", "SerialNumber"])
        components.append(f"BIOS:{bios}")

        mobo = _run_wmic(["wmic", "baseboard", "get", "SerialNumber"])
        components.append(f"MOBO:{mobo}")

        disk = _run_wmic(["wmic", "diskdrive", "get", "SerialNumber"])
        components.append(f"DISK:{disk}")

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
        try:
            with open("/etc/machine-id", "r") as f:
                components.append(f"MID:{f.read().strip()}")
        except Exception:
            components.append(f"HOST:{platform.node()}")

    raw = "|".join(components)
    return hashlib.sha256(raw.encode()).hexdigest()


# ============================================================
# STOCKAGE LOCAL CHIFFRE (~/.maestro_account.dat)
# ============================================================

def _derive_fernet_key(machine_id: str) -> bytes:
    raw = hashlib.sha256(f"maestro-account-{machine_id}".encode()).digest()
    return base64.urlsafe_b64encode(raw)


def _load_account(machine_id: str) -> dict | None:
    """Charge et dechiffre le fichier de compte local."""
    if not CRYPTO_AVAILABLE:
        return None
    if not os.path.exists(ACCOUNT_FILE):
        return None
    try:
        key = _derive_fernet_key(machine_id)
        f = Fernet(key)
        with open(ACCOUNT_FILE, "rb") as fp:
            encrypted = fp.read()
        decrypted = f.decrypt(encrypted)
        return json.loads(decrypted.decode())
    except Exception as e:
        print(f"Erreur lecture compte local: {e}")
        return None


def _save_account(machine_id: str, data: dict) -> bool:
    """Chiffre et sauvegarde le fichier de compte local."""
    if not CRYPTO_AVAILABLE:
        return False
    try:
        key = _derive_fernet_key(machine_id)
        f = Fernet(key)
        raw = json.dumps(data).encode()
        encrypted = f.encrypt(raw)
        with open(ACCOUNT_FILE, "wb") as fp:
            fp.write(encrypted)
        return True
    except Exception as e:
        print(f"Erreur sauvegarde compte local: {e}")
        return False


def _delete_account():
    """Supprime le fichier de compte local (logout)."""
    try:
        if os.path.exists(ACCOUNT_FILE):
            os.remove(ACCOUNT_FILE)
        return True
    except Exception as e:
        print(f"Erreur suppression compte: {e}")
        return False


# ============================================================
# VERIFICATION INTEGRITE EXE (anti-patch, conserve)
# ============================================================

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    _VERIFY_AVAILABLE = True
except ImportError:
    _VERIFY_AVAILABLE = False

_ED25519_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA6tjDrKl10uRagKkkrIC0oh59c6LpowL/f71EqFfXTFA=
-----END PUBLIC KEY-----
"""

def _verify_signature(data_bytes: bytes, signature_hex: str) -> bool:
    if not _VERIFY_AVAILABLE:
        return False
    try:
        public_key = load_pem_public_key(_ED25519_PUBLIC_KEY_PEM)
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, data_bytes)
        return True
    except Exception:
        return False


def check_exe_integrity() -> bool:
    """
    Verifie l'integrite de l'executable (uniquement en mode frozen/PyInstaller).
    Retourne True si OK ou si on n'est pas en mode frozen.
    """
    if not getattr(sys, 'frozen', False):
        return True

    exe_path = sys.executable
    sig_path = exe_path + ".sig"

    if not os.path.exists(sig_path):
        print("Fichier .sig manquant - integrite non verifiable")
        return False

    try:
        sha256 = hashlib.sha256()
        with open(exe_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        exe_hash = sha256.hexdigest()

        with open(sig_path, "r") as f:
            sig_data = json.load(f)

        expected_hash = sig_data.get("hash", "")
        signature = sig_data.get("signature", "")

        if exe_hash != expected_hash:
            print("Hash exe ne correspond pas - fichier modifie")
            return False

        if signature and _VERIFY_AVAILABLE:
            return _verify_signature(expected_hash.encode(), signature)

        return exe_hash == expected_hash

    except Exception as e:
        print(f"Erreur verification integrite: {e}")
        return False


# ============================================================
# ESSAI LOCAL (sans compte, lie a la machine)
# ============================================================

def _derive_trial_key(machine_id: str) -> bytes:
    raw = hashlib.sha256(f"maestro-trial-{machine_id}".encode()).digest()
    return base64.urlsafe_b64encode(raw)


def _derive_fingerprint_key(machine_id: str) -> bytes:
    raw = hashlib.sha256(f"maestro-fp-{machine_id}".encode()).digest()
    return base64.urlsafe_b64encode(raw)


def _has_trial_fingerprint(machine_id: str) -> bool:
    """Verifie si un essai a deja ete utilise sur cette machine (empreinte cachee)."""
    if not CRYPTO_AVAILABLE or not os.path.exists(_FINGERPRINT_FILE):
        return False
    try:
        key = _derive_fingerprint_key(machine_id)
        f = Fernet(key)
        with open(_FINGERPRINT_FILE, "rb") as fp:
            data = json.loads(f.decrypt(fp.read()).decode())
        return data.get("machine_id") == machine_id and data.get("trial_used", False)
    except Exception:
        return False


def _save_trial_fingerprint(machine_id: str):
    """Sauvegarde l'empreinte irreversible indiquant qu'un essai a ete utilise."""
    try:
        os.makedirs(_FINGERPRINT_DIR, exist_ok=True)
        data = {
            "machine_id": machine_id,
            "trial_used": True,
            "created_utc": datetime.now(timezone.utc).timestamp(),
        }
        key = _derive_fingerprint_key(machine_id)
        encrypted = Fernet(key).encrypt(json.dumps(data).encode())
        with open(_FINGERPRINT_FILE, "wb") as fp:
            fp.write(encrypted)
        # Cacher le fichier sur Windows
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(_FINGERPRINT_FILE, 0x02)
            except Exception:
                pass
    except Exception as e:
        print(f"Erreur empreinte: {e}")


def _load_trial_data(machine_id: str) -> dict | None:
    """Charge le fichier d'essai local."""
    if not CRYPTO_AVAILABLE or not os.path.exists(TRIAL_FILE):
        return None
    try:
        key = _derive_trial_key(machine_id)
        f = Fernet(key)
        with open(TRIAL_FILE, "rb") as fp:
            data = json.loads(f.decrypt(fp.read()).decode())
        # Verifier que le machine_id correspond (protection copie de fichier)
        if data.get("machine_id") != machine_id:
            return None
        return data
    except Exception:
        return None


def _activate_local_trial(machine_id: str) -> bool:
    """Active l'essai local automatiquement (premier lancement)."""
    if not CRYPTO_AVAILABLE:
        return False
    try:
        now = datetime.now(timezone.utc).timestamp()
        data = {
            "machine_id": machine_id,
            "created_utc": now,
            "expiry_utc": now + (TRIAL_DAYS * 86400),
        }
        key = _derive_trial_key(machine_id)
        encrypted = Fernet(key).encrypt(json.dumps(data).encode())
        with open(TRIAL_FILE, "wb") as fp:
            fp.write(encrypted)
        _save_trial_fingerprint(machine_id)
        print(f"Essai local active ({TRIAL_DAYS} jours)")
        return True
    except Exception as e:
        print(f"Erreur activation essai: {e}")
        return False


def _verify_local_trial(machine_id: str) -> LicenseResult:
    """Verifie l'etat de l'essai local."""
    trial = _load_trial_data(machine_id)
    if trial is None:
        return _result_not_activated()
    now = datetime.now(timezone.utc).timestamp()
    expiry = trial.get("expiry_utc", 0)
    if now >= expiry:
        return _result_trial_expired()
    days = max(1, int((expiry - now) / 86400))
    return _result_trial_active(days)


# ============================================================
# VERIFICATION PRINCIPALE (appelee UNE FOIS au demarrage)
# ============================================================

def verify_license() -> LicenseResult:
    """
    Verifie l'etat de la licence. Appelee une seule fois au demarrage.

    Flux :
    1. Compte Firebase present → verification en ligne (priorite)
    2. Fichier essai local present → verifier l'essai
    3. Ni l'un ni l'autre + pas d'empreinte → activer l'essai automatiquement
    4. Empreinte presente + pas de compte → essai deja utilise → NOT_ACTIVATED
    """
    try:
        machine_id = get_machine_id()
    except Exception as e:
        print(f"Erreur machine ID: {e}")
        return _result_not_activated()

    # --- Etape 1 : Compte Firebase ---
    account = _load_account(machine_id)
    if account is not None:
        return _verify_firebase_account(machine_id, account)

    # --- Etape 2 : Essai local existant ---
    if _load_trial_data(machine_id) is not None:
        return _verify_local_trial(machine_id)

    # --- Etape 3 : Premier lancement → activer l'essai automatiquement ---
    if not _has_trial_fingerprint(machine_id):
        if _activate_local_trial(machine_id):
            return _verify_local_trial(machine_id)

    # --- Etape 4 : Essai deja utilise, pas de compte → connexion requise ---
    return _result_not_activated()


def _verify_firebase_account(machine_id: str, account: dict) -> LicenseResult:
    """Verification en ligne via Firebase (appel Firestore)."""
    try:
        import firebase_client as fc

        token_data = fc.refresh_id_token(account["refresh_token"])
        uid = token_data["uid"]
        id_token = token_data["id_token"]

        if token_data.get("refresh_token"):
            account["refresh_token"] = token_data["refresh_token"]

        doc = fc.get_license_doc(uid, id_token)
        if doc is None:
            return _result_not_activated()

        fc.add_machine(uid, id_token, machine_id, label=platform.node()[:32])

        now = datetime.now(timezone.utc).timestamp()
        account["last_verified_utc"] = now
        account["uid"] = uid
        account["cached_plan"] = doc.get("plan", "trial")
        account["cached_expiry_utc"] = doc.get("expiry_utc", now)
        _save_account(machine_id, account)

        return _build_result(doc.get("plan", "trial"), doc.get("expiry_utc", now))

    except Exception as e:
        err_msg = str(e)
        print(f"Firebase injoignable ou erreur : {err_msg}")

        if "2 appareils" in err_msg or "désactivé" in err_msg or "Session expirée" in err_msg:
            return _result_invalid(err_msg)

        return _offline_fallback(account)


def _build_result(plan: str, expiry_utc: float) -> LicenseResult:
    """Construit un LicenseResult depuis les donnees Firestore."""
    now = datetime.now(timezone.utc).timestamp()
    days_remaining = max(0, int((expiry_utc - now) / 86400))

    if plan == "license":
        if now >= expiry_utc:
            return _result_license_expired()
        return _result_license_active(max(1, days_remaining))
    else:  # trial
        if now >= expiry_utc:
            return _result_trial_expired()
        return _result_trial_active(max(1, days_remaining))


def _offline_fallback(account: dict) -> LicenseResult:
    """Retourne un resultat depuis le cache si < 7 jours offline.
    Les comptes en trial doivent etre en ligne — pas de grace offline."""
    cached_plan = account.get("cached_plan", "trial")

    # Essai = connexion obligatoire (pas de fallback offline)
    if cached_plan == "trial":
        print("Trial : connexion Firebase requise")
        return _result_not_activated()

    last_verified = account.get("last_verified_utc", 0)
    now = datetime.now(timezone.utc).timestamp()
    days_offline = int((now - last_verified) / 86400)

    if days_offline > OFFLINE_GRACE_DAYS:
        print(f"Hors-ligne depuis {days_offline} jours > grace {OFFLINE_GRACE_DAYS}j")
        return _result_not_activated()

    cached_expiry = account.get("cached_expiry_utc", 0)
    print(f"Mode hors-ligne ({days_offline}j) — licence")
    return _result_offline(cached_plan, cached_expiry, days_offline)


# ============================================================
# ACTIONS COMPTE (login, register, logout)
# ============================================================

def login_account(email: str, password: str) -> tuple[bool, str]:
    """
    Connecte un compte Firebase et enregistre le token localement.
    Retourne (success: bool, message: str).
    """
    try:
        machine_id = get_machine_id()
    except Exception as e:
        return False, f"Erreur identification machine: {e}"

    try:
        import firebase_client as fc

        auth = fc.sign_in(email.strip(), password)
        uid = auth["uid"]
        id_token = auth["id_token"]
        refresh_token = auth["refresh_token"]

        # Verifier que le document de licence existe
        doc = fc.get_license_doc(uid, id_token)
        if doc is None:
            return False, "Aucun compte licence associe a cet email."

        # Ajouter la machine
        fc.add_machine(uid, id_token, machine_id, label=platform.node()[:32])

        # Sauvegarder le compte local
        now = datetime.now(timezone.utc).timestamp()
        account_data = {
            "refresh_token": refresh_token,
            "uid": uid,
            "email": auth.get("email", email),
            "last_verified_utc": now,
            "cached_plan": doc.get("plan", "trial"),
            "cached_expiry_utc": doc.get("expiry_utc", now),
        }
        _save_account(machine_id, account_data)

        plan = doc.get("plan", "trial")
        plan_label = "licence" if plan == "license" else "essai"
        return True, f"Connecte — {auth.get('email', email)} ({plan_label})"

    except Exception as e:
        return False, str(e)


def register_account(email: str, password: str) -> tuple[bool, str]:
    """
    Cree un compte Firebase et le document Firestore.
    Retourne (success: bool, message: str).
    """
    try:
        machine_id = get_machine_id()
    except Exception as e:
        return False, f"Erreur identification machine: {e}"

    try:
        import firebase_client as fc

        # Creer le compte Firebase Auth
        auth = fc.sign_up(email.strip(), password)
        uid = auth["uid"]
        id_token = auth["id_token"]
        refresh_token = auth["refresh_token"]

        # Creer le document Firestore avec plan trial
        fc.create_license_doc(uid, id_token, auth.get("email", email))

        # Ajouter la machine
        fc.add_machine(uid, id_token, machine_id, label=platform.node()[:32])

        # Sauvegarder le compte local
        now = datetime.now(timezone.utc).timestamp()
        account_data = {
            "refresh_token": refresh_token,
            "uid": uid,
            "email": auth.get("email", email),
            "last_verified_utc": now,
            "cached_plan": "trial",
            "cached_expiry_utc": now + (15 * 86400),
        }
        _save_account(machine_id, account_data)

        return True, f"Compte cree — essai gratuit 15 jours active !"

    except Exception as e:
        return False, str(e)


def deactivate_machine() -> tuple[bool, str]:
    """
    Deconnecte cette machine : retire machine_id de Firestore et supprime le compte local.
    Retourne (success: bool, message: str).
    """
    try:
        machine_id = get_machine_id()
    except Exception as e:
        return False, f"Erreur identification machine: {e}"

    account = _load_account(machine_id)
    if account is None:
        _delete_account()
        return True, "Deconnecte."

    try:
        import firebase_client as fc

        uid = account.get("uid", "")
        refresh_token = account.get("refresh_token", "")

        if uid and refresh_token:
            try:
                token_data = fc.refresh_id_token(refresh_token)
                fc.remove_machine(uid, token_data["id_token"], machine_id)
            except Exception as e:
                print(f"Impossible de retirer la machine de Firestore: {e}")
                # Continuer quand meme pour le logout local

    except ImportError:
        pass

    _delete_account()
    return True, "Machine deconnectee avec succes."


# ============================================================
# UTILITAIRES DEBUG
# ============================================================

def get_license_info() -> dict:
    """Retourne les infos du compte actuel (pour affichage debug)."""
    try:
        machine_id = get_machine_id()
        account = _load_account(machine_id)
        info = {"machine_id": machine_id[:16] + "..."}
        if account:
            info.update({
                "email": account.get("email", "?"),
                "uid": account.get("uid", "?")[:8] + "...",
                "plan": account.get("cached_plan", "?"),
                "expiry": datetime.fromtimestamp(
                    account.get("cached_expiry_utc", 0), tz=timezone.utc
                ).strftime("%Y-%m-%d UTC"),
                "last_verified": datetime.fromtimestamp(
                    account.get("last_verified_utc", 0), tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC"),
            })
        else:
            info["status"] = "non_connecte"
        return info
    except Exception as e:
        return {"error": str(e)}
