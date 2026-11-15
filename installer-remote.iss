#define AppName "Agente de Vendas - Controle VPS"
#define AppVersion "1.0.0"
#define AppExe "AgenteVendasControleVPS.exe"
[Setup]
AppId={{12D2AB3B-3F6A-4A8B-9A41-849CB5C3D26E}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\SalesAgentRemoteControl
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=AgenteVendasControleVPS-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
[Files]
Source: "dist\remote-control\AgenteVendasControleVPS-win32-x64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"
[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
