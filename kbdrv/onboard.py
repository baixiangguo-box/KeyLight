"""WIN60 HE's built-in lighting configuration, distinct from RAM RGB streaming.

Lighting only: 07/01 reads, 07/00 writes, and 09/00 custom RGB chunks.
No firmware, actuation, keymap, profile, or reset commands are used.
"""
from __future__ import annotations

import math
import time

from . import validation

MODES = {'static':(0,'纯色'), 'breathe':(1,'呼吸'), 'rainbow':(2,'彩虹'),
         'wave':(2,'双色波'), 'aurora':(7,'极光'), 'ripple':(8,'涟漪'),
         'sparkle':(9,'星光'), 'paint':(10,'逐键涂色')}
NOTE = '使用键盘内置版本；动画可能与软件版不同，速度和亮度按键盘的 5 档保存。'


class OnboardError(ValueError):
    pass


def plan(params: dict) -> dict:
    effect = params['effect']
    if effect not in MODES:
        return {'supported':False, 'message':'此效果由软件计算，当前固件保存协议不能将它保存为离线动态灯效。电脑预设仍会保留。'}
    checked = validation.params(params)
    mode, name = MODES[effect]
    foreground = list(checked['color'])
    background = list(checked['color2'])
    full_color = int(effect == 'rainbow')
    if effect == 'ripple':
        foreground = list(checked['color2'])
        background = [int(v*.2) for v in checked['color']]
    brightness = min(4, max(0, int(checked['brightness']*4+.5)))
    if checked['brightness'] == 0:
        # Black static is unambiguous even if firmware's lowest brightness
        # level is dim rather than off.
        mode, foreground, background, full_color, brightness = 0, [0]*3, [0]*3, 0, 4
    speed = min(4, max(0, int(2+2*math.log(checked['speed'], 3)+.5)))
    fields = [mode, speed, brightness, *foreground, *background, 0, full_color, 0]
    return {'supported':True, 'effect':effect, 'name':name, 'fields':fields,
            'speed_level':speed, 'brightness_level':brightness, 'message':NOTE}


def packet(command: int, payload: bytes) -> bytes:
    if len(payload) > 62:
        raise OnboardError('板载报文过长')
    return bytes([1, command]) + payload + bytes(62-len(payload))


class Lighting:
    """Use hidapi's bounded reads; never wait indefinitely for a write ACK."""
    def __init__(self, path: str):
        import hid
        self.device = hid.device()
        try:
            self.device.open_path(path.encode('utf-8') if isinstance(path,str) else path)
        except Exception:
            self.device.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.device.close()

    def _write(self, data: bytes):
        if self.device.write(data) != 64:
            raise OnboardError('键盘灯效设置未完整写入')

    def _drain(self):
        for _ in range(32):
            if not self.device.read(64, 1):
                return
        raise OnboardError('键盘持续返回其他数据，请关闭其他驱动后重试')

    def read(self) -> list[int]:
        self._drain()
        self._write(packet(7, bytes([1])))
        deadline = time.perf_counter()+.8
        while time.perf_counter() < deadline:
            raw = bytes(self.device.read(64, 100))
            if len(raw) >= 18 and raw[:2] == b'\x01\x07' and raw[5] >= 12:
                return list(raw[6:18])
        raise OnboardError('没有读到键盘返回的灯效设置，未确认保存成功')

    def _global(self, fields: list[int]):
        if len(fields) != 12 or any(type(v) is not int or not 0 <= v <= 255 for v in fields):
            raise OnboardError('板载灯效设置无效')
        # Write commands on the tested firmware have no response. A separate
        # 07/01 query provides the actual verification instead.
        self._write(packet(7, bytes([0,0,0,14,*fields])))

    def save(self, request: dict, paint: list | None = None) -> dict:
        if not request.get('supported'):
            raise OnboardError(request['message'])
        old = self.read()
        expected = request['fields']
        if request['effect'] == 'paint' and expected[0] == 10:
            colors = validation.paint(paint)
            # Snapshot custom colors for rollback before changing any bytes.
            old_colors = self.read_colors()
        else:
            colors, old_colors = None, None
        try:
            if colors is not None:
                self._colors(colors)
                if self.read_colors() != colors:
                    raise OnboardError('逐键配色读取核对不一致，未确认保存成功')
            self._global(expected)
            actual = self.read()
            if actual != expected:
                raise OnboardError('键盘返回的模式或参数不一致，未确认保存成功')
        except Exception:
            try:
                if old_colors is not None:
                    self._colors(old_colors)
                self._global(old)
            except Exception:
                pass
            raise
        return {'verified':True, 'effect':request['effect'], 'name':request['name'],
                'fields':actual, 'message':request['message']}

    def _colors(self, colors: list):
        raw = bytes(v for rgb in colors for v in rgb)
        for index, start in enumerate(range(0,396,54)):
            chunk = raw[start:start+54]
            self._write(packet(9, bytes([0,0,index,len(chunk)])+chunk))
            time.sleep(.005)

    def read_colors(self) -> list:
        self._drain()
        self._write(packet(9, bytes([0x80])))
        chunks = {}
        deadline = time.perf_counter()+1
        while len(chunks) < 8 and time.perf_counter() < deadline:
            raw = bytes(self.device.read(64, 100))
            if len(raw) != 64 or raw[:3] != b'\x01\x09\x80':
                continue
            index, size = raw[3]*256+raw[4], raw[5]
            if index < 8 and size == (18 if index == 7 else 54):
                chunks[index] = raw[6:6+size]
        if len(chunks) != 8:
            raise OnboardError('未能读取完整的键盘逐键配色')
        flat = b''.join(chunks[i] for i in range(8))
        return [list(flat[i:i+3]) for i in range(0,396,3)]
