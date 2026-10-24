"""Protocol adapters - one per family of AULA keyboards.

Only the RuiLianWei family (usage page 0xFF1B, WIN 60/68 HE) has an adapter;
only WIN 60 HE is verified on real hardware. Everything else is recognised from
the official device table, reported to the user, and refused instead of being
sent garbage.
"""

from __future__ import annotations

import time

from . import hidwin
from .layout import LED_COLUMNS, LED_COUNT
from .models import Model

Color = tuple[int, int, int]
FRAME_LEDS = LED_COUNT  # 6 x 22 slots per wire frame


class AdapterError(RuntimeError):
    pass


class NotSupported(AdapterError):
    def __init__(self, model: Model | None, family: str | None = None):
        self.model = model
        self.family = family or (model.family if model else "?")
        label = model.family_label if model else self.family
        name = model.name if model else "未知型号"
        super().__init__(
            f"{name} 属于 {self.family}（{label}）协议族，尚未逆向；"
            f"需要一次抓包才能支持。"
        )


class Adapter:
    """Common interface used by the studio / CLI."""

    family = "?"
    rows = 5
    cols = 22
    row_offset = 1
    verified = False

    def __init__(self, device: hidwin.HidDevice, model: Model | None):
        self.device = device
        self.model = model

    # -- to implement ---------------------------------------------------
    def send_frame(self, colors: list[Color]) -> None:
        raise NotImplementedError

    def release(self) -> None:
        pass

    def close(self) -> None:
        try:
            self.device.close()
        except Exception:  # noqa: BLE001
            pass

    @property
    def led_count(self) -> int:
        return self.rows * self.cols


class FrameStream(Adapter):
    """Command 0x17 (take over) + 0x0F (RGB frames), 18 LEDs per packet.

    Measured on WIN 60 HE. WIN 68 HE uses the vendor's five-row layout with
    extra navigation columns; its physical behavior is not locally verified.
    """

    family = "0xFF1B"
    verified = False
    report_id = 0x01
    report_len = 64
    sync_cmd = 0x17
    frame_cmd = 0x0F
    leds_per_packet = 18
    packet_delay = 0.002
    sync_delay = 0.05

    def __init__(self, device: hidwin.HidDevice, model: Model | None,
                 rows: int = 5, row_offset: int = 1):
        super().__init__(device, model)
        self.rows = rows
        self.row_offset = row_offset
        self.verified = bool(model and model.hardware_verified)
        self._synced = False

    # ------------------------------------------------------------------
    def _write(self, packet: bytes, label: str) -> None:
        if len(packet) != self.report_len:
            raise AdapterError(f"{label}: 报文长度 {len(packet)} != {self.report_len}")
        written = self.device.write(bytes(packet))
        if written != self.report_len:
            raise AdapterError(f"{label}: 只写入 {written} 字节")

    def set_sync(self, enabled: bool = True) -> None:
        packet = bytearray(self.report_len)
        packet[0] = self.report_id
        packet[1] = self.sync_cmd
        packet[5] = 2
        packet[6] = 1 if enabled else 0
        packet[7] = 1 if enabled else 0
        self._write(packet, "sync")
        self._synced = bool(enabled)
        if enabled:
            time.sleep(self.sync_delay)

    def send_frame(self, colors: list[Color]) -> None:
        # the wire frame is always 6 x 22 slots, even when the board only lights
        # five of the rows (the 60% variant ignores frame row 0)
        count = FRAME_LEDS
        if len(colors) != count:
            raise ValueError(f"需要 {count} 个颜色，收到 {len(colors)}")
        if not self._synced:
            self.set_sync(True)
        flat = bytes(int(c) & 0xFF for rgb in colors for c in rgb)
        total = (count + self.leds_per_packet - 1) // self.leds_per_packet
        for index in range(total):
            start = index * self.leds_per_packet * 3
            chunk = flat[start:start + self.leds_per_packet * 3]
            packet = bytearray(self.report_len)
            packet[0] = self.report_id
            packet[1] = self.frame_cmd
            packet[3] = (index >> 8) & 0xFF
            packet[4] = index & 0xFF
            packet[5] = len(chunk)
            packet[6:6 + len(chunk)] = chunk
            self._write(packet, f"frame {index + 1}/{total}")
            time.sleep(self.packet_delay)

    def release(self) -> None:
        self.set_sync(False)
        self._synced = False


class Unsupported(Adapter):
    def __init__(self, device: hidwin.HidDevice, model: Model | None):
        super().__init__(device, model)
        self.family = model.family if model else "?"

    def send_frame(self, colors: list[Color]) -> None:
        raise NotSupported(self.model, self.family)


def build(device: hidwin.HidDevice, model: Model | None) -> Adapter:
    """Pick an adapter for the detected model."""
    family = model.family if model else None
    if family == "0xFF1B":
        name = (model.name if model else "") or ""
        if "68" in name:
            # The 65% WIN68 adds navigation columns, not an F-key row.
            return FrameStream(device, model, rows=5, row_offset=1)
        return FrameStream(device, model, rows=5, row_offset=1)
    return Unsupported(device, model)
