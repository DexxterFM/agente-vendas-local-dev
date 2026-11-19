param(
  [string]$SshHost,
  [int]$LocalPort = 8787,
  [int]$RemotePort = 8787,
  [string]$UserDataDir,
  [switch]$SkipConnectionTest
)

$ErrorActionPreference = 'Stop'

function Get-PanelUserDataDir {
  param([string]$Explicit)
  if ($Explicit) { return $Explicit }
  $candidates = @(
    (Join-Path $env:APPDATA 'AgenteVendasControleVPS'),
    (Join-Path $env:APPDATA 'AgenteVendasLocal')
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) { return $candidate }
  }
  return $candidates[0]
}

function Test-SshTarget {
  param([string]$Target)
  $ssh = Get-Command ssh -ErrorAction Stop
  $arguments = @('-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=accept-new',$Target,'true')
  $output = & $ssh.Source @arguments 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "Nao foi possivel conectar via SSH em '$Target': $($output -join ' ')"
  }
}

$panelData = Get-PanelUserDataDir -Explicit $UserDataDir
New-Item -ItemType Directory -Path $panelData -Force | Out-Null
$configPath = Join-Path $panelData 'remote-control.json'

if (-not $SshHost) {
  $current = $null
  if (Test-Path $configPath) {
    try { $current = Get-Content $configPath -Raw | ConvertFrom-Json } catch {}
  }
  $prompt = 'Host SSH da VPS (alias do arquivo ~/.ssh/config ou usuario@host)'
  if ($current -and $current.sshHost) { $prompt += " [atual: $($current.sshHost)]" }
  $SshHost = Read-Host $prompt
  if (-not $SshHost -and $current -and $current.sshHost) { $SshHost = $current.sshHost }
}

$SshHost = ([string]$SshHost).Trim()
if (-not $SshHost) { throw 'O host SSH e obrigatorio.' }
if ($LocalPort -lt 1024 -or $LocalPort -gt 65535) { throw 'LocalPort fora da faixa 1024-65535.' }
if ($RemotePort -lt 1 -or $RemotePort -gt 65535) { throw 'RemotePort fora da faixa 1-65535.' }

if (-not $SkipConnectionTest) {
  Write-Host "Testando SSH em '$SshHost'..."
  Test-SshTarget -Target $SshHost
  Write-Host 'SSH OK.'
}

$config = [ordered]@{
  enabled = $true
  sshHost = $SshHost
  localPort = $LocalPort
  remotePort = $RemotePort
  sshOptions = '-o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3'
}
$temporary = "$configPath.tmp"
[System.IO.File]::WriteAllText($temporary, ($config | ConvertTo-Json -Depth 4), [System.Text.UTF8Encoding]::new($false))
Move-Item -Path $temporary -Destination $configPath -Force

Write-Host "Conexao configurada em: $configPath"
Write-Host "Host: $SshHost | RPC local: $LocalPort | RPC remoto: $RemotePort"
Write-Host 'Abra o atalho "Agente de Vendas - Controle VPS" para operar o painel.'
