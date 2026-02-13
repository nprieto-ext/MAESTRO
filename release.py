import subprocess
import sys
import re
from pathlib import Path

INNO_PATH = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
ISS_FILE = "installer\\maestro.iss"
MAIN_FILE = "maestro_new.py"


def run(cmd):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("Erreur détectée. Arrêt.")
        sys.exit(1)


def get_current_version():
    content = Path(MAIN_FILE).read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"(.*?)"', content)
    return match.group(1) if match else None


def update_version(new_version):
    # Update Python file
    content = Path(MAIN_FILE).read_text(encoding="utf-8")
    content = re.sub(
        r'APP_VERSION\s*=\s*"(.*?)"',
        f'APP_VERSION = "{new_version}"',
        content,
    )
    Path(MAIN_FILE).write_text(content, encoding="utf-8")

    # Update ISS file
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

print(f"\nMise à jour vers {new_version}...")

update_version(new_version)

# Nettoyage
if Path("build").exists():
    run("rmdir /s /q build")
if Path("dist").exists():
    run("rmdir /s /q dist")

# Build exe
run("pyinstaller --onefile --windowed maestro_new.py")

# Build installer
run(f'"{INNO_PATH}" {ISS_FILE}')

# Git commit + tag
run("git add .")
run(f'git commit -m "Release {new_version}"')
run(f"git tag v{new_version}")
run("git push origin main --tags")

print("\n========== RELEASE TERMINE ==========")