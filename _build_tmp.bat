@echo off
cd /d "C:\Users\nikop\Desktop\MyStrow"
"C:\Users\nikop\AppData\Local\Programs\Python\Python313\python.exe" -m PyInstaller --onefile --windowed --icon=mystrow.ico --add-data "logo.png;." --add-data "mystrow.ico;." --name=MyStrow --paths="C:\Users\nikop\Desktop\MyStrow" --noconfirm main.py
