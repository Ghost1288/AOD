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
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=yes
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
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AOD"; ValueData: """{app}\AOD.exe"" --hidden"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\AOD.exe"; Description: "Start AOD now"; Flags: nowait postinstall; Check: ShouldRun

[Code]
function ShouldRun: Boolean;
begin
  Result := ExpandConstant('{param:NORUN|0}') <> '1';
end;

