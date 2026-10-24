# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path(SPECPATH).parent
assets = [(str(root/'studio'/name), 'studio') for name in ('index.html','app.js','splash.js','style.css','icon.svg','icon-mono.ico')]
assets += [(str(root/'kbdrv'/'devices.json'),'kbdrv')]
a = Analysis([str(root/'keylight_launcher.py')], pathex=[str(root)], binaries=[], datas=assets,
             hiddenimports=['pyaudiowpatch','hid','webview.platforms.edgechromium','webview.platforms.winforms'], hookspath=[], runtime_hooks=[],
             excludes=['matplotlib','pandas','scipy','IPython','pytest','tkinter','PIL','cv2','torch',
                       'PyQt5','PyQt6','PySide2','PySide6','qtpy','webview.platforms.qt','webview.platforms.cef'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='键光',debug=False,
          bootloader_ignore_signals=False,strip=False,upx=False,console=False,
          icon=str(root/'studio'/'icon-mono.ico'),version=str(root/'packaging'/'version_info.txt'))
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='KeyLight')
