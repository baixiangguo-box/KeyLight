"""Embedded Windows desktop window; no external browser fallback."""
from __future__ import annotations

import ctypes
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def activate_existing(port: int) -> bool:
    """Ask the locked instance to restore its own window, including during startup."""
    if not 1 <= port <= 65535:
        return False
    for _ in range(20):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/window/activate",
                data=b"{}", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=.5):
                return True
        except (OSError, urllib.error.URLError):
            time.sleep(.1)
    return False


def run(server, url: str, data: Path, *, before_close=None) -> None:
    import webview
    import winreg

    # pywebview may select MSHTML when WebView2 is absent, even with a preferred
    # backend. Reject that case before creating a window for the modern UI.
    runtime_key = r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    available = False
    for hive, view in ((winreg.HKEY_CURRENT_USER, 0), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY)):
        try:
            with winreg.OpenKey(hive, runtime_key, 0, winreg.KEY_READ | view) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                available |= int(str(version).split(".")[0]) >= 86
        except (OSError, ValueError):
            pass
    if not available:
        raise RuntimeError("缺少 Microsoft WebView2，请连接网络并重新运行键光安装包补齐运行组件")

    # A stable AppUserModelID lets Windows use the application's own taskbar icon.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KeyLight.Desktop")
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    window = webview.create_window("键光", url, width=1320, height=900,
        min_size=(1000, 680), background_color="#060708", text_select=True)
    ready, closed = threading.Event(), threading.Event()
    exit_allowed, saving = threading.Event(), threading.Event()

    def close_requested():
        if exit_allowed.is_set() or before_close is None:
            return True
        if saving.is_set():
            return False
        saving.set()

        def save_and_close():
            try:
                try:
                    if window.events.loaded.is_set():
                        flushed, response = threading.Event(), {}
                        def pending_saved(value):
                            response['value'] = value
                            flushed.set()
                        window.evaluate_js('''(async () => {
                            try { await flushParams(); await flushPaint(); return {ok:true}; }
                            catch (e) { return {ok:false,error:String(e.message || e)}; }
                        })()''', pending_saved)
                        if not flushed.wait(5):
                            raise RuntimeError('界面尚未保存完最新修改，请稍后重试')
                        value = response.get('value')
                        if not isinstance(value, dict) or not value.get('ok'):
                            raise RuntimeError(value.get('error','界面保存失败') if isinstance(value,dict) else '界面保存失败')
                    receipt = before_close()
                    if isinstance(receipt, dict):
                        print(f"[exit] saved_to={receipt.get('saved_to')} reason={receipt.get('reason','verified')}", flush=True)
                except Exception as exc:
                    print(f'[exit] save failed: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
                    # No hidden process or silent substitution for unsupported
                    # effects. The user can keep editing or explicitly exit.
                    answer = ctypes.windll.user32.MessageBoxW(None,
                        f'退出前保存失败：{exc}\n\n仍然退出吗？未保存的修改可能丢失。\n'
                        '退出后软件动态效果停止，键盘将使用之前的内置设置。', '键光', 0x134)
                    if answer != 6:  # IDYES; default button is No
                        return
                exit_allowed.set()
                window.destroy()
            finally:
                saving.clear()
        threading.Thread(target=save_and_close, name='keylight-save-exit', daemon=True).start()
        return False

    window.events.closing += close_requested

    def activate():
        if not ready.wait(3) or closed.is_set():
            return False
        window.restore()
        window.show()
        return True

    server.window_activate = activate
    window.events.shown += ready.set
    window.events.closed += closed.set
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1},
                              name="keylight-server", daemon=True)
    worker.start()

    def close_when_service_stops():
        worker.join()
        if ready.wait(10) and not closed.is_set():
            exit_allowed.set()
            window.destroy()

    threading.Thread(target=close_when_service_stops, name="keylight-window-close", daemon=True).start()
    try:
        # EdgeChromium is an embedded WebView2 control, not a browser tab.
        # Runtime detection above prevents the obsolete MSHTML fallback.
        webview.start(gui="edgechromium", private_mode=False,
                      storage_path=str(data.parent / "webview"))
    finally:
        server.window_activate = None
        if worker.is_alive():
            server.shutdown()
        worker.join(timeout=5)
        if worker.is_alive():
            raise RuntimeError("窗口已关闭，但本机服务未能退出")
