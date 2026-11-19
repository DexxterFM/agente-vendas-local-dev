param(
  [switch]$SkipTests,
  [switch]$SkipBackend,
  [switch]$SkipInstaller,
  [string]$Version = '1.1.0'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root
try {
  $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
  if (-not (Test-Path $iscc)) { throw "Inno Setup 6 nao foi encontrado em '$iscc'." }

  Write-Host "[0/6] Fixando a versao $Version nos instaladores..."
  [System.IO.File]::WriteAllText((Join-Path $root 'version.iss'), ('#define AppVersion "' + $Version + '"' + [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))

  if (-not $SkipTests) {
    Write-Host '[1/6] Executando a suite de testes...'
    python -m unittest discover -s .\tests
    if ($LASTEXITCODE -ne 0) { throw 'Os testes falharam; release cancelado.' }
  }

  if (-not $SkipBackend) {
    Write-Host '[2/6] Empacotando o backend persistente...'
    pyinstaller --noconfirm .\SalesAgentBackend.spec
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao empacotar o backend.' }
  }

  Write-Host '[3/6] Empacotando o painel local...'
  npm.cmd run desktop:build
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao empacotar o painel local.' }

  Write-Host '[4/6] Empacotando o painel de controle da VPS...'
  npm.cmd run desktop:build:remote
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao empacotar o painel de controle da VPS.' }

  if (-not $SkipInstaller) {
    Write-Host '[5/6] Gerando os instaladores...'
    & $iscc .\installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o instalador local.' }
    & $iscc .\installer-remote.iss
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o instalador de controle da VPS.' }
  }

  Write-Host '[6/6] Montando o pacote de entrega...'
  $releaseDir = Join-Path $root ('dist\release\AgenteVendas-' + $Version)
  if (Test-Path $releaseDir) { Remove-Item -Path $releaseDir -Recurse -Force }
  New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

  $payload = @(
    'dist\installer\AgenteVendasLocal-Setup.exe',
    'dist\installer\AgenteVendasControleVPS-Setup.exe',
    'scripts\configurar-conexao.ps1',
    'scripts\operar-painel.ps1',
    'OPERACAO.md',
    '.env.example'
  )
  foreach ($item in $payload) {
    $source = Join-Path $root $item
    if (-not (Test-Path $source)) { throw "Arquivo de entrega ausente: $item" }
    Copy-Item -Path $source -Destination (Join-Path $releaseDir (Split-Path -Leaf $source)) -Force
  }

  $zip = Join-Path $root ('dist\release\AgenteVendas-' + $Version + '.zip')
  if (Test-Path $zip) { Remove-Item -Path $zip -Force }
  Add-Type -AssemblyName System.IO.Compression
  $zipStream = [System.IO.File]::Open($zip, [System.IO.FileMode]::Create)
  $archive = [System.IO.Compression.ZipArchive]::new($zipStream, [System.IO.Compression.ZipArchiveMode]::Create, $true)
  try {
    foreach ($file in Get-ChildItem -Path $releaseDir -File) {
      $entry = $archive.CreateEntry($file.Name, [System.IO.Compression.CompressionLevel]::Optimal)
      $entryStream = $entry.Open()
      $input = [System.IO.File]::OpenRead($file.FullName)
      try { $input.CopyTo($entryStream, 1048576) } finally { $input.Dispose(); $entryStream.Dispose() }
    }
  } finally {
    $archive.Dispose()
    $zipStream.Dispose()
  }

  Write-Host "Release pronto: $zip"
  Write-Host "Pasta: $releaseDir"
} finally {
  Pop-Location
}
