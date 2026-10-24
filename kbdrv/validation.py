"""Shared, side-effect-free validation for HTTP, persistence and AI output."""
from __future__ import annotations

import math
from copy import deepcopy

from .expr import compile_expression
from .layout import LED_COUNT

EFFECTS = ["static", "breathe", "rainbow", "wave", "chase", "sparkle", "ripple",
           "audio", "meteor", "plasma", "fire", "aurora", "ai", "paint"]
DEFAULT_PARAMS = {"effect": "rainbow", "color": [255, 90, 60],
                  "color2": [30, 123, 255], "speed": 1.0, "brightness": 1.0,
                  "audio_style": "staggered"}


def number(value, lo: float, hi: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}必须是数字")
    try:
        value = float(value)
    except OverflowError:
        raise ValueError(f"{name}数值过大") from None
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{name}必须在 {lo:g}～{hi:g} 之间")
    return value


def color(value) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("颜色必须包含三个 0～255 的数字")
    return [int(number(c, 0, 255, "颜色")) for c in value]


def params(patch: dict, base: dict | None = None) -> dict:
    if not isinstance(patch, dict):
        raise ValueError("参数必须是 JSON 对象")
    if set(patch) - DEFAULT_PARAMS.keys():
        raise ValueError("包含未知灯效参数")
    out = deepcopy(DEFAULT_PARAMS)
    if base:
        out.update(deepcopy(base))
    out.update(patch)
    if out["effect"] not in EFFECTS:
        raise ValueError("未知灯效")
    if out["audio_style"] not in ("staggered", "radial"):
        raise ValueError("未知音频律动方式")
    out["speed"] = number(out["speed"], 0.05, 3, "速度")
    out["brightness"] = number(out["brightness"], 0, 1, "亮度")
    out["color"], out["color2"] = color(out["color"]), color(out["color2"])
    return out


def paint(value) -> list[list[int]]:
    if not isinstance(value, list) or len(value) != LED_COUNT:
        raise ValueError(f"涂色帧必须包含 {LED_COUNT} 个颜色")
    return [color(c) for c in value]


def spec(value: dict) -> tuple[dict, object | None]:
    if not isinstance(value, dict):
        raise ValueError("AI 光效必须是 JSON 对象")
    out = deepcopy(value)
    kind = out.get("kind", "expression")
    if kind not in ("expression", "preset", "program"):
        raise ValueError("未知 AI 光效类型")
    out["kind"] = kind
    out["name"] = str(out.get("name") or "AI 光效").strip()[:40]
    out["speed"] = number(out.get("speed", 1), 0.05, 3, "速度")
    out["brightness"] = number(out.get("brightness", 1), 0, 1, "亮度")
    fn = None
    if kind == "program":
        from .program import compile_program
        from .expr import normalize_expression
        out["color"] = color(out.get("color", DEFAULT_PARAMS["color"]))
        out["color2"] = color(out.get("color2", DEFAULT_PARAMS["color2"]))
        source = out.get("expression", "")
        if not isinstance(source,str):
            raise ValueError("光效程序必须是文本")
        source = normalize_expression(source)
        fn = compile_program(source)
        out["expression"] = source
    elif kind == "expression":
        fn = compile_expression(out.get("expression", ""))
    else:
        checked = params({k: out[k] for k in DEFAULT_PARAMS if k in out})
        if checked["effect"] in ("ai", "paint"):
            raise ValueError("内置 AI 预设必须指定普通灯效")
        out.update(checked)
    return out, fn


def snapshot(value: dict) -> tuple[dict, object | None]:
    if not isinstance(value, dict):
        raise ValueError("效果快照格式错误")
    checked = params(value.get("params", {}))
    pixels = paint(value.get("paint", [[0, 0, 0] for _ in range(LED_COUNT)]))
    current, fn = (None, None)
    if value.get("ai_spec") is not None:
        current, fn = spec(value["ai_spec"])
    if checked["effect"] == "ai" and fn is None:
        raise ValueError("这份旧预设缺少 AI 表达式，请重新生成或从 AI 收藏应用")
    return {"version": 2, "params": checked, "paint": pixels, "ai_spec": current}, fn
