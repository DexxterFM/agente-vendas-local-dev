param(
  [switch]$SkipTests,
  [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root
try {
  if (-not $SkipTests) {
    Write-Host "Executando a suíte do produto..."
    python -m unittest discover -s .\tests
    if ($LASTEXITCODE -ne 0) { throw "Os testes falharam; build cancelado." }
  }

  Write-Host "Empacotando o backend persistente..."
  pyinstaller --noconfirm .\SalesAgentBackend.spec
  if ($LASTEXITCODE -ne 0) { throw "Falha ao empacotar o backend." }

  Write-Host "Empacotando a aplicação desktop Electron..."
  npm.cmd run desktop:build
  if ($LASTEXITCODE -ne 0) { throw "Falha ao empacotar a aplicação desktop." }

  if (-not $SkipInstaller) {
    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $iscc)) { throw "Inno Setup 6 não foi encontrado." }
    Write-Host "Gerando o instalador Windows..."
    & $iscc .\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }
  }

  Write-Host "Produto pronto: dist\installer\AgenteVendasLocal-Setup.exe"
} finally {
  Pop-Location
}
