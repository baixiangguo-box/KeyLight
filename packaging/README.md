# Windows构建

本版本使用 Python 3.12.10 x64，依赖固定在 `requirements-build.txt`。Windows构建需要Inno Setup 6.7.3（`ISCC.exe`）及系统WebView2。命令在仓库根目录执行，推荐使用ASCII构建/部署路径。

```powershell
python -m venv .build/venv
.build/venv/Scripts/python.exe -m pip install -r packaging/requirements-build.txt
.build/venv/Scripts/python.exe -B -m unittest discover -s tests -v
.build/venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --distpath dist --workpath .build/pyinstaller packaging/keylight.spec
.build/venv/Scripts/python.exe packaging/make_docs.py --output .build/release-docs
```

在 `.build/tools/MicrosoftEdgeWebview2Setup.exe` 放置微软原版引导程序： https://go.microsoft.com/fwlink/p/?LinkId=2124703 。构建前用 `Get-AuthenticodeSignature` 确认签名有效且签名者是Microsoft；不要运行未知来源替代物。

```powershell
& 'C:/Program Files (x86)/Inno Setup 6/ISCC.exe' packaging/installer.iss
```

输出 `dist/installer/键光-一键安装-1.7.0-win64.exe`。此版本的公开Release将该文件重命名为ASCII下载名，不改变字节。

打包资源采用白名单，只含UI与设备目录；用户数据和API配置不进入冻结包。教程生成器收集构建环境组件的原始许可。未购买代码签名证书；WebView2引导程序签名与最终产品签名是不同的事。

浏览器测试需要Node.js与Chrome，先启动 `tests/ui_fixture.py --port 8799` 再运行 `tests/browser_check.mjs`。这是假设备/假模型测试。冻结QA `packaging/test_desktop.ps1` 在隔离数据目录、8797端口、`--no-device`模式下测试窗口和创作HTTP链路。`test_installer.ps1` 需要单独QA AppId和安装目录，请阅读脚本；其他live/hardware脚本会使用真实硬件，不能当普通离线CI执行。

当前已知：直接从中文路径运行冻结程序可能出现pythonnet加载差异；默认固定安装路径和ASCII临时部署路径已通过原生测试。其他系统/模型/设备没有由这些检查获得兼容保证。Microsoft引导程序和平台组件可能更新，不保证其他时间构建的安装包与现成Release逐字节一致。
