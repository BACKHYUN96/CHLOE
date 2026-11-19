$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$localData = Join-Path $PSScriptRoot ".data"
New-Item -ItemType Directory -Path $localData -Force | Out-Null
$address = "http://127.0.0.1:8768"
$ready = $false
try {
    $state = Invoke-RestMethod "$address/api/state" -TimeoutSec 2
    $ready = [bool]($state.token -and $state.models)
} catch {}
if (-not $ready) {
    $python = Get-Command py.exe -ErrorAction SilentlyContinue
    $prefix = @("-3")
    if (-not $python) {
        $python = Get-Command python.exe -ErrorAction Stop
        $prefix = @()
    }
    $script = Join-Path $PSScriptRoot "server.py"
    $quotedScript = '"' + $script + '"'
    $process = Start-Process -FilePath $python.Source -ArgumentList ($prefix + @($quotedScript)) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localData "server.stdout.log") -RedirectStandardError (Join-Path $localData "server.stderr.log")
    $process.Id | Set-Content -LiteralPath (Join-Path $localData "server.pid")
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 250
        try {
            $state = Invoke-RestMethod "$address/api/state" -TimeoutSec 1
            if ($state.token -and $state.models) { $ready = $true; break }
        } catch {}
        if ($process.HasExited) { break }
    }
}
if (-not $ready) {
    Write-Host "클로이 서버를 시작하지 못했습니다. Python 3.10 이상 설치와 .data/server.stderr.log를 확인해 주세요."
    Read-Host "Enter"
    exit 1
}
Start-Process $address
