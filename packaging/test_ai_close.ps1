# Live regression: the user's existing AI effect, exact installed native window,
# no effect edits, no model calls and no onboard write for this software effect.
param([string]$AppPath = '')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if(-not $AppPath){$AppPath=Join-Path $env:LOCALAPPDATA 'Programs\KeyLight\键光.exe'}
$AppPath=(Resolve-Path -LiteralPath $AppPath).Path
$data=Join-Path $env:LOCALAPPDATA 'KeyLight\data'
$saved=Get-Content -LiteralPath (Join-Path $data 'settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($saved.params.effect -ne 'ai' -or $saved.close_behavior -ne 'hold'){
    throw 'This regression requires the existing AI effect and save-on-close preference; no settings changed.'
}
$hashes=@{}
foreach($name in @('settings.json','presets.json','custom_effects.json','ai_config.json','keymap_calibration.json')){
    $path=Join-Path $data $name
    if(Test-Path -LiteralPath $path){$hashes[$name]=(Get-FileHash -LiteralPath $path).Hash}
}
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class KeyLightAICloseQA {
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
}
'@
# This is the actual interactive software; a visible main window is required for WM_CLOSE.
$instance=Start-Process -FilePath $AppPath -WindowStyle Normal -PassThru
try {
    $ready=$false
    for($i=0;$i -lt 150;$i++){
        $instance.Refresh()
        if($instance.HasExited){throw 'Application exited before the native close test.'}
        try{
            $state=Invoke-RestMethod 'http://127.0.0.1:8787/api/state'
            if($state.build -eq '20261024-creator1' -and $state.params.effect -eq 'ai' -and $state.device.connected -and $state.device.frames_sent -gt 10 -and $instance.MainWindowHandle -ne 0){$ready=$true;break}
        }catch{}
        Start-Sleep -Milliseconds 100
    }
    if(-not $ready){throw 'Updated native window did not become ready.'}
    Start-Sleep -Milliseconds 1500
    [KeyLightAICloseQA]::PostMessage($instance.MainWindowHandle,0x10,[IntPtr]::Zero,[IntPtr]::Zero) | Out-Null
    if(-not $instance.WaitForExit(12000) -or $instance.ExitCode -ne 0){throw 'AI close displayed a blocking error or failed to exit.'}
    $reachable=$false
    try{$null=Invoke-RestMethod 'http://127.0.0.1:8787/api/health' -TimeoutSec 1;$reachable=$true}catch{}
    if($reachable){throw 'AI close left a background service running.'}
    foreach($name in $hashes.Keys){
        if((Get-FileHash -LiteralPath (Join-Path $data $name)).Hash -ne $hashes[$name]){throw "Data changed during close: $name"}
    }
    $log=Get-Content -LiteralPath (Join-Path $data '..\logs\runtime.log') -Tail 8 -Encoding UTF8
    if(-not ($log -match '\[exit\] saved_to=computer reason=software_effect')){throw 'Expected local-only AI close receipt was not recorded.'}
    [ordered]@{ok=$true;version=(Get-Item -LiteralPath $AppPath).VersionInfo.ProductVersion;effect='ai';connected=$state.device.connected;title_bar_close=$true;exit_code=$instance.ExitCode;port_closed=$true;user_data_unchanged=$true;model_calls=0} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot '.build\close-review\installed-ai-close.json') -Encoding UTF8
    Get-Content -LiteralPath (Join-Path $projectRoot '.build\close-review\installed-ai-close.json') -Raw -Encoding UTF8
} finally {
    if(-not $instance.HasExited){Start-Process -FilePath $AppPath -ArgumentList '--shutdown' -WindowStyle Hidden -Wait}
}
