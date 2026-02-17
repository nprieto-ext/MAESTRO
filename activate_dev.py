"""
Activation licence developpeur MyStrow (offline, 1 an)
Usage: py activate_dev.py
"""
import json
from datetime import datetime, timezone
from license_manager import (
    get_machine_id, _save_license_data, _sign_data, get_license_info
)

machine_id = get_machine_id()
now_utc = datetime.now(timezone.utc).timestamp()

# Licence valable 365 jours
license_data = {
    "type": "license",
    "machine_id": machine_id,
    "created_utc": now_utc,
    "expiry_utc": now_utc + (365 * 86400),
    "last_launch_utc": now_utc,
    "last_monotonic": 0,
}

# Signer avec la cle Ed25519 embarquee
data_str = json.dumps(license_data, sort_keys=True, separators=(',', ':'))
signature = _sign_data(data_str.encode())

if not signature:
    print("ERREUR: impossible de signer la licence")
    exit(1)

license_data["signature"] = signature

if _save_license_data(machine_id, license_data):
    print("Licence developpeur activee (365 jours)")
    print(json.dumps(get_license_info(), indent=2))
else:
    print("ERREUR: impossible de sauvegarder la licence")
