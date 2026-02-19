"""
Genere MyStrow.exe.sig (hash SHA256 + signature Ed25519).
Usage: python _gen_sig.py dist/MyStrow.exe
"""
import sys
import json
import hashlib
from pathlib import Path

exe_path = Path(sys.argv[1])

sha256 = hashlib.sha256()
with open(exe_path, "rb") as f:
    for chunk in iter(lambda: f.read(8192), b""):
        sha256.update(chunk)
exe_hash = sha256.hexdigest()

signature = ""
try:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    _KS = b"MC4CAQAwBQYDK2VwBCIEIO4dq7bapt3BQlEKe5aYxrP0aH9KbiN/Xdc/oij6uMQm"
    pem = b"-----BEGIN PRIVATE KEY-----\n" + _KS + b"\n-----END PRIVATE KEY-----\n"
    key = load_pem_private_key(pem, password=None)
    signature = key.sign(exe_hash.encode()).hex()
except Exception as e:
    print(f"Signature ignoree : {e}")

sig_path = Path(str(exe_path) + ".sig")
sig_path.write_text(json.dumps({"hash": exe_hash, "signature": signature}))
print(f"Sig generated : {exe_hash[:16]}...")
