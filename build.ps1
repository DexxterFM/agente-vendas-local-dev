$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root
try {
  pyinstaller --noconfirm --clean --onefile --windowed --name SalesAgentLocal .\app.py
  Write-Host "Build concluído: dist\SalesAgentLocal.exe"
} finally {
  Pop-Location
}
