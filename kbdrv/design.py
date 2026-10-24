"""Compile data-only lighting layers into the existing portable expression DSL."""
from __future__ import annotations

from . import validation as valid

GUIDE = """优先使用结构化方案，无需自己写数学公式：
{"kind":"layers","name":"深海白光","background":[0,4,18],
 "layers":[{"pattern":"scan","color":[220,235,255],"axis":"x","rate":0.2,"width":0.15,"strength":0.8}],
 "speed":1,"brightness":0.8,"explain":"深蓝底上白光从左向右掠过","change":""}
background 是实际底色 RGB(0..255)，要暗就直接用小数值颜色分量，例如 [0,4,18]。
layers 可为 0..3 层，按顺序叠加。每层 color 为 RGB，strength 为 0..1。
pattern 可选：solid(覆盖)、breathe(呼吸)、wave(连续波)、scan(单向循环光束)、
ring(自动从指定中心扩散的环)、sparkle(分散明暗光点)、checker(交错亮起)。
rate 为每秒周期 0.02..3，phase 为周期偏移 0..1；wave/scan 的 axis 可为 x/y，
wave 的 frequency 为 0.2..8，scan/ring 的 width 为 0.03..0.8，
direction 可为 forward(左到右/上到下/向外) 或 reverse(反向)，
ring 的 center 为 [0..1,0..1]，自动环与按键触发不同。未用参数可省略。
speed 范围 0.05..3；brightness 范围 0..1。先尊重自然语言颜色，再参考选色。
需要真实按键触发或系统声音时，必须使用内置方案：
{"kind":"preset","name":"蓝色涟漪","effect":"ripple","color":[0,30,80],
 "color2":[200,225,255],"speed":1,"brightness":0.8,"explain":"按键触发涟漪","change":""}
effect 可选 static/breathe/rainbow/wave/chase/sparkle/ripple/audio/meteor/plasma/fire/aurora。
ripple 使用主色 20% 作底，按键出现副色光环；audio 的 audio_style 为 staggered(交错)
或 radial(按键中心辐射)，真实响应系统声音。内置方案不能任意逐键编程。
结构化方案不满足时才使用 kind=expression，遵守以下 DSL；它不能访问声音或按键。
"""


def compile_design(value: dict) -> dict:
    background = valid.color(value.get("background", [0, 0, 0]))
    layers = value.get("layers", [])
    if not isinstance(layers, list) or len(layers) > 3:
        raise ValueError("光效最多组合三层")
    clean = []
    expr = f"rgb({','.join(map(str, background))})"
    for layer in layers:
        if not isinstance(layer, dict):
            raise ValueError("每层光效必须是对象")
        pattern = layer.get("pattern", "solid")
        if pattern not in ("solid", "breathe", "wave", "scan", "ring", "sparkle", "checker"):
            raise ValueError("未知的光效图层")
        color = valid.color(layer.get("color", [255, 255, 255]))
        strength = valid.number(layer.get("strength", 1), 0, 1, "图层亮度")
        rate = valid.number(layer.get("rate", 0.25), 0.02, 3, "变化频率")
        phase = valid.number(layer.get("phase", 0), 0, 1, "相位")
        axis = layer.get("axis", "x")
        if axis not in ("x", "y"):
            raise ValueError("方向只能是 x 或 y")
        direction = layer.get("direction", "forward")
        if direction not in ("forward", "reverse"):
            raise ValueError("移动方向无效")
        width = valid.number(layer.get("width", 0.15), 0.03, 0.8, "光束宽度")
        frequency = valid.number(layer.get("frequency", 1), 0.2, 8, "波纹密度")
        center = layer.get("center", [0.5, 0.5])
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            raise ValueError("光环中心必须是两个坐标")
        cx, cy = [valid.number(c, 0, 1, "中心坐标") for c in center]
        clock = f"(t*{rate:g}+{phase:g})"
        position = f"mod({clock},1)"
        if direction == "reverse":
            position = f"(1-{position})"
        if pattern == "solid":
            mask = "1"
        elif pattern == "breathe":
            mask = f"(0.5-0.5*cos(tau*{clock}))"
        elif pattern == "wave":
            sign = "-" if direction == "forward" else "+"
            mask = f"(0.5+0.5*cos(tau*({axis}*{frequency:g}{sign}{clock})))"
        elif pattern == "scan":
            mask = f"max(0,1-abs({axis}-{position})/{width:g})"
        elif pattern == "ring":
            mask = f"max(0,1-abs(sqrt((x-{cx:g})**2+(y-{cy:g})**2)-{position}*1.5)/{width:g})"
        elif pattern == "sparkle":
            mask = f"(0.5+0.5*sin(i*12.9898+{clock}*tau))**8"
        else:
            mask = f"(0.5+0.5*cos(pi*(row+col)+tau*{clock}))"
        expr = f"mix({expr},rgb({','.join(map(str, color))}),{strength:g}*{mask})"
        clean.append(dict(pattern=pattern, color=color, strength=strength, rate=rate,
                          phase=phase, axis=axis, direction=direction, width=width,
                          frequency=frequency, center=[cx, cy]))
    return {**value, "kind": "expression", "expression": expr,
            "design": {"background": background, "layers": clean}}
