import subprocess
import sys
import re
import shutil
import hashlib
import json
from pathlib import Path

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "core.py"
ISS_FILE = BASE_DIR / "installer" / "maestro.iss"
DESKTOP = Path.home() / "Desktop"

# ------------------------------------------------------------------
# UTIL
# ------------------------------------------------------------------

def run(cmd, allow_fail=False):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0 and not allow_fail:
        print("Erreur detectee. Arret.")
        sys.exit(1)

def get_current_version():
    content = CONFIG_FILE.read_text(encoding="utf-8")
    match = re.search(r'VERSION\s*=\s*"(.*?)"', content)
    return match.group(1) if match else None

def bump_version(current):
    """Auto-increment patch version: 2.5.3 -> 2.5.4"""
    parts = current.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)

def update_version(new_version):
    # Update core.py
    content = CONFIG_FILE.read_text(encoding="utf-8")
    content = re.sub(
        r'VERSION\s*=\s*"(.*?)"',
        f'VERSION = "{new_version}"',
        content,
    )
    CONFIG_FILE.write_text(content, encoding="utf-8")

    # Update installer .iss
    iss_content = ISS_FILE.read_text(encoding="utf-8")
    iss_content = re.sub(
        r'AppVersion=.*',
        f'AppVersion={new_version}',
        iss_content,
    )
    ISS_FILE.write_text(iss_content, encoding="utf-8")

# ------------------------------------------------------------------
# BUILD LOCAL EXE
# ------------------------------------------------------------------

def generate_sig_file(exe_path):
    """Genere MyStrow.exe.sig (hash SHA256 + signature Ed25519)"""
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
        private_key = load_pem_private_key(pem, password=None)
        signature = private_key.sign(exe_hash.encode()).hex()
    except Exception as e:
        print(f"Avertissement: signature .sig non generee ({e})")

    sig_path = Path(str(exe_path) + ".sig")
    sig_path.write_text(json.dumps({"hash": exe_hash, "signature": signature}))
    print(f"Fichier .sig genere : {sig_path}")
    return sig_path


def build_local_installer(version):
    print("\n========== BUILD INSTALLEUR LOCAL ==========")
    dist_exe = BASE_DIR / "dist" / "MyStrow.exe"
    installer_out = BASE_DIR / "installer" / "installer_output" / "MyStrow_Setup.exe"

    # 1) Nettoyage des anciens builds
    for d in ["dist", "build"]:
        p = BASE_DIR / d
        if p.exists():
            shutil.rmtree(p)

    # 2) Build EXE via un .bat execute par cmd.exe (contourne MINGW64)
    print("\n--- PyInstaller ---")
    python_win = sys.executable.replace("/", "\\")
    base_win = str(BASE_DIR).replace("/", "\\")

    bat_path = BASE_DIR / "_build_tmp.bat"
    bat_path.write_text(
        f"@echo off\n"
        f"cd /d \"{base_win}\"\n"
        f"\"{python_win}\" -m PyInstaller "
        f"--onefile --windowed "
        f"--icon=mystrow.ico "
        f"--add-data \"logo.png;.\" "
        f"--add-data \"mystrow.ico;.\" "
        f"--name=MyStrow "
        f"--paths=\"{base_win}\" "
        f"--noconfirm main.py\n"
    )

    result = subprocess.run(
        ["cmd.exe", "/c", str(bat_path).replace("/", "\\")],
        cwd=str(BASE_DIR),
    )
    bat_path.unlink(missing_ok=True)

    if result.returncode != 0:
        print("ERREUR PyInstaller. Arret.")
        sys.exit(1)

    if not dist_exe.exists():
        print("ERREUR: MyStrow.exe non trouve apres PyInstaller.")
        sys.exit(1)

    # Generer le fichier .sig (requis par check_exe_integrity)
    generate_sig_file(dist_exe)

    # 3) Build installeur avec Inno Setup
    print("\n--- Inno Setup ---")
    iscc_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        "ISCC",  # si dans le PATH
    ]
    iscc = next((p for p in iscc_paths if Path(p).exists() or p == "ISCC"), None)
    if not iscc:
        print("ERREUR: Inno Setup (ISCC.exe) introuvable.")
        sys.exit(1)

    result = subprocess.run(
        f'"{iscc}" installer\\maestro.iss',
        shell=True, cwd=BASE_DIR
    )
    if result.returncode != 0:
        print("ERREUR Inno Setup. Arret.")
        sys.exit(1)

    if not installer_out.exists():
        print("ERREUR: MyStrow_Setup.exe non trouve apres Inno Setup.")
        sys.exit(1)

    # 4) Copie de l'installeur sur le Bureau
    dest = DESKTOP / f"MyStrow_Setup_{version}.exe"
    shutil.copy2(installer_out, dest)
    print(f"\nInstalleur copie sur le bureau : {dest}")


# ------------------------------------------------------------------
# RELEASE
# ------------------------------------------------------------------

print("========== RELEASE MYSTROW ==========")

current_version = get_current_version()
print(f"Version actuelle : {current_version}")

new_version = input(f"Nouvelle version ? [{bump_version(current_version)}] : ").strip()
if not new_version:
    new_version = bump_version(current_version)

print("\nQue veux-tu faire ?")
print("  1) Installeur local seulement (Bureau)")
print("  2) Push GitHub seulement (CI build)")
print("  3) Les deux")
choix = input("Choix [3] : ").strip() or "3"

if choix not in ("1", "2", "3"):
    print("Choix invalide. Arret.")
    sys.exit(1)

print(f"\nMise a jour vers {new_version}...")
update_version(new_version)

if choix in ("1", "3"):
    build_local_installer(new_version)

if choix in ("2", "3"):
    run("git add -A")
    run(f'git commit -m "Release {new_version}"', allow_fail=True)
    run(f"git tag v{new_version}")
    run("git push origin main --tags")
    print(f"\n========== TAG v{new_version} POUSSE ==========")
    print("GitHub Actions va maintenant builder:")
    print("  - Windows (EXE + Installer)")
    print("  - Mac (DMG)")
    print("La release GitHub sera creee automatiquement.")
    print(f"\nSuivre le build: https://github.com/nprieto-ext/MAESTRO/actions")
