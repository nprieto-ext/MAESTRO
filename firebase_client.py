"""
Client Firebase HTTP pour MyStrow.
Wrapper urllib uniquement (pas de SDK Firebase).
Couvre : Auth (email/password) + Firestore REST API.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Importé depuis core pour éviter la circularité
from core import FIREBASE_API_KEY, FIREBASE_PROJECT_ID

# ---------------------------------------------------------------
# URLs de base
# ---------------------------------------------------------------
_AUTH_BASE = "https://identitytoolkit.googleapis.com/v1"
_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
_FS_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
    f"/databases/(default)/documents"
)

_TIMEOUT = 10  # secondes


# ---------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------

def _post_json(url, payload: dict, id_token: str = None) -> dict:
    """POST JSON vers une URL, retourne le dict réponse ou lève une exception."""
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _get_json(url, id_token: str) -> dict:
    """GET JSON avec Bearer token."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {id_token}"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _patch_json(url, payload: dict, id_token: str) -> dict:
    """PATCH JSON (Firestore update partiel)."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}",
        },
        method="PATCH"
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _firebase_error(e: urllib.error.HTTPError) -> str:
    """Extrait le message d'erreur Firebase d'une HTTPError."""
    try:
        body = json.loads(e.read().decode())
        return body.get("error", {}).get("message", str(e))
    except Exception:
        return str(e)


# ---------------------------------------------------------------
# Conversion Firestore ↔ Python
# ---------------------------------------------------------------

def _to_firestore(value) -> dict:
    """Convertit une valeur Python en champ Firestore."""
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_to_firestore(v) for v in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {k: _to_firestore(v) for k, v in value.items()}}}
    return {"nullValue": None}


def _from_firestore(field: dict):
    """Convertit un champ Firestore en valeur Python."""
    if "stringValue" in field:
        return field["stringValue"]
    if "integerValue" in field:
        return int(field["integerValue"])
    if "doubleValue" in field:
        return float(field["doubleValue"])
    if "booleanValue" in field:
        return field["booleanValue"]
    if "nullValue" in field:
        return None
    if "arrayValue" in field:
        return [_from_firestore(v) for v in field["arrayValue"].get("values", [])]
    if "mapValue" in field:
        return {k: _from_firestore(v) for k, v in field["mapValue"].get("fields", {}).items()}
    return None


def _doc_to_dict(doc: dict) -> dict:
    """Convertit un document Firestore complet en dict Python."""
    fields = doc.get("fields", {})
    return {k: _from_firestore(v) for k, v in fields.items()}


def _dict_to_fields(d: dict) -> dict:
    """Convertit un dict Python en champ 'fields' Firestore."""
    return {k: _to_firestore(v) for k, v in d.items()}


# ---------------------------------------------------------------
# Auth Firebase
# ---------------------------------------------------------------

def sign_up(email: str, password: str) -> dict:
    """
    Crée un compte Firebase avec email + mot de passe.
    Retourne {"uid": ..., "id_token": ..., "refresh_token": ...}
    ou lève une Exception avec un message lisible.
    """
    url = f"{_AUTH_BASE}/accounts:signUp?key={FIREBASE_API_KEY}"
    try:
        resp = _post_json(url, {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        })
        return {
            "uid": resp["localId"],
            "id_token": resp["idToken"],
            "refresh_token": resp["refreshToken"],
            "email": resp.get("email", email),
        }
    except urllib.error.HTTPError as e:
        msg = _firebase_error(e)
        if "EMAIL_EXISTS" in msg:
            raise Exception("Un compte existe déjà avec cet email.")
        if "WEAK_PASSWORD" in msg:
            raise Exception("Mot de passe trop faible (6 caractères minimum).")
        if "INVALID_EMAIL" in msg:
            raise Exception("Adresse email invalide.")
        raise Exception(f"Erreur création compte : {msg}")


def sign_in(email: str, password: str) -> dict:
    """
    Connecte un compte Firebase.
    Retourne {"uid": ..., "id_token": ..., "refresh_token": ...}
    """
    url = f"{_AUTH_BASE}/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    try:
        resp = _post_json(url, {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        })
        return {
            "uid": resp["localId"],
            "id_token": resp["idToken"],
            "refresh_token": resp["refreshToken"],
            "email": resp.get("email", email),
        }
    except urllib.error.HTTPError as e:
        msg = _firebase_error(e)
        if "EMAIL_NOT_FOUND" in msg or "INVALID_LOGIN_CREDENTIALS" in msg:
            raise Exception("Email ou mot de passe incorrect.")
        if "INVALID_PASSWORD" in msg:
            raise Exception("Mot de passe incorrect.")
        if "USER_DISABLED" in msg:
            raise Exception("Ce compte a été désactivé.")
        raise Exception(f"Erreur connexion : {msg}")


def refresh_id_token(refresh_token: str) -> dict:
    """
    Renouvelle l'ID token depuis un refresh token.
    Retourne {"uid": ..., "id_token": ...}
    """
    url = f"{_TOKEN_URL}?key={FIREBASE_API_KEY}"
    try:
        resp = _post_json(url, {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })
        return {
            "uid": resp["user_id"],
            "id_token": resp["id_token"],
            "refresh_token": resp.get("refresh_token", refresh_token),
        }
    except urllib.error.HTTPError as e:
        msg = _firebase_error(e)
        if "TOKEN_EXPIRED" in msg or "INVALID_REFRESH_TOKEN" in msg:
            raise Exception("Session expirée. Reconnectez-vous.")
        raise Exception(f"Erreur renouvellement token : {msg}")


def send_password_reset(email: str) -> bool:
    """
    Envoie un email de reinitialisation de mot de passe via Firebase.
    Firebase gere l'envoi — aucune config SMTP requise.
    """
    url = f"{_AUTH_BASE}/accounts:sendOobCode?key={FIREBASE_API_KEY}"
    try:
        _post_json(url, {
            "requestType": "PASSWORD_RESET",
            "email": email,
        })
        return True
    except urllib.error.HTTPError as e:
        raise Exception(f"Erreur envoi email : {_firebase_error(e)}")


# ---------------------------------------------------------------
# Firestore : document licence
# ---------------------------------------------------------------

def get_license_doc(uid: str, id_token: str) -> dict | None:
    """
    Lit le document /licenses/{uid} depuis Firestore.
    Retourne le dict Python du document, ou None si absent.
    """
    url = f"{_FS_BASE}/licenses/{uid}"
    try:
        doc = _get_json(url, id_token)
        return _doc_to_dict(doc)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Exception(f"Erreur lecture Firestore : {_firebase_error(e)}")


def create_license_doc(uid: str, id_token: str, email: str) -> bool:
    """
    Crée le document /licenses/{uid} avec plan 'trial'.
    Appelé lors de la création de compte (register_account).
    Retourne True si succès.
    """
    now = datetime.now(timezone.utc).timestamp()
    doc_data = {
        "email": email,
        "plan": "trial",
        "expiry_utc": now + (15 * 86400),  # 15 jours d'essai
        "created_utc": now,
        "machines": [],
    }

    url = f"{_FS_BASE}/licenses/{uid}"
    payload = {"fields": _dict_to_fields(doc_data)}
    try:
        _patch_json(url, payload, id_token)
        return True
    except urllib.error.HTTPError as e:
        raise Exception(f"Erreur création document : {_firebase_error(e)}")


def add_machine(uid: str, id_token: str, machine_id: str, label: str = "") -> bool:
    """
    Ajoute machine_id dans /licenses/{uid}/machines si count < 2.
    - Si la machine est déjà présente : retourne True (rien à faire).
    - Si count >= 2 : lève Exception("2 appareils max atteint").
    - Sinon : ajoute et retourne True.
    """
    doc = get_license_doc(uid, id_token)
    if doc is None:
        raise Exception("Document de licence introuvable.")

    machines: list = doc.get("machines", [])

    # Déjà enregistrée ?
    for m in machines:
        if isinstance(m, dict) and m.get("id") == machine_id:
            return True

    # Limite atteinte ?
    if len(machines) >= 2:
        raise Exception(
            "2 appareils maximum autorisés pour ce compte.\n"
            "Déconnectez-vous d'un autre appareil pour continuer."
        )

    # Ajouter la machine
    machines.append({
        "id": machine_id,
        "label": label or machine_id[:16],
        "activated_at": datetime.now(timezone.utc).timestamp(),
    })

    # Mettre à jour uniquement le champ machines
    url = f"{_FS_BASE}/licenses/{uid}?updateMask.fieldPaths=machines"
    payload = {
        "fields": {
            "machines": _to_firestore(machines)
        }
    }
    try:
        _patch_json(url, payload, id_token)
        return True
    except urllib.error.HTTPError as e:
        raise Exception(f"Erreur mise à jour machines : {_firebase_error(e)}")


def remove_machine(uid: str, id_token: str, machine_id: str) -> bool:
    """
    Retire machine_id de /licenses/{uid}/machines.
    Utilisé lors du logout (deactivate_machine).
    """
    doc = get_license_doc(uid, id_token)
    if doc is None:
        return True  # Rien à faire

    machines: list = doc.get("machines", [])
    new_machines = [m for m in machines if not (isinstance(m, dict) and m.get("id") == machine_id)]

    url = f"{_FS_BASE}/licenses/{uid}?updateMask.fieldPaths=machines"
    payload = {"fields": {"machines": _to_firestore(new_machines)}}
    try:
        _patch_json(url, payload, id_token)
        return True
    except urllib.error.HTTPError as e:
        raise Exception(f"Erreur suppression machine : {_firebase_error(e)}")
