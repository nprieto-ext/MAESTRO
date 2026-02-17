import subprocess
import sys
import re
from pathlib import Path

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "core.py"
ISS_FILE = BASE_DIR / "installer" / "maestro.iss"

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
# RELEASE
# ------------------------------------------------------------------

print("========== RELEASE MYSTROW ==========")

current_version = get_current_version()
print(f"Version actuelle : {current_version}")

new_version = input(f"Nouvelle version ? [{bump_version(current_version)}] : ").strip()
if not new_version:
    new_version = bump_version(current_version)

print(f"\nMise a jour vers {new_version}...")
update_version(new_version)

# Git commit + tag + push (le CI build Windows + Mac automatiquement)
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
