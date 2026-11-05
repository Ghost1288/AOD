; Inno Setup script - builds AOD-Setup.exe from the PyInstaller output in host\dist\AOD
[Setup]
AppName=AOD
AppVersion=2.0
AppPublisher=AOD
DefaultDirName={autopf}\AOD
DefaultGroupName=AOD
OutputBaseFilename=AOD-Setup
OutputDir=Output
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\AOD.exe

[Files]
Source: "..\host\dist\AOD\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Tasks]
Name: "startup"; Description: "Start AOD when Windows starts"; Flags: checkedonce

[Icons]
Name: "{group}\AOD"; Filename: "{app}\AOD.exe"
Name: "{autodesktop}\AOD"; Filename: "{app}\AOD.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AOD"; ValueData: """{app}\AOD.exe"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""AOD host"" dir=in action=allow program=""{app}\AOD.exe"" enable=yes profile=private"; Flags: runhidden
Filename: "{app}\AOD.exe"; Description: "Start AOD now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""AOD host"""; Flags: runhidden
