"""Windowed entry point for the self-contained Windows release."""
import ctypes
from ctypes import wintypes
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path


def shutdown() -> int:
    from kbdrv.runtime import data_directory
    root = data_directory(Path(__file__).resolve().parent / "studio")
    lock = root / ".studio.lock"
    if not lock.exists():
        return 0
    process = None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        with lock.open("rb") as stream:
            stream.seek(1)
            port = int(stream.read(8).decode("ascii").strip())
        if not 1 <= port <= 65535:
            return 1
        base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(base+"/api/health", timeout=2) as response:
            health = json.load(response)
        if health.get("app") != "AulaStudio":
            return 1
        pid = health.get("pid")
        if isinstance(pid, int) and pid > 0 and pid != os.getpid():
            process = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
        req = urllib.request.Request(base+"/api/shutdown", data=b'{"force":true}', headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5):
            pass
        if process:
            return 0 if kernel.WaitForSingleObject(process, 10000) == 0 else 1
        # Older browser releases did not expose their PID.
        for _ in range(50):
            try:
                with urllib.request.urlopen(base+"/api/health", timeout=.2):
                    pass
            except (OSError, urllib.error.URLError):
                return 0
            time.sleep(.1)
        return 1
    except (OSError, ValueError, urllib.error.URLError):
        return 0
    finally:
        if process:
            kernel.CloseHandle(process)


def main() -> int:
    if "--shutdown" in sys.argv:
        return shutdown()
    from kbdrv.runtime import data_directory
    logs = data_directory(Path(__file__).resolve().parent / "studio").parent / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / "runtime.log"
    if log.exists() and log.stat().st_size > 1024*1024:
        log.write_text("", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log.open("a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout
    try:
        import aula_studio
        return aula_studio.main(desktop=True)
    except Exception as exc:
        traceback.print_exc()
        if "--self-test" not in sys.argv:
            ctypes.windll.user32.MessageBoxW(None, f"键光启动失败：{exc}\n\n请查看日志：\n{log}", "键光", 0x10)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
