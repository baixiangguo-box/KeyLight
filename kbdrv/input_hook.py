"""Global keyboard input with exact model-specific physical-key mapping."""

from __future__ import annotations

import ctypes
import threading
import time
from collections import deque
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_KEYUP, WM_SYSKEYUP = 0x0101, 0x0105
WM_QUIT = 0x0012
PM_REMOVE = 0x0001

LED_ROWS = 5
LED_COLS = 22
ROW_OFFSET = 1
KEY_UNITS = 15.0  # ANSI 60% keyboard is 15 units wide


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


class POINT(ctypes.Structure):
    _fields_ = [("x", w.LONG), ("y", w.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", w.HWND), ("message", w.UINT), ("wParam", w.WPARAM),
                ("lParam", w.LPARAM), ("time", w.DWORD), ("pt", POINT)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, w.WPARAM, w.LPARAM)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, w.DWORD]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, w.WPARAM, w.LPARAM]
user32.UnhookWindowsHookEx.restype = w.BOOL
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.PeekMessageW.restype = w.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), w.HWND, w.UINT, w.UINT, w.UINT]
user32.PostThreadMessageW.restype = w.BOOL
user32.PostThreadMessageW.argtypes = [w.DWORD, w.UINT, w.WPARAM, w.LPARAM]

# Compatibility helpers now use the exact WIN60 firmware map.
from .keymap import KeyMap, DEFAULT_MAP
_KEY_TABLE = DEFAULT_MAP.by_vk


def vk_to_cell(vk: int) -> tuple[int, int] | None:
    return DEFAULT_MAP.cells.get(vk)


def vk_to_led(vk: int) -> int | None:
    entry = DEFAULT_MAP.by_vk.get(vk)
    return entry["led"] if entry else None


class KeyHook:
    """Runs a low-level keyboard hook on its own thread."""

    def __init__(self, max_events: int = 64):
        self.keymap = KeyMap()
        self.debug_enabled = False
        self.debug_last = None
        self.debug_sequence = 0
        self.events: deque[tuple[int, float]] = deque(maxlen=max_events)
        self.lock = threading.Lock()
        self._pressed: set[int] = set()
        self._times: dict[int, float] = {}
        self._counts: dict[int, int] = {}
        self._released: dict[int, float] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._hook = None
        self._proc = HOOKPROC(self._callback)
        self.thread_id = 0
        self.error: str | None = None
        self.last_vk: int | None = None
        self.count = 0

    # ------------------------------------------------------------------
    def _callback(self, n_code, w_param, l_param):
        try:
            if n_code >= 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                raw_vk, scan = int(info.vkCode), int(info.scanCode)
                extended = bool(info.flags & 1)
                with self.lock:
                    entry = self.keymap.resolve(raw_vk,scan,extended)
                    is_up = w_param in (WM_KEYUP, WM_SYSKEYUP)
                    vk = entry["vk"] if entry else None
                    repeat = vk in self._pressed and not is_up
                    if self.debug_enabled:
                        self.debug_sequence += 1
                        self.debug_last = {"sequence":self.debug_sequence,"vk":raw_vk,"scan_code":scan,
                            "extended":extended,"injected":bool(info.flags & 0x10),"canonical_vk":vk,
                            "code":entry["code"] if entry else None,"led":entry["led"] if entry else None,
                            "label":entry["label"] if entry else "当前配列没有这个系统键",
                            "action":"松开" if is_up else "长按重复" if repeat else "按下"}
                    if entry is not None:
                        led = entry["led"]
                        if is_up:
                            if vk in self._pressed:
                                self._released[vk] = time.time()
                            self._pressed.discard(vk)
                        elif not repeat:
                            self._pressed.add(vk)
                            now = time.time()
                            self._times[vk] = now
                            self._counts[vk] = self._counts.get(vk, 0) + 1
                            self.events.append((led, now))
                            self.count += 1
                            self.last_vk = vk
        except Exception:  # noqa: BLE001 - never break the hook chain
            pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        with self.lock:
            self._pressed.clear()
            self.events.clear()
            self._times.clear()
            self._counts.clear()
            self._released.clear()
            self.last_vk = None
        self._thread = threading.Thread(target=self._run, name="key-hook", daemon=True)
        self._thread.start()
        time.sleep(0.15)
        return self._hook is not None

    def _run(self) -> None:
        self.thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            self.error = f"SetWindowsHookEx failed: {ctypes.get_last_error()}"
            return
        msg = MSG()
        while not self._stop.is_set():
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    self._stop.set()
                    break
            time.sleep(0.004)
        try:
            user32.UnhookWindowsHookEx(self._hook)
        except Exception:  # noqa: BLE001
            pass
        self._hook = None

    def stop(self) -> None:
        self._stop.set()
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=1.0)
        with self.lock:
            self._pressed.clear()
            self.events.clear()
            self._times.clear()
            self._counts.clear()
            self._released.clear()
            self.last_vk = None

    def snapshot(self) -> dict:
        with self.lock:
            now = time.time()
            return {"held": set(self._pressed), "ages": {vk:max(0,now-ts) for vk,ts in self._times.items()},
                    "counts": dict(self._counts), "last_vk": self.last_vk,
                    "releases": {vk:max(0,now-ts) for vk,ts in self._released.items()},
                    "key_cells":self.keymap.cells}

    def configure_map(self, keymap):
        with self.lock:
            self.keymap = keymap
            self._pressed.clear()
            self.events.clear()
            self._times.clear()
            self._released.clear()
            self._counts.clear()
            self.last_vk = None
            self.debug_last = None

    def debug_status(self):
        with self.lock:
            return {"enabled":self.debug_enabled,"last":dict(self.debug_last) if self.debug_last else None}

    def drain(self) -> list[tuple[int, float]]:
        with self.lock:
            items = list(self.events)
            self.events.clear()
        return items
