$ErrorActionPreference = "Stop"
pyinstaller --noconfirm --clean --onefile --windowed --name SalesAgentLocal .\sales_agent_unified\app.py
Write-Host "Build concluído: dist\SalesAgentLocal.exe"
