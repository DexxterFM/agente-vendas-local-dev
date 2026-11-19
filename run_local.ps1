$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Test-Port([int]$Port) {
  try { return (Test-NetConnection 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded }
  catch { return $false }
}

$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not (Test-Port 11434) -and $ollama) {
  Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
}

$browserServer = if ($env:BROWSEROS_SERVER) { $env:BROWSEROS_SERVER } else { "C:\Users\denis\AppData\Local\BrowserClaw\Application\155.0.8318.26\BrowserClawServer\default\resources\bin\browseros-claw-server.exe" }
$browserConfig = if ($env:BROWSEROS_CONFIG) { $env:BROWSEROS_CONFIG } else { "C:\Users\denis\AppData\Local\BrowserClaw\User Data\.browseros\config.json" }
if (-not (Test-Port 9210) -and (Test-Path $browserServer) -and (Test-Path $browserConfig)) {
  Start-Process -FilePath $browserServer -ArgumentList "--config `"$browserConfig`"" -WindowStyle Hidden
}

Start-Sleep -Seconds 3
python .\health_check.py
if (Test-Path .\dist\SalesAgentLocalV3.exe) {
  Start-Process -FilePath (Join-Path $root "dist\SalesAgentLocalV3.exe")
} elseif (Test-Path .\dist\SalesAgentLocalV2.exe) {
  Start-Process -FilePath (Join-Path $root "dist\SalesAgentLocalV2.exe")
} elseif (Test-Path .\dist\SalesAgentLocal.exe) {
  Start-Process -FilePath (Join-Path $root "dist\SalesAgentLocal.exe")
} else {
  python .\app.py
}
