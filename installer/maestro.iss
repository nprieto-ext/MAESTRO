[Setup]
AppName=Maestro
AppVersion=1.0.3
AppPublisher=Maestro
AppPublisherURL=https://maestro.fr
DefaultDirName={pf}\Maestro
DefaultGroupName=Maestro
OutputDir=installer_output
OutputBaseFilename=Maestro_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\maestro_new.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Maestro"; Filename: "{app}\maestro_new.exe"
Name: "{commondesktop}\Maestro"; Filename: "{app}\maestro_new.exe"

[Run]
Filename: "{app}\maestro_new.exe"; Description: "Lancer Maestro"; Flags: nowait postinstall skipifsilent