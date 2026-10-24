#ifndef StageDir
  #define StageDir "..\dist\KeyLight"
#endif
#ifndef DocsDir
  #define DocsDir "..\.build\release-docs"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif
#ifndef KeyLightAppId
  #define KeyLightAppId "{{27AC3F1D-9233-4B08-AEDB-61F68198C313}"
#endif
#ifndef KeyLightGroupName
  #define KeyLightGroupName "键光"
#endif

[Setup]
AppId={#KeyLightAppId}
AppName=键光
AppVersion=1.7.0
AppPublisher=KeyLight Project（非狼蛛官方）
DefaultDirName={localappdata}\Programs\KeyLight
DefaultGroupName={#KeyLightGroupName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir={#OutputDir}
OutputBaseFilename=键光-一键安装-1.7.0-win64
SetupIconFile=..\studio\icon-mono.ico
UninstallDisplayIcon={app}\键光.exe
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableStartupPrompt=yes
ShowLanguageDialog=no
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no
VersionInfoDescription=键光一键安装包
VersionInfoProductName=键光
VersionInfoVersion=1.7.0.0
UninstallDisplayName=键光

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"

[Messages]
ReadyLabel1=即将安装键光 1.7.0 桌面版（Windows 64 位）。%n独立窗口运行，无需打开浏览器。已实测 WIN 60 HE。
ReadyLabel2b=已内置 Python。若缺少 WebView2，将自动从微软下载运行组件（需要联网）。点击“安装”即可完成。
FinishedLabel=键光已安装完成。已实测型号：WIN 60 HE；WIN 68 HE 尚未实测，其他型号暂未适配。使用说明可在开始菜单中打开。

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: checkedonce

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DocsDir}\*"; DestDir: "{app}\帮助"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\.build\tools\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[Icons]
Name: "{userdesktop}\键光"; Filename: "{app}\键光.exe"; Tasks: desktopicon
Name: "{group}\键光"; Filename: "{app}\键光.exe"
Name: "{group}\使用教程"; Filename: "{app}\帮助\使用教程.html"
Name: "{group}\卸载键光"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\键光.exe"; Description: "立即打开键光"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\键光.exe"; Parameters: "--shutdown"; RunOnceId: "StopKeyLight"; Flags: runhidden waituntilterminated skipifdoesntexist

[Code]
function HasWebView2: Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := RegQueryStringValue(HKCU, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
  if not Result then
    Result := RegQueryStringValue(HKLM32, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if not HasWebView2 then
  begin
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := 'WebView2 运行组件无法启动，请检查网络后重试。'
    else if not HasWebView2 then
      Result := 'WebView2 运行组件未能安装，请连接网络后重试。';
    if Result <> '' then Exit;
  end;
  if FileExists(ExpandConstant('{app}\键光.exe')) then
  begin
    if not Exec(ExpandConstant('{app}\键光.exe'), '--shutdown', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      Result := '旧版键光无法正常退出，请先在界面中点击“退出服务”，然后重试安装。'
    else if ExitCode <> 0 then
      Result := '无法确认旧版服务已退出，请在旧版界面中点击“退出服务”后重试。';
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := PageID = wpSelectTasks;
end;
