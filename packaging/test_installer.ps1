$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$buildRoot = (Resolve-Path (Join-Path $projectRoot '.build')).Path
$qaInstall = Join-Path $buildRoot 'qa-installed'
$qaData = Join-Path $buildRoot ('install-qa-data-' + [Guid]::NewGuid().ToString('N'))
$qaLog = Join-Path $buildRoot 'installer-qa.json'
$installer = Join-Path $projectRoot '.build\qa-installer\键光-一键安装-1.7.0-win64.exe'
$registryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{B983DA07-6C25-4FD0-82F7-C7FA9D645A20}_is1'
if (Test-Path -LiteralPath $registryKey) { throw 'Existing QA installation detected; clean it up before rerunning QA.' }
if (-not $qaInstall.StartsWith($buildRoot + '\')) { throw 'QA install path escaped build directory.' }
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut = Join-Path $desktop '键光.lnk'
$shortcutBackup = Join-Path $buildRoot 'desktop-shortcut-before-qa.lnk'
$hadShortcut = Test-Path -LiteralPath $shortcut
if ($hadShortcut) { Copy-Item -LiteralPath $shortcut -Destination $shortcutBackup -Force }
$env:KEYLIGHT_DATA_DIR = $qaData
$env:PATH = $env:SystemRoot + '\System32'
$checks = [System.Collections.Generic.List[string]]::new()
$exe = Join-Path $qaInstall '键光.exe'
try {
    $parameters = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS','/TASKS=""',('/DIR="'+$qaInstall+'"'),('/LOG="'+(Join-Path $buildRoot 'qa-install.log')+'"'))
    $setup = Start-Process -FilePath $installer -ArgumentList $parameters -WindowStyle Hidden -Wait -PassThru
    if ($setup.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $exe)) { throw 'Installer did not succeed.' }
    $checks.Add('Per-user silent installation succeeds without Python in PATH')
    $selfTestResult = Join-Path $buildRoot 'installed-self-test.json'
    $selfTest = Start-Process -FilePath $exe -ArgumentList '--self-test',('"'+$selfTestResult+'"') -WindowStyle Hidden -Wait -PassThru
    if ($selfTest.ExitCode -ne 0) { throw 'Installed self-test failed.' }
    $checks.Add('Installed executable passes bundled-resource/audio/renderer/sharing self-test')
    $service = Start-Process -FilePath $exe -ArgumentList '--no-device','--no-open','--port','8798' -WindowStyle Hidden -PassThru
    $ready = $false
    for($i=0; $i -lt 40; $i++) {
        try { $state = Invoke-RestMethod 'http://127.0.0.1:8798/api/state'; $ready = $true; break } catch { Start-Sleep -Milliseconds 100 }
    }
    if (-not $ready -or $state.build -ne '20261024-creator1') { throw 'Installed server did not start.' }
    $checks.Add('Installed local UI starts on an isolated port without opening devices')
    $runner = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    & $runner -B (Join-Path $projectRoot 'tests\package_check.py') --output (Join-Path $buildRoot 'installed-http.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installed HTTP/share tests failed.' }
    $checks.Add('Installed AI/share save and restore work offline')
    $settingsBefore = (Get-FileHash -LiteralPath (Join-Path $qaData 'settings.json')).Hash
    Start-Process -FilePath $exe -ArgumentList '--shutdown' -WindowStyle Hidden -Wait
    if (-not $service.WaitForExit(10000)) { throw 'Headless QA service did not stop.' }
    $native = Start-Process -FilePath $exe -ArgumentList '--no-device','--port','8798' -PassThru
    for ($i=0; $i -lt 200; $i++) {
        $native.Refresh()
        if ($native.MainWindowTitle -eq '键光' -and $native.MainWindowHandle -ne 0) { break }
        Start-Sleep -Milliseconds 100
    }
    if ($native.MainWindowTitle -ne '键光') { throw 'Installed native window did not open.' }
    $checks.Add('Installed desktop window starts without an external browser')
    $upgrade = Start-Process -FilePath $installer -ArgumentList $parameters -WindowStyle Hidden -Wait -PassThru
    if ($upgrade.ExitCode -ne 0) { throw 'Upgrade installation failed.' }
    if (-not $native.WaitForExit(10000)) { throw 'Upgrade left old GUI process running.' }
    if ((Get-FileHash -LiteralPath (Join-Path $qaData 'settings.json')).Hash -ne $settingsBefore) { throw 'Upgrade changed user data.' }
    $checks.Add('Reinstall gracefully closes the native window and preserves user settings')
} finally {
    if (Test-Path -LiteralPath $exe) {
        Start-Process -FilePath $exe -ArgumentList '--shutdown' -WindowStyle Hidden -Wait
    }
    $uninstaller = Join-Path $qaInstall 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        $removed = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -WindowStyle Hidden -Wait -PassThru
        if ($removed.ExitCode -ne 0) { throw 'QA uninstallation failed.' }
    }
    if ($hadShortcut) { Copy-Item -LiteralPath $shortcutBackup -Destination $shortcut -Force }
}
if (Test-Path -LiteralPath $exe) { throw 'Uninstaller left the installed executable behind.' }
if (Test-Path -LiteralPath $registryKey) { throw 'Uninstaller left its application registration behind.' }
if (-not (Test-Path -LiteralPath (Join-Path $qaData 'presets.json'))) { throw 'Uninstaller deleted user data.' }
$checks.Add('Uninstall removes app and registration while keeping user data')
if ($hadShortcut -and (Get-FileHash -LiteralPath $shortcut).Hash -ne (Get-FileHash -LiteralPath $shortcutBackup).Hash) { throw 'Original desktop shortcut changed.' }
$checks.Add('Original desktop shortcut preserved')
[ordered]@{ok=$true; checks=$checks; admin_requested=$false; real_hardware_opened=$false; python_path_hidden=$true} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $qaLog -Encoding UTF8
Get-Content -LiteralPath $qaLog -Raw -Encoding UTF8
