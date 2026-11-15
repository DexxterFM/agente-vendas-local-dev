[CmdletBinding(SupportsShouldProcess)]
param(
  [string]$InstallRoot = "",
  [string]$Package = ""
)

if ([string]::IsNullOrWhiteSpace($Package)) {
  $Package = Join-Path (Split-Path -Parent $PSScriptRoot) "dist\AgenteVendasLocal-update.asar"
}
if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
  $candidates = @()
  if ($env:LOCALAPPDATA) { $candidates += Join-Path $env:LOCALAPPDATA "Programs\SalesAgentLocal" }
  $candidates += Get-ChildItem -LiteralPath "C:\Users" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    Join-Path $_.FullName "AppData\Local\Programs\SalesAgentLocal"
  }
  $InstallRoot = $candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ "resources\app.asar") } | Select-Object -First 1
}
$target = Join-Path $InstallRoot "resources\app.asar"
if (!(Test-Path -LiteralPath $Package)) { throw "Pacote de atualização não encontrado: $Package" }
if (!(Test-Path -LiteralPath $target)) { throw "Instalação local não encontrada: $target" }

$packageHash = (Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash
if (!$packageHash) { throw "Não foi possível validar a integridade do pacote." }

$backupRoot = Join-Path $env:LOCALAPPDATA "Programs\SalesAgentLocal\backups"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $backupRoot "app-$stamp.asar"

if ($PSCmdlet.ShouldProcess($target, "Criar backup e instalar pacote validado")) {
  New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
  Copy-Item -LiteralPath $target -Destination $backup -Force
  Copy-Item -LiteralPath $Package -Destination $target -Force
  $installedHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
  if ($installedHash -ne $packageHash) {
    Copy-Item -LiteralPath $backup -Destination $target -Force
    throw "A validação final falhou; a versão anterior foi restaurada."
  }
  [pscustomobject]@{ Installed = $true; Backup = $backup; Hash = $installedHash }
}
