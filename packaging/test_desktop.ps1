param([string]$AppPath = '', [int]$Port = 8797)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$buildRoot = (Resolve-Path (Join-Path $projectRoot '.build')).Path
if (-not $AppPath) { $AppPath = Join-Path $projectRoot 'dist\KeyLight\键光.exe' }
$AppPath = (Resolve-Path -LiteralPath $AppPath).Path
$env:KEYLIGHT_DATA_DIR = Join-Path $buildRoot 'desktop-qa-data'
$env:PATH = $env:SystemRoot + '\System32'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class KeyLightDesktopQA {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
}
'@
$checks = [System.Collections.Generic.List[string]]::new()
$exeArgs = @('--no-device','--port',"$Port")
$instance = $null
try {
    $instance = Start-Process -FilePath $AppPath -ArgumentList $exeArgs -PassThru
    $ready = $false
    for ($i=0; $i -lt 200; $i++) {
        $instance.Refresh()
        if ($instance.HasExited) { throw 'Native app exited before creating its window' }
        if ($instance.MainWindowTitle -eq '键光' -and $instance.MainWindowHandle -ne 0) {
            try {
                $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health"
                if ($health.build -eq '20261024-creator1') { $ready = $true; break }
            } catch {}
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $ready) { throw 'Native app window or server never became ready' }
    $checks.Add('Packaged executable owns a real top-level KeyLight window; no host Python in PATH')
    & (Join-Path $projectRoot '.build\venv\Scripts\python.exe') -B (Join-Path $projectRoot 'tests\creator_package_check.py')
    if ($LASTEXITCODE -ne 0) { throw 'Frozen creator integration failed' }
    $checks.Add('Frozen creator conversation, auto-repair, cancel, explicit apply and sharing passed with local model fixture')
    $firstPid = $instance.Id
    [KeyLightDesktopQA]::ShowWindow($instance.MainWindowHandle,6) | Out-Null
    if (-not [KeyLightDesktopQA]::IsIconic($instance.MainWindowHandle)) { throw 'Minimize failed' }
    $second = Start-Process -FilePath $AppPath -ArgumentList $exeArgs -PassThru
    if (-not $second.WaitForExit(12000) -or $second.ExitCode -ne 0) { throw 'Second instance failed to exit normally' }
    if ([KeyLightDesktopQA]::IsIconic($instance.MainWindowHandle)) { throw 'Second launch did not restore the existing window' }
    $checks.Add('Second launch restores minimized existing instance and exits without a duplicate window')
    # Send the same Windows close message as the title-bar X, not an HTTP stop.
    [KeyLightDesktopQA]::PostMessage($instance.MainWindowHandle,0x0010,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
    if (-not $instance.WaitForExit(10000) -or $instance.ExitCode -ne 0) { throw 'Window X failed to stop the process cleanly' }
    $reachable = $false
    try { $null = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 1; $reachable=$true } catch {}
    if ($reachable) { throw 'Window X left a background HTTP server behind' }
    $checks.Add('Title-bar X shuts down process and releases its listening port')
    $instance = Start-Process -FilePath $AppPath -ArgumentList $exeArgs -PassThru
    for ($i=0; $i -lt 100; $i++) {
        try { $null = Invoke-RestMethod "http://127.0.0.1:$Port/api/health"; break } catch { Start-Sleep -Milliseconds 100 }
    }
    $restored=Invoke-RestMethod "http://127.0.0.1:$Port/api/creator"
    if ($restored.draft.name -ne 'Native creator QA' -or $restored.draft.brightness -ne .35) { throw 'Creator draft did not persist across native restart' }
    $checks.Add('Creator draft and manual parameters survive actual native restart')
    Invoke-RestMethod "http://127.0.0.1:$Port/api/shutdown" -Method Post -Body '{}' -ContentType 'application/json' | Out-Null
    if (-not $instance.WaitForExit(12000) -or $instance.ExitCode -ne 0) { throw 'API shutdown did not close the window and process' }
    $checks.Add('App relaunches after close; Exit Service also closes its window and process')
    [ordered]@{ok=$true; app=$AppPath; checks=$checks; first_pid=$firstPid; real_hardware_opened=$false} |
        ConvertTo-Json -Depth 4 | Set-Content (Join-Path $buildRoot 'desktop-qa.json') -Encoding UTF8
    Get-Content (Join-Path $buildRoot 'desktop-qa.json') -Raw -Encoding UTF8
} finally {
    if ($instance -and -not $instance.HasExited) {
        Start-Process -FilePath $AppPath -ArgumentList '--shutdown' -WindowStyle Hidden -Wait
        if (-not $instance.WaitForExit(10000)) { throw 'QA instance did not stop' }
    }
}
