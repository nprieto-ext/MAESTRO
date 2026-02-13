#!/usr/bin/env python3
"""
Outil d'administration pour Maestro.py - Generation de cles et licences
NE PAS DISTRIBUER avec l'application

Usage:
    python license_keygen.py --generate-keypair
    python license_keygen.py --sign --machine-id XXXX --type trial --days 7
    python license_keygen.py --sign --machine-id XXXX --type license --days 365
    python license_keygen.py --sign-exe path/to/maestro.exe
"""

import argparse
import json
import hashlib
import sys
import os
import time
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption
    )
except ImportError:
    print("ERREUR: pip install cryptography")
    sys.exit(1)


KEYS_DIR = os.path.join(os.path.dirname(__file__), "keys")


def generate_keypair():
    """Genere une paire de cles Ed25519"""
    os.makedirs(KEYS_DIR, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()

    # Sauvegarder cle privee
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    private_path = os.path.join(KEYS_DIR, "private_key.pem")
    with open(private_path, "wb") as f:
        f.write(private_pem)

    # Sauvegarder cle publique
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    public_path = os.path.join(KEYS_DIR, "public_key.pem")
    with open(public_path, "wb") as f:
        f.write(public_pem)

    print(f"Cle privee: {private_path}")
    print(f"Cle publique: {public_path}")
    print()
    print("=== CLE PUBLIQUE (a copier dans license_manager.py) ===")
    print(public_pem.decode())


def load_private_key():
    """Charge la cle privee depuis le dossier keys/"""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    path = os.path.join(KEYS_DIR, "private_key.pem")
    if not os.path.exists(path):
        print(f"ERREUR: {path} non trouve. Lancez --generate-keypair d'abord.")
        sys.exit(1)

    with open(path, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def sign_license(machine_id, license_type, days):
    """Genere et signe une licence"""
    private_key = load_private_key()

    now_utc = datetime.now(timezone.utc).timestamp()

    license_data = {
        "type": license_type,
        "machine_id": machine_id,
        "created_utc": now_utc,
        "expiry_utc": now_utc + (days * 86400),
        "last_launch_utc": now_utc,
        "last_monotonic": 0,
    }

    # Signer les donnees
    data_str = json.dumps(license_data, sort_keys=True, separators=(',', ':'))
    signature = private_key.sign(data_str.encode())
    license_data["signature"] = signature.hex()

    # Sauvegarder en JSON (pour envoi au client ou insertion dans Firebase)
    output_path = os.path.join(
        KEYS_DIR,
        f"license_{license_type}_{machine_id[:8]}.json"
    )
    with open(output_path, "w") as f:
        json.dump(license_data, f, indent=2)

    print(f"Licence generee: {output_path}")
    print(f"  Type: {license_type}")
    print(f"  Machine: {machine_id[:16]}...")
    print(f"  Expire: {datetime.fromtimestamp(license_data['expiry_utc'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Signature: {license_data['signature'][:32]}...")

    return license_data


def sign_exe(exe_path):
    """Signe un executable pour l'anti-patch"""
    private_key = load_private_key()

    if not os.path.exists(exe_path):
        print(f"ERREUR: {exe_path} non trouve.")
        sys.exit(1)

    # Calculer SHA256
    sha256 = hashlib.sha256()
    with open(exe_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    exe_hash = sha256.hexdigest()

    # Signer le hash
    signature = private_key.sign(exe_hash.encode())

    sig_data = {
        "hash": exe_hash,
        "signature": signature.hex(),
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }

    sig_path = exe_path + ".sig"
    with open(sig_path, "w") as f:
        json.dump(sig_data, f, indent=2)

    print(f"Executable signe: {sig_path}")
    print(f"  SHA256: {exe_hash}")
    print(f"  Signature: {sig_data['signature'][:32]}...")


def main():
    parser = argparse.ArgumentParser(description="Maestro License Keygen")

    parser.add_argument("--generate-keypair", action="store_true",
                        help="Generer une paire de cles Ed25519")
    parser.add_argument("--sign", action="store_true",
                        help="Signer une licence")
    parser.add_argument("--sign-exe", type=str,
                        help="Signer un executable (.exe)")
    parser.add_argument("--machine-id", type=str,
                        help="Machine ID du client")
    parser.add_argument("--type", type=str, choices=["trial", "license"],
                        help="Type de licence")
    parser.add_argument("--days", type=int, default=7,
                        help="Duree en jours")

    args = parser.parse_args()

    if args.generate_keypair:
        generate_keypair()
    elif args.sign:
        if not args.machine_id:
            print("ERREUR: --machine-id requis")
            sys.exit(1)
        if not args.type:
            print("ERREUR: --type requis (trial ou license)")
            sys.exit(1)
        sign_license(args.machine_id, args.type, args.days)
    elif args.sign_exe:
        sign_exe(args.sign_exe)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
