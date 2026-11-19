param([string]$SshHost)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $root 'scripts\operar-painel.ps1') -Action open -SshHost $SshHost
if ($LASTEXITCODE -ne 0) { throw 'Falha ao abrir o painel da VPS.' }
