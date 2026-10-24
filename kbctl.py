"""Command line control for the AULA / 狼蛛 WIN 60 HE (RuiLianWei) RGB lighting.

Examples
--------
  python kbctl.py list
  python kbctl.py info
  python kbctl.py test                      # R / G / B quick check, then release
  python kbctl.py solid "#FF0000"
  python kbctl.py effect rainbow --seconds 30 --speed 1.2
  python kbctl.py paint '{"1": "#FF0000", "2": "#00FF00"}'
  python kbctl.py off                       # hand the LEDs back to the keyboard
"""

from __future__ import annotations

import argparse
import json
import time

from kbdrv import effects, hidwin
from kbdrv.device import Keyboard, UnsupportedKeyboard, describe, detect, lighting_candidates
from kbdrv.layout import LED_COLUMNS, LED_COUNT, LED_ROWS, frame_from_keys, key_label
from kbdrv.models import FAMILY_LABELS, MODELS, families


def cmd_list(args: argparse.Namespace) -> int:
    if args.all:
        for d in hidwin.enumerate_devices():
            print(
                f"{d['vid']:04X}:{d['pid']:04X} up=0x{d['usage_page']:04X} "
                f"u=0x{d['usage']:04X} in={d['in_len']} out={d['out_len']} "
                f"feat={d['feature_len']} {d['product']!r}"
            )
        return 0

    cands = detect()
    if not cands:
        print("没有找到狼蛛（AULA）键盘")
        return 1
    print(f"检测到 {len(cands)} 个 AULA HID 接口：")
    for cand in cands:
        print("  " + describe(cand))
    lighting = lighting_candidates()
    print(f"\n可作为灯光通道的接口：{len(lighting)}")
    for cand in lighting[:1]:
        print("  " + cand["path"])
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    fams = families()
    print(f"官方设备表：{len(MODELS)} 个型号 / {len(fams)} 个协议族\n")
    for fam, count in fams.items():
        mark = "✔ 已支持" if fam in ("0xFF1B",) else "· 仅识别"
        label = FAMILY_LABELS.get(fam, "")
        names = [m.name for m in MODELS if m.family == fam][:4]
        print(f"  {fam}  {mark:<8} {count:3d} 个  {label}")
        print(f"           例：{', '.join(names)}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    try:
        kb = Keyboard()
    except UnsupportedKeyboard as exc:
        print("识别到设备，但暂不支持：", exc)
        if exc.model:
            print(f"型号     : {exc.model.name}  ({exc.model.id_text})")
            print(f"协议族   : {exc.model.family}  {exc.model.family_label}")
        return 3
    try:
        info = kb.info or {}
        print(f"型号      : {info.get('model')}  ({info.get('product')})")
        print(f"USB       : {info.get('vid', 0):04X}:{info.get('pid', 0):04X}  固件 bcd {info.get('version', 0):04X}")
        print(f"协议族    : {info.get('family')}  {info.get('family_label')}")
        print(f"灯光接口  : usage page 0x{info.get('usage_page', 0):04X} / usage 0x{info.get('usage', 0):04X}")
        print(f"报文长度  : 输出 {info.get('out_len')} 字节")
        print(f"LED 矩阵  : {kb.rows} 行 x {kb.cols} 列 = {kb.rows * kb.cols} 颗"
              f"（帧 6x22，行偏移 {kb.row_offset}）")
        print(f"协议      : report id 0x01, sync 0x17, frame 0x0F, 每包 18 颗灯")
        return 0
    finally:
        kb.close()


def _apply(kb: Keyboard, args) -> None:
    frame = effects.render(
        args.effect,
        time.time(),
        color=effects.hex_to_rgb(args.color),
        brightness=args.brightness,
    )
    kb.send_frame(frame)


def cmd_test(args: argparse.Namespace) -> int:
    kb = Keyboard()
    try:
        for name, rgb in (("红", (255, 0, 0)), ("绿", (0, 255, 0)), ("蓝", (0, 0, 255))):
            print(f"发送 {name} 全键盘 ...", flush=True)
            kb.send_frame([rgb] * LED_COUNT)
            time.sleep(0.7)
        print("恢复键盘自带灯效 ...")
        kb.release()
        return 0
    finally:
        kb.close()


def cmd_solid(args: argparse.Namespace) -> int:
    rgb = effects.hex_to_rgb(args.color)
    kb = Keyboard()
    try:
        print(f"纯色 {effects.rgb_to_hex(rgb)}，{args.seconds}s")
        end = time.time() + args.seconds
        while time.time() < end:
            kb.send_frame([rgb] * LED_COUNT)
            time.sleep(0.05)
        kb.release()
        return 0
    finally:
        kb.close()


def cmd_effect(args: argparse.Namespace) -> int:
    kb = Keyboard()
    engine = effects.Engine(kb, fps=args.fps)
    engine.update(
        name=args.effect,
        color=effects.hex_to_rgb(args.color),
        color2=effects.hex_to_rgb(args.color2),
        speed=args.speed,
        brightness=args.brightness,
    )
    engine.start()
    print(f"效果 {args.effect} 运行 {args.seconds}s（Ctrl+C 提前结束）")
    try:
        end = time.time() + args.seconds
        while time.time() < end:
            time.sleep(0.24)
            if engine.error:
                print("错误:", engine.error)
                break
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        kb.release()
        kb.close()
    return 0


def cmd_paint(args: argparse.Namespace) -> int:
    raw = json.loads(args.colors)
    colors = {}
    for key, value in raw.items():
        if not str(key).isdigit():
            print(f"跳过非数字键位: {key}")
            continue
        colors[int(key)] = effects.hex_to_rgb(value)
    frame = frame_from_keys(colors)
    frame = [effects.scale(c, args.brightness) for c in frame]
    kb = Keyboard()
    try:
        print(f"逐键配色：{len(colors)} 个键位")
        end = time.time() + args.seconds
        while time.time() < end:
            kb.send_frame(frame)
            time.sleep(0.05)
        kb.release()
        return 0
    finally:
        kb.close()


def cmd_off(args: argparse.Namespace) -> int:
    kb = Keyboard()
    try:
        kb.release()
        print("已把灯光交还给键盘固件")
        return 0
    finally:
        kb.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="AULA WIN 60 HE 灯光驱动")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出键盘 HID 接口")
    p.add_argument("--all", action="store_true", help="列出全部 HID 设备")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("info", help="显示键盘与协议信息")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("models", help="列出官方设备表里的型号与协议族")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("test", help="红/绿/蓝快速自检")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("solid", help="整块键盘纯色")
    p.add_argument("color", nargs="?", default="#FF0000")
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--brightness", type=float, default=1.0)
    p.set_defaults(func=cmd_solid)

    p = sub.add_parser("effect", help="动态灯效")
    p.add_argument("effect", choices=list(effects.EFFECT_NAMES))
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--brightness", type=float, default=1.0)
    p.add_argument("--color", default="#FF2B2B")
    p.add_argument("--color2", default="#1E7BFF")
    p.add_argument("--fps", type=float, default=40.0)
    p.set_defaults(func=cmd_effect)

    p = sub.add_parser("paint", help="逐键配色 (JSON: 键位号 -> 颜色)")
    p.add_argument("colors", help='例如 \'{"1": "#FF0000", "14": "#00FF00"}\'')
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--brightness", type=float, default=1.0)
    p.set_defaults(func=cmd_paint)

    p = sub.add_parser("off", help="交还灯光控制权")
    p.set_defaults(func=cmd_off)

    args = parser.parse_args()
    try:
        return args.func(args)
    except OSError as exc:
        print("错误:", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
