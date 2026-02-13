import subprocess
import sys
import re
from pathlib import Path

INNO_PATH = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
ISS_FILE = "installer\\maestro.iss"
CONFIG_FILE = "config.py"
SETUP_OUTPUT = "installer\\installer_output\\Maestro_Setup.exe"


def run(cmd, allow_fail=False):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0 and not allow_fail:
        print("Erreur détectée. Arrêt.")
        sys.exit(1)


def get_current_version():
    content = Path(CONFIG_FILE).read_text(encoding="utf-8")
    match = re.search(r'VERSION\s*=\s*"(.*?)"', content)
    return match.group(1) if match else None


def update_version(new_version):
    # Update config.py
    content = Path(CONFIG_FILE).read_text(encoding="utf-8")
    content = re.sub(
        r'VERSION\s*=\s*"(.*?)"',
        f'VERSION = "{new_version}"',
        content,
    )
    Path(CONFIG_FILE).write_text(content, encoding="utf-8")

    # Update installer .iss
    iss_content = Path(ISS_FILE).read_text(encoding="utf-8")
    iss_content = re.sub(
        r'AppVersion=.*',
        f'AppVersion={new_version}',
        iss_content,
    )
    Path(ISS_FILE).write_text(iss_content, encoding="utf-8")


print("========== RELEASE MAESTRO ==========")

current_version = get_current_version()
print(f"Version actuelle : {current_version}")

new_version = input("Nouvelle version ? (ex: 1.0.2) : ").strip()

if not new_version:
    print("Version invalide.")
    sys.exit(1)

if new_version == current_version:
    print("La version est identique. On continue quand même.")

print(f"\nMise à jour vers {new_version}...")
update_version(new_version)

# Nettoyage build
if Path("build").exists():
    run("rmdir /s /q build")
if Path("dist").exists():
    run("rmdir /s /q dist")

# Build EXE
run("pyinstaller --onefile --windowed maestro_new.py")

# Build Installer
run(f'"{INNO_PATH}" {ISS_FILE}')

# Git commit + tag
run("git add .")
run(f'git commit -m "Release {new_version}" --allow-empty', allow_fail=True)
run(f"git tag v{new_version}")
run("git push origin main --tags")

# Create GitHub Release + upload installer
print("\nCréation GitHub Release...")
run(
    f'gh release create v{new_version} "{SETUP_OUTPUT}" '
    f'--title "Maestro v{new_version}" '
    f'--notes "Release version {new_version}"'
)

print("\n========== RELEASE + UPLOAD TERMINE ==========")