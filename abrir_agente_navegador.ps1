param(
  [int]$Port = 4173
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $ProjectRoot 'frontend'
$Url = "http://127.0.0.1:$Port/"

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $existing) {
  Start-Process python -ArgumentList '-m','http.server',"$Port",'--directory',"$Frontend" -WorkingDirectory $ProjectRoot -WindowStyle Hidden
  Start-Sleep -Milliseconds 900
}

$edge = Get-Command msedge.exe -ErrorAction SilentlyContinue
$chrome = Get-Command chrome.exe -ErrorAction SilentlyContinue
if ($edge) {
  Start-Process $edge.Source -ArgumentList "--app=$Url","--start-maximized"
} elseif ($chrome) {
  Start-Process $chrome.Source -ArgumentList "--app=$Url","--start-maximized"
} else {
  Start-Process $Url
}

Write-Host "Agente de Vendas Local aberto em $Url"
