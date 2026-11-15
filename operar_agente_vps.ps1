$ErrorActionPreference = 'Stop'
$ssh = (Get-Command ssh -ErrorAction Stop).Source
Start-Process -FilePath $ssh -ArgumentList @('-N','-L','8787:127.0.0.1:8787','erpclinicatea-vps') -WindowStyle Hidden
Start-Sleep -Seconds 2
Start-Process 'http://127.0.0.1:8787/'
