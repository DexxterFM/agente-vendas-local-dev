param(
  [ValidateSet('open','configure','status','logs','stop','start')]
  [string]$Action = 'open',
  [string]$SshHost,
  [string]$UserDataDir,
  [int]$Lines = 80
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$configure = Join-Path $PSScriptRoot 'configurar-conexao.ps1'
$panelData = if ($UserDataDir) { $UserDataDir } else { Join-Path $env:APPDATA 'AgenteVendasControleVPS' }
$configPath = Join-Path $panelData 'remote-control.json'
$panelExeNames = @(
  (Join-Path $env:LOCALAPPDATA 'Programs\SalesAgentRemoteControl\AgenteVendasControleVPS.exe'),
  (Join-Path $root 'dist\remote-control\AgenteVendasControleVPS-win32-x64\AgenteVendasControleVPS.exe')
)

function Read-PanelHost {
  if ($SshHost) { return $SshHost }
  if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    if ($config.sshHost) { return $config.sshHost }
  }
  return $null
}

function Require-PanelHost {
  $panelHost = Read-PanelHost
  if (-not $panelHost) {
    Write-Host 'Conexao ainda nao configurada. Vou solicitar o host SSH.'
    & $configure -UserDataDir $panelData
    $panelHost = Read-PanelHost
  }
  return $panelHost
}

function Invoke-PanelSsh {
  param([string]$Target, [string]$RemoteCommand)
  $ssh = (Get-Command ssh -ErrorAction Stop).Source
  & $ssh -o BatchMode=yes -o ConnectTimeout=10 $Target $RemoteCommand
  if ($LASTEXITCODE -ne 0) { throw "Comando remoto falhou em '$Target'." }
}

switch ($Action) {
  'configure' {
    & $configure -SshHost $SshHost -UserDataDir $panelData
  }
  'open' {
    $panelHost = Require-PanelHost
    if (-not $panelHost) { throw 'Host SSH nao configurado.' }
    $exe = $panelExeNames | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $exe) { throw 'Painel nao encontrado. Instale o AgenteVendasControleVPS-Setup.exe.' }
    Write-Host "Abrindo painel conectado a '$panelHost'..."
    Start-Process -FilePath $exe
  }
  'status' {
    $panelHost = Require-PanelHost
    Invoke-PanelSsh -Target $panelHost -RemoteCommand "for s in agente-vendas-control agente-vendas-worker agente-vendas-internal-browser erpclinicatea.service; do printf '%s=' `$s; systemctl is-active `$s; done"
  }
  'logs' {
    $panelHost = Require-PanelHost
    Invoke-PanelSsh -Target $panelHost -RemoteCommand "journalctl -u agente-vendas-worker -n $Lines --no-pager"
  }
  'stop' {
    $panelHost = Require-PanelHost
    Invoke-PanelSsh -Target $panelHost -RemoteCommand 'sudo systemctl stop agente-vendas-worker agente-vendas-control'
  }
  'start' {
    $panelHost = Require-PanelHost
    Invoke-PanelSsh -Target $panelHost -RemoteCommand 'sudo systemctl start agente-vendas-control agente-vendas-worker'
  }
}
