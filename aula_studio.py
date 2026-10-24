"""AULA 键光：本机 HTTP 控制台与 RAM 灯光推流。"""
from __future__ import annotations

import argparse
import copy
import json
import math
import mimetypes
import os
import sys
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kbdrv import ai as ai_effects, effects, validation as valid, sharing
from kbdrv.audio import AudioAnalyzer
from kbdrv.device import Keyboard, UnsupportedKeyboard
from kbdrv.expr import compile_expression
from kbdrv.input_hook import KeyHook
from kbdrv.keymap import KeyMap
from kbdrv.layout import LED_COLUMNS, LED_COUNT, LED_ROWS
from kbdrv.storage import LOCK as STORE_LOCK, read_json as _read_json, write_json as _write_json
from kbdrv.runtime import data_directory, self_test
from kbdrv import onboard, creator

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "studio"
DATA = data_directory(WEB)
DATA.mkdir(parents=True, exist_ok=True)
# Legacy locations stay compatible; HTTP serves an explicit asset allowlist only.
PRESETS, CUSTOM = DATA / "presets.json", DATA / "custom_effects.json"
AI_CONFIG, SETTINGS = DATA / "ai_config.json", DATA / "settings.json"
KEYMAP_CONFIG = DATA / "keymap_calibration.json"
DEFAULT_PARAMS, EFFECTS = valid.DEFAULT_PARAMS, valid.EFFECTS
FPS = 45.0
BUILD = "20261024-creator1"


class Studio:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.io_lock = threading.RLock()
        self.settings_lock = threading.RLock()
        self.input_lock = threading.Lock()
        self.ai_lock = threading.Lock()
        self.params = copy.deepcopy(DEFAULT_PARAMS)
        self.paint = [[0, 0, 0] for _ in range(LED_COUNT)]
        self.ai_spec, self.ai_expr, self.ai_history = None, None, []
        self.ai_versions = []
        self.ai_new = False
        self.close_behavior = "hold"
        self.control_enabled = True
        self.warning = None
        self.onboard_saved = None
        saved = _read_json(SETTINGS, {})
        try:
            snapshot, expr = valid.snapshot(saved)
            self.params, self.paint = snapshot["params"], snapshot["paint"]
            self.ai_spec, self.ai_expr = snapshot["ai_spec"], expr
            mode = saved.get("close_behavior", "hold")
            if mode not in ("hold", "release"):
                raise ValueError("关闭策略无效")
            self.close_behavior = mode
            self.control_enabled = saved.get("control", "software") != "firmware"
        except (ValueError, TypeError, KeyError, ai_effects.AIError) as exc:
            self.params = copy.deepcopy(DEFAULT_PARAMS)
            self.ai_spec, self.ai_expr = None, None
            self.warning = f"上次设置无法完整恢复，已使用默认灯效：{exc}"
        # Conversation data is local only, bounded, and excluded from share codes.
        saved = saved if isinstance(saved, dict) else {}
        self.ai_history = ai_effects.clean_history(saved.get("ai_history"))
        self.ai_new = saved.get("ai_new") is True
        self.creator=creator.Session(saved.get("creator"),draft=None if self.ai_new else self.ai_spec,
                                     history=self.ai_history,on_save=self.save_settings)
        versions = saved.get("ai_versions", [])
        if isinstance(versions, list):
            for version in versions[-8:]:
                try:
                    snapshot, _ = valid.snapshot(version["snapshot"])
                    self.ai_versions.append({"snapshot": snapshot,
                        "history": ai_effects.clean_history(version.get("history")),
                        "new": version.get("new") is True})
                except (ValueError, TypeError, KeyError):
                    continue
        self.frame = bytes(LED_COUNT * 3)  # Last successfully written frame only.
        self.keyboard = None
        self.error = None
        self.connected = False
        self.frames = 0
        self.revision = 0
        self.model_info = None
        self.rows, self.cols, self.row_offset = LED_ROWS, LED_COLUMNS, 1
        self.ripples = []
        self.audio_center = None
        self._stop = threading.Event()
        self._thread = None
        self._next_connect = 0.0
        self._backoff = 1.0
        self._sent_times = deque(maxlen=90)
        self.audio = AudioAnalyzer()
        self.audio_device = None
        self.audio_gain = 1.4
        self._audio_attempted = False
        self.hook = KeyHook()
        self.keymap = self.hook.keymap
        self.keymap_revision = 0
        self.keymap_debug = False
        self.keymap_single = False
        self.keymap_deadline = 0.0
        self.keymap_probe = None
        self.keymap_probe_until = 0.0

    def connect(self) -> None:
        with self.io_lock:
            try:
                keyboard = Keyboard()
                info = keyboard.info or {}
                calibration = _read_json(KEYMAP_CONFIG,{})
                with self.lock:
                    self.keyboard, self.connected, self.error = keyboard, True, None
                    self.rows, self.cols, self.row_offset = keyboard.rows, keyboard.cols, keyboard.row_offset
                    self.model_info = {"name": info.get("model") or info.get("product"),
                        "family": info.get("family"), "family_label": info.get("family_label"),
                        "supported": True, "id": f"{info.get('vid',0):04X}:{info.get('pid',0):04X}"}
                    self.model_info["hardware_verified"] = bool(info.get("hardware_verified"))
                    model_name = info.get("mapping_model") or self.model_info["name"]
                    base_map = KeyMap(model_name)
                    try:
                        self.keymap = KeyMap(model_name,calibration.get(base_map.profile,{}) if isinstance(calibration,dict) else {})
                    except ValueError:
                        self.keymap = base_map
                        self.warning = "上次键灯校准无效，已恢复厂商逐键表。"
                    self.hook.configure_map(self.keymap)
                    self.keymap_revision += 1
                    if self.model_info["name"] == "WIN 68 HE" and not self.warning:
                        self.warning = "WIN 68 HE 使用型号专属厂商键位表，尚未在本机实物验证。"
                    self.revision += 1
                self._backoff = 1
            except UnsupportedKeyboard as exc:
                with self.lock:
                    self.keyboard, self.connected, self.error = None, False, str(exc)
                    self.model_info = {**exc.model.as_dict(), "supported": False} if exc.model else None
            except OSError as exc:
                with self.lock:
                    self.keyboard, self.connected, self.error = None, False, str(exc)
            finally:
                self._next_connect = time.perf_counter() + self._backoff
                if not self.connected:
                    self._backoff = min(10, self._backoff * 2)

    def info(self) -> dict:
        with self.lock:
            info = (self.keyboard.info if self.keyboard else {}) or {}
            observed = 0.0
            if len(self._sent_times) > 1 and time.perf_counter() - self._sent_times[-1] < 1:
                observed = (len(self._sent_times)-1) / max(0.001, self._sent_times[-1]-self._sent_times[0])
            return {"connected": self.connected, "error": self.error, "warning": self.warning,
                "name": info.get("product") or (self.model_info or {}).get("name") or "AULA",
                "vid": f"{info.get('vid',0):04X}", "pid": f"{info.get('pid',0):04X}",
                "rows": self.rows, "cols": self.cols, "row_offset": self.row_offset,
                "fps": FPS, "observed_fps": round(observed, 1), "model": self.model_info,
                "control": "software" if self.control_enabled else "firmware",
                "frame_kind": "last_sent", "frames_sent": self.frames,
                "frame_max": max(self.frame), "revision": self.revision,
                "render_alive": bool(self._thread and self._thread.is_alive()),
                "hook": {"started": bool(self.hook._hook), "error": self.hook.error,
                         "events": self.hook.count, "last_vk": self.hook.last_vk,
                         "ripples": len(self.ripples)},
                "keymap_revision":self.keymap_revision, "keymap_profile":self.keymap.profile,
                "keymap_debug":self.hook.debug_status() if self.keymap_debug else {"enabled":False}}

    def mapping_status(self):
        with self.lock:
            data = self.keymap.describe()
            frame = self.frame
            data.update(revision=self.keymap_revision,debug=self.keymap_debug,single_key=self.keymap_single,
                        event=self.hook.debug_status()["last"],connected=self.connected,
                        control="software" if self.control_enabled else "firmware",
                        frame_kind="last_sent",sent_leds=[i for i in range(LED_COUNT) if max(frame[i*3:i*3+3])>0])
            return data

    def configure_mapping_debug(self, enabled, single=False):
        if type(enabled) is not bool or type(single) is not bool:
            raise ValueError("调试开关必须是布尔值")
        with self.lock:
            self.keymap_debug, self.keymap_single = enabled, enabled and single
            self.keymap_deadline = time.perf_counter()+300 if enabled else 0
            self.keymap_probe = None
            with self.hook.lock:
                self.hook.debug_enabled = enabled
                self.hook.debug_last = None

    def calibrate_mapping(self, body):
        # io -> store, then state: never wait for STORE_LOCK while holding state.
        with self.io_lock:
            with self.lock:
                if not self.keymap.profile:
                    raise ValueError("当前型号没有可校准键位表")
                new_map = KeyMap(self.keymap.model) if body.get("reset") is True else self.keymap.swap(body.get("vk"),body.get("led"))
            with STORE_LOCK:
                config = _read_json(KEYMAP_CONFIG,{})
                config = config if isinstance(config,dict) else {}
                config[new_map.profile] = {str(k):v for k,v in new_map.overrides.items()}
                _write_json(KEYMAP_CONFIG,config)
            with self.lock:
                self.keymap = new_map
                self.hook.configure_map(new_map)
                self.keymap_revision += 1
                self.revision += 1
        return self.mapping_status()

    def current(self) -> dict:
        with self.lock:
            return copy.deepcopy({"version": 2, "params": self.params, "paint": self.paint,
                                  "ai_spec": self.ai_spec})

    def save_settings(self) -> None:
        # Lock order is settings -> state; never hold state while waiting for I/O.
        with self.settings_lock:
            with self.lock:
                payload = {**self.current(), "close_behavior": self.close_behavior,
                           "control": "software" if self.control_enabled else "firmware",
                           "ai_history": copy.deepcopy(self.ai_history), "ai_new": self.ai_new,
                           "ai_versions": copy.deepcopy(self.ai_versions),"creator":self.creator.export()}
            _write_json(SETTINGS, payload)

    def apply_snapshot(self, value: dict) -> None:
        snapshot, expr = valid.snapshot(value)
        with self.lock:
            self.params, self.paint = snapshot["params"], snapshot["paint"]
            self.ai_spec, self.ai_expr = snapshot["ai_spec"], expr
            self.ai_history, self.ai_versions, self.ai_new = [], [], False
            self.control_enabled = True
            self.revision += 1
        self.save_settings()

    def update_params(self, patch: dict) -> None:
        with self.lock:
            checked = valid.params(patch, self.params)
            if checked["effect"] == "ai" and self.ai_expr is None:
                raise ValueError("请先生成或应用一份 AI 光效")
            self.params = checked
            if self.ai_spec and (checked["effect"] == "ai" or
                    checked["effect"] == self.ai_spec.get("effect")):
                self.ai_spec.update({k: checked[k] for k in DEFAULT_PARAMS
                                    if k != "effect" or self.ai_spec["kind"] == "preset"})
            self.control_enabled = True
            self.revision += 1
        self.save_settings()

    def apply_spec(self, value: dict, expected_revision=None, conversation=None) -> None:
        spec, expr = valid.spec(value)
        with self.lock:
            if expected_revision is not None and (self.revision != expected_revision or self._stop.is_set()):
                raise RequestError("生成期间灯效已改变，本次结果未覆盖当前灯效，请重新提交", 409)
            patch = {k: spec[k] for k in DEFAULT_PARAMS if k in spec}
            patch["effect"] = "ai" if expr else spec["effect"]
            checked = valid.params(patch, self.params)
            self.ai_spec, self.ai_expr, self.params = spec, expr, checked
            if conversation is None:
                self.ai_history, self.ai_versions, self.ai_new = [], [], False
            else:
                self.ai_history, self.ai_versions = conversation
                self.ai_new = False
            self.control_enabled = True
            self.revision += 1
        self.save_settings()

    def undo_ai(self) -> None:
        with self.lock:
            if not self.ai_versions:
                raise ValueError("还没有可以撤回的修改")
            version = self.ai_versions[-1]
            snapshot, expr = valid.snapshot(version["snapshot"])
            self.params, self.paint = snapshot["params"], snapshot["paint"]
            self.ai_spec, self.ai_expr = snapshot["ai_spec"], expr
            self.ai_history, self.ai_new = version["history"], version["new"]
            self.ai_versions = self.ai_versions[:-1]
            self.control_enabled = True
            self.revision += 1
        self.save_settings()

    def audio_status(self) -> dict:
        reactive = self.audio.reactive_snapshot()
        return {"available": AudioAnalyzer.available(), "active": self.audio.active,
                "device": self.audio.device_name, "gain": self.audio_gain, "error": self.audio.error,
                "pulse": reactive["pulse"], "energy": reactive["energy"],
                "center": list(self.audio_center) if self.audio_center is not None else None,
                "beat_count": reactive["beat_count"]}

    def start_audio(self, device_index=None) -> None:
        self.stop_audio()
        self.audio = AudioAnalyzer()
        self.audio.set_gain(self.audio_gain)
        self._audio_attempted = True
        if self.audio.open(device_index):
            self.audio_device = self.audio.device_index
            self.audio.start()

    def stop_audio(self) -> None:
        self.audio.stop()

    def _sync_inputs(self, effect: str | None) -> None:
        with self.input_lock:
            with self.lock:
                radial_audio = effect == "audio" and self.params["audio_style"] == "radial"
                program = self.ai_expr if effect == "ai" else None
                needs_keys = bool(getattr(program, "needs_keys", False))
                needs_audio = bool(getattr(program, "needs_audio", False))
            if effect == "ripple" or radial_audio or needs_keys or self.keymap_debug:
                if not self.hook._thread or not self.hook._thread.is_alive():
                    self.hook.start()
            elif self.hook._thread and self.hook._thread.is_alive():
                self.hook.stop()
                self.ripples.clear()
                self.audio_center = None
            if (effect == "audio" or needs_audio) and not self._audio_attempted:
                self.start_audio(self.audio_device)
            elif effect != "audio" and not needs_audio and self._audio_attempted:
                self.stop_audio()
                self._audio_attempted = False

    def ai_config(self, masked=True) -> dict:
        cfg = _read_json(AI_CONFIG, {})
        key = str(cfg.get("api_key") or "")
        return {"base_url": cfg.get("base_url") or ai_effects.DEFAULT_BASE,
                "model": cfg.get("model") or ai_effects.DEFAULT_MODEL,
                "api_key": ("•" * 8 + key[-4:]) if key and masked else ("" if masked else key),
                "has_key": bool(key)}

    def raw_ai_config(self) -> dict:
        return _read_json(AI_CONFIG, {})

    def save_ai_config(self, body: dict) -> None:
        with STORE_LOCK:
            cfg = _read_json(AI_CONFIG, {})
            for key in ("api_key", "base_url", "model"):
                if key in body and body[key]:
                    if not isinstance(body[key], str) or len(body[key]) > 2000:
                        raise ValueError("接口配置格式错误")
                    cfg[key] = body[key].strip()
            parsed = urlsplit(cfg.get("base_url") or ai_effects.DEFAULT_BASE)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
                raise ValueError("接口地址必须是有效的 HTTP(S) 地址")
            _write_json(AI_CONFIG, cfg)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.connect()
        self._thread = threading.Thread(target=self._run, name="frame-loop", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        t0 = time.perf_counter()
        while not self._stop.is_set():
            started = time.perf_counter()
            try:
                if self.keymap_debug and started > self.keymap_deadline:
                    self.configure_mapping_debug(False)
                if not self.connected and started >= self._next_connect:
                    self.connect()
                with self.lock:
                    enabled = self.control_enabled and self.connected
                    params, expr, revision = dict(self.params), self.ai_expr, self.revision
                    paint = [tuple(c) for c in self.paint] if params["effect"] == "paint" else None
                self._sync_inputs(params["effect"] if enabled else None)
                if enabled:
                    speed = valid.number(params["speed"], 0.05, 3, "速度")
                    now = time.time()
                    if params["effect"] == "ripple" or (params["effect"] == "audio" and params["audio_style"] == "radial"):
                        for led, ts in self.hook.drain():
                            col, row = led % LED_COLUMNS, led // LED_COLUMNS - self.row_offset
                            if params["effect"] == "ripple":
                                self.ripples.append((col, row, ts))
                            else:
                                self.audio_center = (col, row)
                    self.ripples = [r for r in self.ripples if now-r[2] < effects.RIPPLE_LIFETIME/speed]
                    reactive = self.audio.reactive_snapshot() if self.audio.active else None
                    frame = effects.render(params["effect"], started-t0,
                        color=tuple(params["color"]), color2=tuple(params["color2"]), speed=speed,
                        brightness=params["brightness"], paint=paint, expr=expr,
                        key_state=self.hook.snapshot() if getattr(expr,"needs_keys",False) else {"key_cells":self.keymap.cells},
                        ripples=[(c,r,now-ts) for c,r,ts in self.ripples],
                        levels=reactive["levels"] if reactive else None,
                        audio_pulse=reactive["pulse"] if reactive else 0,
                        audio_energy=reactive["energy"] if reactive else 0,
                        audio_beat=reactive["beat_count"] if reactive else 0,
                        audio_style=params["audio_style"], audio_center=self.audio_center,
                        rows=self.rows, row_offset=self.row_offset)
                    if self.keymap_debug and self.keymap_single:
                        frame = [(0,0,0)]*LED_COUNT
                        held = self.hook.snapshot()["held"]
                        for vk in held:
                            entry = self.keymap.by_vk.get(vk)
                            if entry:
                                frame[entry["led"]] = (140,140,140)
                        if self.keymap_probe is not None and started < self.keymap_probe_until:
                            frame[self.keymap_probe] = (140,140,140)
                    raw = bytes(int(v) for rgb in frame for v in rgb)
                    with self.io_lock:
                        with self.lock:
                            send = self.control_enabled and self.connected and self.revision == revision and not self._stop.is_set()
                        if send:
                            try:
                                self.keyboard.send_frame(frame)
                            except Exception:
                                with self.lock:
                                    self.connected = False
                                    self.revision += 1
                                self.keyboard.close()
                                with self.lock:
                                    self.keyboard = None
                                self._next_connect = time.perf_counter() + 1
                                raise
                            with self.lock:
                                self.frame, self.error = raw, None
                                self.frames += 1
                                self._sent_times.append(time.perf_counter())
            except Exception as exc:
                with self.lock:
                    self.error = f"{type(exc).__name__}: {exc}"
                self._stop.wait(0.2)
            # Use QPC (perf_counter), not the coarse Windows monotonic clock.
            # Windows Event.wait uses coarse timer ticks; time.sleep has the
            # high-resolution wait needed for the remaining ~5ms of a 45fps frame.
            time.sleep(max(0, 1/FPS-(time.perf_counter()-started)))

    def release(self) -> None:
        with self.io_lock:
            if not self.keyboard or not self.connected:
                raise ValueError("键盘未连接，无法交还控制权")
            with self.lock:
                self.control_enabled = False
                self.revision += 1
            try:
                if self.keyboard and self.connected:
                    self.keyboard.release()
                    with self.lock:
                        self.error = None
            except Exception as exc:
                with self.lock:
                    self.error = f"交还失败：{exc}"
                raise
        self.save_settings()

    def save_onboard(self) -> dict:
        with self.io_lock:
            with self.lock:
                if not self.keyboard or not self.connected:
                    raise ValueError('键盘未连接，无法保存到键盘')
                request = onboard.plan(self.params)
                if not request['supported']:
                    raise ValueError(request['message'])
                keyboard, paint = self.keyboard, copy.deepcopy(self.paint)
                previous = self.control_enabled
                self.control_enabled = False
                self.revision += 1
                saving_revision = self.revision
            try:
                result = keyboard.save_onboard(request, paint)
                with self.lock:
                    if self.revision != saving_revision:
                        raise ValueError('保存期间设置发生变化，请再次保存最新设置')
                    self.onboard_saved = result
                    self.error = None
            except Exception:
                with self.lock:
                    if self.revision == saving_revision:
                        self.control_enabled = previous
                        self.revision += 1
                raise
        self.save_settings()
        return result

    def prepare_exit(self) -> dict:
        with self.lock:
            needs_save = self.close_behavior == 'hold' and self.control_enabled and self.connected
            supported = onboard.plan(self.params)['supported'] if needs_save else False
        # Computer persistence is independent of the firmware's capabilities.
        # Unsupported software effects are a normal local-only exit, not a
        # failed hardware write. Explicit Save to Keyboard remains strict.
        self.save_settings()
        if needs_save and supported:
            return {**self.save_onboard(), 'saved_to':'keyboard'}
        message = ('设置已保存到电脑。此效果需要软件运行，退出后键盘使用之前的内置灯效。'
                   if needs_save else '设置已保存到电脑，软件已退出。')
        return {'saved_to':'computer', 'verified':False,
                'reason':'software_effect' if needs_save else 'local', 'message':message}

    def shutdown(self) -> None:
        self.creator.cancel(save=False)
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise RuntimeError("推帧线程仍在退出，未关闭正在使用的设备")
        with self.input_lock:
            self.hook.stop()
            self.stop_audio()
        with self.io_lock:
            if self.keyboard:
                if self.close_behavior == "release" and self.control_enabled:
                    self.keyboard.release()
                self.keyboard.close()
                with self.lock:
                    self.keyboard = None
                    self.connected = False


STUDIO = Studio()


def _preview_frame(body: dict) -> str:
    checked = valid.params({k: body[k] for k in DEFAULT_PARAMS if k in body},
                           {**DEFAULT_PARAMS, "effect": "static"})
    src = body.get("expression")
    expr = compile_expression(src) if src else None
    if body.get("spec") is not None:
        spec, expr = valid.spec(body["spec"])
        checked = valid.params({k:spec[k] for k in DEFAULT_PARAMS if k in spec}, checked)
        checked["effect"] = "ai" if expr else spec["effect"]
    if expr:
        checked["effect"] = "ai"
    if checked["effect"] == "ai" and expr is None:
        raise ValueError("此 AI 预设缺少表达式")
    pixels = valid.paint(body["paint"]) if body.get("paint") is not None else None
    t = valid.number(body.get("t", 1.2), 0, 1e6, "预览时间")
    audio = body.get("audio",{})
    if not isinstance(audio,dict):
        raise ValueError("预览音频须为对象")
    from kbdrv.program import validate_checks
    validate_checks([{"keys":[],"expect":[],"others_off":True,"audio":audio}])
    keys = body.get("keys", [])
    if not isinstance(keys, list) or len(keys)>64:
        raise ValueError("预览按键格式错误")
    key_state = {"held":set(), "ages":{}, "counts":{}, "last_vk":None,"releases":{},"key_cells":STUDIO.keymap.cells}
    for key in keys:
        if not isinstance(key,dict):
            raise ValueError("预览按键必须是对象")
        vk = int(valid.number(key.get("vk"), 0,255,"键码"))
        key_state["ages"][vk] = valid.number(key.get("age",0),0,1e6,"按键时间")
        key_state["counts"][vk] = int(valid.number(key.get("count",1),0,1e6,"按下次数"))
        if "release_age" in key:
            key_state["releases"][vk] = valid.number(key["release_age"],0,1e6,"松开时间")
        if key.get("held") is True:
            key_state["held"].add(vk)
        last = key_state["last_vk"]
        if last is None or key_state["ages"][vk] <= key_state["ages"][last]:
            key_state["last_vk"] = vk
    frame = effects.render(checked["effect"], t, color=checked["color"], color2=checked["color2"],
        speed=checked["speed"], brightness=checked["brightness"], paint=pixels, expr=expr,
        audio_style=checked["audio_style"],
        levels=audio.get("levels"),audio_pulse=audio.get("pulse",0),
        audio_energy=audio.get("energy",0),audio_beat=audio.get("beat",0),
        key_state=key_state,
        rows=STUDIO.rows, row_offset=STUDIO.row_offset)
    return bytes(int(v) for rgb in frame for v in rgb).hex()


_audio_devices_cache = (0.0, [])


def state() -> dict:
    global _audio_devices_cache
    # A normal page load must not initialize PortAudio. Device discovery is
    # available explicitly via /api/audio/devices; unused audio stays asleep.
    with STUDIO.lock:
        current = STUDIO.current()
        result = {"build": BUILD, "device": STUDIO.info(), "params": current["params"],
            "keymap":{**STUDIO.keymap.describe(),"revision":STUDIO.keymap_revision},
            "paint": current["paint"], "ai_spec": current["ai_spec"],
            "ai_history": copy.deepcopy(STUDIO.ai_history), "effects": EFFECTS,
            "ai_new": STUDIO.ai_new, "ai_undo": len(STUDIO.ai_versions),"creator":STUDIO.creator.view(),
            "settings": {"close_behavior": STUDIO.close_behavior},
            "onboard": {**onboard.plan(current['params']), 'effects':list(onboard.MODES),
                        'saved':copy.deepcopy(STUDIO.onboard_saved)},
            "audio": {**STUDIO.audio_status(), "devices": _audio_devices_cache[1]}}
    result.update(presets=_read_json(PRESETS, []), custom=_read_json(CUSTOM, []), ai=STUDIO.ai_config())
    return result


class RequestError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server_version = "AulaStudio/1.2"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_args):
        pass

    def _json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _check_request(self):
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host", "").lower() not in allowed:
            raise RequestError("仅允许本机地址访问", 403)
        origin = self.headers.get("Origin")
        if origin and origin.lower() not in {f"http://{host}" for host in allowed}:
            raise RequestError("拒绝跨站请求", 403)
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise RequestError("拒绝跨站请求", 403)

    def _static(self, rel):
        if rel not in {"index.html", "app.js", "splash.js", "style.css", "icon.svg"}:
            raise RequestError("文件不存在", 404)
        path = (WEB / rel).resolve()
        if not path.is_relative_to(WEB.resolve()) or not path.is_file():
            raise RequestError("文件不存在", 404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(rel)[0] or "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise RequestError("不支持分块请求")
        if self.headers.get_content_type() != "application/json":
            raise RequestError("请使用 application/json", 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise RequestError("请求长度无效") from None
        if not 0 < length <= 65536:
            raise RequestError("请求为空或超过 64KB", 413)
        data = self.rfile.read(length)
        if len(data) != length:
            raise RequestError("请求未完整接收")
        try:
            body = json.loads(data.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("不支持非有限数值")))
        except (ValueError, UnicodeError, RecursionError):
            raise RequestError("JSON 格式错误") from None
        if not isinstance(body, dict):
            raise RequestError("请求必须是 JSON 对象")
        return body

    def _dispatch(self, method):
        try:
            self._check_request()
            return method()
        except RequestError as exc:
            self._json({"ok": False, "error": str(exc)}, exc.status)
        except (ValueError, TypeError, KeyError, ai_effects.AIError) as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except OSError:
            self._json({"ok": False, "error": "设备操作或本地文件写入失败，请检查设备与目录权限"}, 500)
        except Exception:
            self._json({"ok": False, "error": "操作失败，请查看服务日志"}, 500)
            import traceback
            traceback.print_exc()

    def do_GET(self):
        self._dispatch(self._get)

    def _get(self):
        route = self.path.split("?")[0]
        if route in ("/", "/index.html"):
            self._static("index.html")
        elif route == "/api/state":
            self._json(state())
        elif route == "/api/creator":
            self._json({"ok":True,**STUDIO.creator.view()})
        elif route == "/api/audio/devices":
            global _audio_devices_cache
            _audio_devices_cache = time.perf_counter(), AudioAnalyzer.list_devices()
            self._json({"devices": _audio_devices_cache[1], **STUDIO.audio_status()})
        elif route == "/api/ai/config":
            self._json({"ai": STUDIO.ai_config()})
        elif route == "/api/keymap":
            self._json(STUDIO.mapping_status())
        elif route == "/api/health":
            self._json({"app": "AulaStudio", "build": BUILD, "pid": os.getpid()})
        elif route == "/api/stream":
            self._stream()
        else:
            self._static(route.lstrip("/"))

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while not STUDIO._stop.is_set():
                with STUDIO.lock:
                    payload = {"f": STUDIO.frame.hex(), "c": STUDIO.connected, "e": STUDIO.error,
                        "n": STUDIO.frames, "v": STUDIO.revision, "d": STUDIO.info(),
                        "p": copy.deepcopy(STUDIO.params), "s": copy.deepcopy(STUDIO.ai_spec)}
                if STUDIO.audio.active:
                    reactive = STUDIO.audio.reactive_snapshot()
                    payload["l"] = [round(v, 3) for v in reactive["levels"]]
                    payload["a"] = {k: reactive[k] for k in ("pulse", "energy", "beat_count")}
                self.wfile.write(f"data: {json.dumps(payload, allow_nan=False)}\n\n".encode())
                self.wfile.flush()
                STUDIO._stop.wait(0.07)
        except (OSError, TimeoutError):
            return

    def do_POST(self):
        self._dispatch(lambda: self._post(self.path.split("?")[0], self._body()))

    def _ok(self, **payload):
        self._json({"ok": True, **payload})

    def _post(self, route, body):
        if STUDIO._stop.is_set():
            raise RequestError("服务正在退出", 503)
        if route.startswith("/api/creator/"):
            return self._creator(route,body)
        if route == "/api/keymap/debug":
            STUDIO.configure_mapping_debug(body.get("enabled"),body.get("single_key",False))
            return self._ok(keymap=STUDIO.mapping_status())
        if route == "/api/keymap/calibrate":
            return self._ok(keymap=STUDIO.calibrate_mapping(body))
        if route == "/api/keymap/probe":
            led = body.get("led")
            if type(led) is not int or not 22<=led<LED_COUNT:
                raise ValueError("灯位编号须为22～131的整数（从0计数）")
            with STUDIO.lock:
                if not STUDIO.keymap_debug or not STUDIO.keymap_single:
                    raise ValueError("请先开启单键点亮测试")
                if not STUDIO.connected or not STUDIO.control_enabled:
                    raise ValueError("设备需要处于软件控制状态")
                STUDIO.keymap_probe,STUDIO.keymap_probe_until = led,time.perf_counter()+2
            return self._ok()
        if route == "/api/window/activate":
            activate = getattr(self.server, "window_activate", None)
            if not activate or not activate():
                raise RequestError("桌面窗口尚未就绪", 503)
            return self._ok()
        if route.startswith("/api/share/"):
            return self._share(route, body)
        if route == "/api/params":
            STUDIO.update_params(body)
            return self._ok(params=STUDIO.current()["params"], spec=STUDIO.ai_spec)
        if route == "/api/effect":
            if body.get("effect") == "ai":
                # AI works can use either an expression or a native engine.
                # The card is also an entry point for first-time creation.
                with STUDIO.lock:
                    revision, spec = STUDIO.revision, copy.deepcopy(STUDIO.ai_spec)
                    conversation = (copy.deepcopy(STUDIO.ai_history), copy.deepcopy(STUDIO.ai_versions))
                if spec is None:
                    return self._ok(params=STUDIO.current()["params"], needs_ai=True)
                STUDIO.apply_spec(spec, expected_revision=revision, conversation=conversation)
            else:
                STUDIO.update_params({"effect": body.get("effect")})
            return self._ok(params=STUDIO.current()["params"])
        if route == "/api/paint":
            leds = body.get("leds", {})
            if not isinstance(leds, dict) or ("clear" in body and not isinstance(body["clear"], bool)):
                raise ValueError("涂色参数格式错误")
            updates = {}
            for idx, rgb in leds.items():
                if not str(idx).isdigit() or not 0 <= int(idx) < LED_COUNT:
                    raise ValueError("灯位超出范围")
                updates[int(idx)] = valid.color(rgb)
            with STUDIO.lock:
                pixels = [[0,0,0] for _ in range(LED_COUNT)] if body.get("clear") else copy.deepcopy(STUDIO.paint)
                for idx, rgb in updates.items():
                    pixels[idx] = rgb
                STUDIO.paint = pixels
                STUDIO.params["effect"] = "paint"
                STUDIO.control_enabled = True
                STUDIO.revision += 1
            STUDIO.save_settings()
            return self._ok()
        if route == "/api/settings":
            mode = body.get("close_behavior")
            if mode not in ("hold", "release"):
                raise ValueError("关闭策略无效")
            with STUDIO.lock:
                STUDIO.close_behavior = mode
            STUDIO.save_settings()
            return self._ok(settings={"close_behavior": mode})
        if route == "/api/off":
            STUDIO.release()
            return self._ok(device=STUDIO.info())
        if route == "/api/onboard/save":
            return self._ok(onboard=STUDIO.save_onboard(), device=STUDIO.info())
        if route == "/api/shutdown":
            if 'force' in body and not isinstance(body['force'], bool):
                raise ValueError('退出选项必须是布尔值')
            receipt = None if body.get('force', False) else STUDIO.prepare_exit()
            self._ok(exit=receipt)
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if route == "/api/preview":
            return self._ok(f=_preview_frame(body))
        if route.startswith("/api/presets") or route.startswith("/api/custom"):
            return self._collection(route, body)
        if route == "/api/audio/config":
            gain = valid.number(body.get("gain", STUDIO.audio_gain), 0.2, 5, "音频增益")
            idx = body.get("device_index", STUDIO.audio_device)
            idx = None if idx in (None, "", "default") else int(valid.number(idx, 0, 10000, "音频设备"))
            with STUDIO.input_lock:
                STUDIO.audio_gain, STUDIO.audio_device = gain, idx
                STUDIO.audio.set_gain(gain)
                if body.get("restart") and STUDIO.params["effect"] == "audio" and STUDIO.control_enabled:
                    STUDIO.start_audio(idx)
            return self._ok(audio=STUDIO.audio_status())
        if route == "/api/ai/config":
            STUDIO.save_ai_config(body)
            return self._ok(ai=STUDIO.ai_config())
        if route == "/api/ai/params":
            with STUDIO.lock:
                if STUDIO.ai_spec is None or STUDIO.ai_new:
                    raise ValueError("请先生成或选择一份作品")
                if set(body) - {"color","color2","speed","brightness"}:
                    raise ValueError("未知作品参数")
                revision = STUDIO.revision
                spec = {**copy.deepcopy(STUDIO.ai_spec), **body}
                conversation = (copy.deepcopy(STUDIO.ai_history), copy.deepcopy(STUDIO.ai_versions))
            STUDIO.apply_spec(spec, expected_revision=revision, conversation=conversation)
            return self._ok(spec=STUDIO.ai_spec, params=STUDIO.current()["params"])
        if route == "/api/ai/apply":
            with STUDIO.lock:
                revision = STUDIO.revision
                conversation = ((copy.deepcopy(STUDIO.ai_history), copy.deepcopy(STUDIO.ai_versions))
                                if body.get("keep_conversation") is True else None)
            STUDIO.apply_spec(body.get("spec"), expected_revision=revision, conversation=conversation)
            return self._ok(spec=STUDIO.ai_spec, params=STUDIO.current()["params"])
        if route == "/api/ai/reset":
            with STUDIO.ai_lock:
                with STUDIO.lock:
                    STUDIO.ai_history = []
                    STUDIO.ai_versions = []
                    STUDIO.ai_new = True
                STUDIO.save_settings()
            return self._ok()
        if route == "/api/ai/undo":
            with STUDIO.ai_lock:
                STUDIO.undo_ai()
            return self._ok(spec=STUDIO.ai_spec, history=STUDIO.ai_history,
                            new=STUDIO.ai_new, undo=len(STUDIO.ai_versions), params=STUDIO.current()["params"])
        if route in ("/api/ai/chat", "/api/ai/compose", "/api/ai/generate", "/api/ai/refine"):
            if STUDIO.creator.busy():raise RequestError("创作正在进行，请先停止本轮",409)
            composing = route.endswith("compose")
            chatting = route.endswith("chat")
            prompt = body.get("prompt", "")
            colors = body.get("colors")
            if not composing and (not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000):
                raise ValueError("请输入 1～4000 字的灯效描述")
            if colors is not None and (not isinstance(colors, list) or len(colors) > 8 or any(not isinstance(c,str) or len(c)>16 for c in colors)):
                raise ValueError("配色参考格式错误")
            if not STUDIO.ai_lock.acquire(blocking=False):
                raise RequestError("另一次 AI 请求尚未结束", 409)
            try:
                with STUDIO.lock:
                    revision, current, history = STUDIO.revision, copy.deepcopy(STUDIO.ai_spec), copy.deepcopy(STUDIO.ai_history)
                    before = {"snapshot":STUDIO.current(), "history":history, "new":STUDIO.ai_new}
                    versions = copy.deepcopy(STUDIO.ai_versions)
                    fresh = route.endswith("generate") or STUDIO.ai_new or not current
                cfg = STUDIO.raw_ai_config()
                if chatting:
                    reply = ai_effects.converse(prompt, cfg, None if STUDIO.ai_new else current, history, colors)
                    with STUDIO.lock:
                        if STUDIO.revision != revision or STUDIO._stop.is_set():
                            raise RequestError("对话期间作品已改变，请重新发送。当前光效未被覆盖。", 409)
                        STUDIO.ai_history = (history+[{"role":"user","content":prompt},
                                                     {"role":"assistant","content":reply}])[-20:]
                    STUDIO.save_settings()
                    return self._ok(reply=reply, history=STUDIO.ai_history)
                if composing:
                    try:
                        spec = ai_effects.compose(cfg, None if STUDIO.ai_new else current, history, colors)
                    except ai_effects.AIError as exc:
                        with STUDIO.lock:
                            if STUDIO.revision == revision and not STUDIO._stop.is_set():
                                STUDIO.ai_history = (history+[{"role":"assistant",
                                    "content":"【程序反馈】生成未完成："+str(exc)}])[-20:]
                        STUDIO.save_settings()
                        raise
                    prompt = "按当前对话生成光效预览"
                else:
                    spec = (ai_effects.generate(prompt, cfg, colors) if fresh
                            else ai_effects.refine(prompt, cfg, current, history, colors))
                history = [] if fresh and not composing else history
                history = (history + [{"role":"user", "content":prompt},
                    {"role":"assistant", "content":ai_effects.summarise(spec)}])[-20:]
                STUDIO.apply_spec(spec, expected_revision=revision,
                                  conversation=(history, (versions+[before])[-8:]))
                return self._ok(spec=STUDIO.ai_spec, history=STUDIO.ai_history,
                                undo=len(STUDIO.ai_versions), params=STUDIO.current()["params"])
            finally:
                STUDIO.ai_lock.release()
        raise RequestError("接口不存在", 404)

    def _creator(self,route,body):
        session=STUDIO.creator
        if route=="/api/creator/message":
            prompt=body.get("prompt","")
            if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=4000:raise ValueError("请输入1～4000字的描述")
            if STUDIO.ai_lock.locked():raise RequestError("另一轮AI请求尚未结束",409)
            observation=None
            inputs=body.get("observation")
            draft=session.view()["draft"]
            if inputs is not None and draft:
                if not isinstance(inputs,dict) or set(inputs)-{"t","keys","audio"}:raise ValueError("模拟预览输入格式错误")
                frame=bytes.fromhex(_preview_frame({**inputs,"spec":draft}))
                selected={65,66,32,13}|{k.get("vk") for k in inputs.get("keys",[])}
                samples=[{"vk":k["vk"],"rgb":list(frame[k["led"]*3:k["led"]*3+3])}
                         for k in STUDIO.keymap.describe()["keys"] if k.get("vk") in selected][:12]
                observation={"source":"local_simulated_preview","inputs":inputs,"samples":samples}
            return self._ok(**session.submit(prompt.strip(),STUDIO.raw_ai_config(),observation))
        if route=="/api/creator/cancel":session.cancel();return self._ok(**session.view())
        if route=="/api/creator/reset":return self._ok(**session.edit(reset=True))
        if route=="/api/creator/undo":return self._ok(**session.edit(undo=True))
        if route=="/api/creator/params":return self._ok(**session.edit(patch=body))
        if route=="/api/creator/select":
            item=next((i for i in _read_json(CUSTOM,[]) if i.get("name")==body.get("name")),None)
            if not item:raise RequestError("作品不存在",404)
            return self._ok(**session.edit(draft=item))
        if route=="/api/creator/apply":
            view=session.view()
            if session.busy():raise RequestError("请先等本轮完成或停止本轮",409)
            if not view["draft"]:raise ValueError("还没有可应用的预览")
            STUDIO.apply_spec(view["draft"])
            return self._ok(params=STUDIO.current()["params"],spec=STUDIO.ai_spec)
        raise RequestError("接口不存在",404)

    def _share(self, route, body):
        with STUDIO.lock:
            geometry = sharing.layout(STUDIO.rows, STUDIO.cols, STUDIO.row_offset)
        if route == "/api/share/export":
            source = body.get("source", "current")
            name = body.get("name")
            if source == "current":
                snapshot = STUDIO.current()
                name = name or (snapshot.get("ai_spec") or {}).get("name") or "我的光效"
            elif source == "preset":
                items = _read_json(PRESETS, [])
                snapshot = next((i for i in items if i.get("name") == name), None)
                if snapshot is None:
                    raise RequestError("预设不存在", 404)
                snapshot = copy.deepcopy(snapshot)
                geometry = snapshot.get("layout", geometry)
                if "params" in body:
                    snapshot["params"] = valid.params(body["params"], snapshot.get("params"))
            elif source == "ai":
                spec, expr = valid.spec(body.get("spec"))
                params = valid.params({k:spec[k] for k in DEFAULT_PARAMS if k in spec})
                params["effect"] = "ai" if expr else spec["effect"]
                snapshot = {"params":params, "ai_spec":spec}
                name = name or spec["name"]
            else:
                raise ValueError("未知分享来源")
            return self._ok(code=sharing.encode(snapshot, name, geometry), name=name, layout=geometry)
        if route not in ("/api/share/inspect", "/api/share/import"):
            raise RequestError("接口不存在", 404)
        item = sharing.decode(body.get("code"))
        compatible = item["layout"] == geometry
        if route == "/api/share/inspect":
            return self._ok(**item, compatible=compatible)
        if not compatible:
            raise ValueError(f"此分享码为 {item['layout']['rows']} 行键盘布局，与本机布局不同，无法原样导入")
        name = body.get("name", item["name"])
        apply = body.get("apply", False)
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40:
            raise ValueError("预设名称须为 1～40 个字符")
        if not isinstance(apply, bool):
            raise ValueError("应用选项必须是布尔值")
        name = name.strip()
        with STORE_LOCK:
            items = _read_json(PRESETS, [])
            existing = {i.get("name") for i in items}
            candidate, index = name, 2
            while candidate in existing:
                suffix = f"（导入{index}）"
                candidate = name[:40-len(suffix)] + suffix
                index += 1
            item = {**item["snapshot"], "name":candidate, "layout":item["layout"]}
            _write_json(PRESETS, [*items, item])
        if apply:
            STUDIO.apply_snapshot(item)
        return self._ok(name=candidate, applied=apply, params=STUDIO.current()["params"], spec=STUDIO.ai_spec)

    def _collection(self, route, body):
        custom = route.startswith("/api/custom")
        prefix, path, field = ("/api/custom", CUSTOM, "custom") if custom else ("/api/presets", PRESETS, "presets")
        action = route[len(prefix):]
        if action not in ("", "/delete", "/rename", "/apply"):
            raise RequestError("接口不存在", 404)
        name = str(body.get("name") or "").strip()[:40]
        with STORE_LOCK:
            items = _read_json(path, [])
            if action == "":
                if not name:
                    raise ValueError("名字不能为空")
                if custom:
                    spec, _ = valid.spec(body.get("spec"))
                    item = {**spec, "name": name}
                else:
                    item = {**STUDIO.current(), "name": name,
                            "layout":sharing.layout(STUDIO.rows, STUDIO.cols, STUDIO.row_offset)}
                items = [i for i in items if i.get("name") != name] + [item]
            elif action == "/rename":
                old, new = str(body.get("old") or ""), str(body.get("new") or "").strip()[:40]
                if not new:
                    raise ValueError("新名字不能为空")
                if old != new and any(i.get("name") == new for i in items):
                    raise RequestError("名字已存在，请换一个名字", 409)
                if not any(i.get("name") == old for i in items):
                    raise RequestError("预设不存在", 404)
                items = [{**i, "name": new} if i.get("name") == old else i for i in items]
            elif action == "/delete":
                items = [i for i in items if i.get("name") != name]
            else:
                match = next((i for i in items if i.get("name") == name), None)
                if match is None:
                    raise RequestError("预设不存在", 404)
                # Release STORE_LOCK before applying (state/settings lock order).
                match = copy.deepcopy(match)
            if action != "/apply":
                _write_json(path, items)
                return self._ok(**{field: items})
        if custom:
            STUDIO.apply_spec(match)
        else:
            if "params" in body:
                match["params"] = valid.params(body["params"], match.get("params"))
            STUDIO.apply_snapshot(match)
        return self._ok(spec=STUDIO.ai_spec, params=STUDIO.current()["params"])


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def main(*, desktop: bool = False) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--self-test", metavar="RESULT_JSON")
    ap.add_argument("--no-device", action="store_true", help="UI diagnostics without opening HID/audio/input")
    args = ap.parse_args()
    if args.self_test:
        result = {"build":BUILD, **self_test(WEB)}
        Path(args.self_test).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    # A file lock covers custom ports too. Bind before any HID or input capture.
    import msvcrt
    lock_root = DATA if getattr(sys, "frozen", False) or DATA != WEB else ROOT
    handle = (lock_root / ".studio.lock").open("a+b")
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        # Do not read the locked first byte (Windows rejects that too).
        handle.seek(1)
        try:
            running_port = int(handle.read(8).decode("ascii").strip() or args.port)
        except (ValueError, OSError):
            running_port = args.port
        handle.close()
        print("键光已经在运行，请使用已打开的控制台。")
        if not args.no_open and 1 <= running_port <= 65535:
            if desktop:
                from kbdrv.desktop import activate_existing
                if not activate_existing(running_port):
                    raise RuntimeError("已有实例正在运行，请先退出旧版后重试")
            else:
                webbrowser.open(f"http://127.0.0.1:{running_port}/")
        return 0
    server = None
    try:
        try:
            server = StudioServer(("127.0.0.1", args.port), Handler)
        except OSError:
            print(f"端口 {args.port} 已占用；未再次接管键盘。请使用现有服务或关闭占用进程。")
            if desktop and not args.no_open:
                raise RuntimeError(f"本机端口 {args.port} 已被占用。请先退出旧版键光或其他占用程序，再重新打开。")
            return 1
        handle.seek(0)
        handle.truncate(0)
        handle.write(b"0" + str(server.server_port).encode("ascii"))
        handle.flush()
        if not args.no_device:
            STUDIO.start()
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"键光 {BUILD} 已启动: {url}", flush=True)
        if not args.no_open and not desktop:
            webbrowser.open(url)
        try:
            if desktop and not args.no_open:
                from kbdrv.desktop import run
                run(server, url, DATA, before_close=STUDIO.prepare_exit)
            else:
                server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            STUDIO.shutdown()
            server.server_close()
        print("已退出，软件灯效计算已停止；已保存的内置灯效由键盘独立运行。", flush=True)
        return 0
    finally:
        if server:
            server.server_close()
        handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
