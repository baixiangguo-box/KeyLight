$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$buildRoot = (Resolve-Path (Join-Path $projectRoot '.build')).Path
$runner = (Get-Command python).Source
$before = Invoke-RestMethod 'http://127.0.0.1:8787/api/state'
$before.params | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $buildRoot 'before-hardware-params.json') -Encoding UTF8
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) '键光.lnk'
$env:KEYLIGHT_DATA_DIR = Join-Path $buildRoot 'hardware-qa-data'
$checks = [System.Collections.Generic.List[string]]::new()
$frozenProcess = $null
try {
    Invoke-RestMethod 'http://127.0.0.1:8787/api/shutdown' -Method Post -ContentType 'application/json' -Body '{}' | Out-Null
    Start-Sleep -Milliseconds 900
    $env:PATH = $env:SystemRoot+'\System32'
    $exe = Join-Path $projectRoot 'dist\KeyLight\键光.exe'
    $frozenProcess = Start-Process -FilePath $exe -ArgumentList '--no-open' -WindowStyle Hidden -PassThru
    $ready=$false
    for($i=0; $i -lt 50; $i++) {
        try { $state=Invoke-RestMethod 'http://127.0.0.1:8787/api/state'; if($state.build -eq '20261024-creator1' -and $state.device.connected){$ready=$true; break} } catch {}
        Start-Sleep -Milliseconds 100
    }
    if(-not $ready -or $state.device.model.name -ne 'WIN 60 HE') { throw 'Packaged keyboard connection failed.' }
    $checks.Add('Self-contained EXE connects to the real WIN 60 HE')
    $params = @{effect='audio';audio_style='staggered';brightness=1;speed=1;color=@(63,196,229);color2=@(30,123,255)}
    Invoke-RestMethod 'http://127.0.0.1:8787/api/params' -Method Post -ContentType 'application/json' -Body ($params|ConvertTo-Json -Compress) | Out-Null
    & $runner -B (Join-Path $projectRoot 'tests\live_audio_check.py') --allow-hardware --output (Join-Path $buildRoot 'frozen-live-audio.json')
    if($LASTEXITCODE -ne 0) { throw 'Packaged audio/HID checks failed.' }
    $checks.Add('Packaged WASAPI loopback follows eight beats and produces staggered lighting frames')
} finally {
    if($frozenProcess) {
        Start-Process -FilePath (Join-Path $projectRoot 'dist\KeyLight\键光.exe') -ArgumentList '--shutdown' -WindowStyle Hidden -Wait
        if(-not $frozenProcess.WaitForExit(5000)) { throw 'Packaged process did not exit normally.' }
    }
    Remove-Item Env:KEYLIGHT_DATA_DIR -ErrorAction SilentlyContinue
    Start-Process -FilePath $desktopShortcut -WindowStyle Hidden
}
Start-Sleep -Seconds 2
$after=Invoke-RestMethod 'http://127.0.0.1:8787/api/state'
if(($after.params|ConvertTo-Json -Compress) -ne ($before.params|ConvertTo-Json -Compress)) { throw 'Original parameters changed.' }
if($after.presets.Count -ne $before.presets.Count -or $after.custom.Count -ne $before.custom.Count) { throw 'Original presets changed.' }
$checks.Add('Original source app, user settings and presets restored')
[ordered]@{ok=$true;checks=$checks;device='WIN 60 HE';python_path_hidden=$true;other_models_tested=$false} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $buildRoot 'hardware-qa.json') -Encoding UTF8
Get-Content -LiteralPath (Join-Path $buildRoot 'hardware-qa.json') -Raw -Encoding UTF8
