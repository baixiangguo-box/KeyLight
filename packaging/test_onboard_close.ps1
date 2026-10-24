# Live test: preserves user data, temporarily streams the user's current effect,
# closes the real packaged desktop window, and reads native settings afterwards.
param([string]$AppPath = '')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$buildRoot=(Resolve-Path (Join-Path $projectRoot '.build')).Path
if (-not $AppPath) { $AppPath=Join-Path $projectRoot 'dist\KeyLight\键光.exe' }
$AppPath=(Resolve-Path -LiteralPath $AppPath).Path
$sourceData=Join-Path $env:LOCALAPPDATA 'KeyLight\data'
$qaData=Join-Path $buildRoot ('native-close-data-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $qaData | Out-Null
foreach($name in @('settings.json','presets.json','custom_effects.json')) {
    $source=Join-Path $sourceData $name
    if(Test-Path -LiteralPath $source){Copy-Item -LiteralPath $source -Destination (Join-Path $qaData $name)}
}
$settingsPath=Join-Path $qaData 'settings.json'
$settings=Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedParams=$settings.params | ConvertTo-Json -Compress
if($settings.params.effect -ne 'ripple'){throw 'This live check expects the user-confirmed ripple settings.'}
$settings.control='software'
$settings.close_behavior='hold'
$settings | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $settingsPath -Encoding UTF8
# The app's JSON reader accepts utf-8-sig only on Python? Write plain UTF-8.
$utf8=[System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($settingsPath,($settings | ConvertTo-Json -Depth 10),$utf8)
$env:KEYLIGHT_DATA_DIR=$qaData
$env:PATH=$env:SystemRoot+'\System32'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class KeyLightOnboardCloseQA {
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
}
'@
$instance=$null
try {
    $instance=Start-Process -FilePath $AppPath -ArgumentList '--port','8797' -PassThru
    $ready=$false
    for($i=0;$i -lt 200;$i++){
        $instance.Refresh()
        try{
            $state=Invoke-RestMethod 'http://127.0.0.1:8797/api/state'
            if($state.build -eq '20261024-creator1' -and $state.device.connected -and $state.device.frames_sent -gt 10 -and $instance.MainWindowTitle -eq '键光'){$ready=$true;break}
        }catch{}
        Start-Sleep -Milliseconds 100
    }
    if(-not $ready){throw 'Packaged desktop did not stream to the real WIN60 HE.'}
    if(($state.params|ConvertTo-Json -Compress) -ne $expectedParams){throw 'User effect was not restored in isolated QA.'}
    [KeyLightOnboardCloseQA]::PostMessage($instance.MainWindowHandle,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
    if(-not $instance.WaitForExit(12000) -or $instance.ExitCode -ne 0){throw 'Title-bar close did not save and exit cleanly.'}
    $reachable=$false
    try{$null=Invoke-RestMethod 'http://127.0.0.1:8797/api/health' -TimeoutSec 1;$reachable=$true}catch{}
    if($reachable){throw 'The application left a background service behind.'}
    $persisted=Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if($persisted.control -ne 'firmware'){throw 'Verified native handoff was not saved.'}
    if(($persisted.params|ConvertTo-Json -Compress) -ne $expectedParams){throw 'Onboard close changed the software parameters.'}
    $runner=Join-Path $projectRoot '.build\venv\Scripts\python.exe'
    & $runner -B (Join-Path $projectRoot 'tests\read_onboard_after_close.py') --settings $settingsPath --output (Join-Path $buildRoot 'native-onboard-qa.json')
    if($LASTEXITCODE -ne 0){throw 'Fresh-handle native settings verification failed.'}
    Get-Content (Join-Path $buildRoot 'native-onboard-qa.json') -Raw -Encoding UTF8
}finally{
    if($instance -and -not $instance.HasExited){Start-Process -FilePath $AppPath -ArgumentList '--shutdown' -WindowStyle Hidden -Wait}
}
