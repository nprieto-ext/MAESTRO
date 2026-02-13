@echo off
echo ============================
echo BUILD MAESTRO
echo ============================

echo.
echo 1) Nettoyage ancien build...
rmdir /s /q build
rmdir /s /q dist

echo.
echo 2) Build exe...
pyinstaller --onefile --windowed maestro_new.py

echo.
echo 3) Build installer...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\maestro.iss

echo.
echo ============================
echo BUILD TERMINE
echo ============================

pause