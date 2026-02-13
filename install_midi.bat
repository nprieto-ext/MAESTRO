@echo off
echo ========================================
echo Installation MIDI pour AKAI APC mini
echo ========================================
echo.
echo Installation de python-rtmidi...
py -m pip install python-rtmidi
echo.
echo ========================================
echo Installation terminee!
echo ========================================
echo.
echo Vous pouvez maintenant lancer:
echo   py test_midi.py     (pour tester)
echo   py maestro.py       (pour lancer le logiciel)
echo.
pause
