#define AppName "Agente de Vendas - Controle VPS"
#include "version.iss"
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
Source: "scripts\configurar-conexao.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "scripts\operar-painel.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "OPERACAO.md"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\Configurar conexao VPS"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\configurar-conexao.ps1"""; IconFilename: "{app}\{#AppExe}"
Name: "{autoprograms}\Operar agente - status"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\operar-painel.ps1"" -Action status"; IconFilename: "{app}\{#AppExe}"
[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
