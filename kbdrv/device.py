"""Device discovery + facade over the protocol adapters."""

from __future__ import annotations

from . import adapters, hidwin
from .adapters import Adapter, NotSupported
from .models import MODELS, Model, guess_model

AULA_VIDS = {m.vid for m in MODELS}


class KeyboardNotFound(OSError):
    def __init__(self) -> None:
        super().__init__("没有找到狼蛛（AULA）键盘，请确认已用数据线连接")


class UnsupportedKeyboard(OSError):
    def __init__(self, model: Model | None, family: str, reason: str) -> None:
        self.model = model
        self.family = family
        self.reason = reason
        name = model.name if model else "未知型号"
        super().__init__(f"{name}：{reason}")


def detect() -> list[dict]:
    """All HID interfaces that belong to a known AULA model."""
    found = []
    for info in hidwin.enumerate_devices():
        if info["vid"] not in AULA_VIDS:
            continue
        model = guess_model(info["vid"], info["pid"], info.get("product"), info["usage_page"])
        found.append({**info, "model": model})
    return found


def lighting_candidates() -> list[dict]:
    """Interfaces that look like a lighting/vendor collection for a known model."""
    out = []
    for cand in detect():
        model = cand["model"]
        if model is None:
            continue
        exact = cand["usage_page"] == model.page and cand.get("usage") == model.usage
        vendor = cand["usage_page"] >= 0xFF00
        if exact or vendor:
            cand["exact"] = exact
            out.append(cand)
    out.sort(key=lambda c: (not c["exact"], not (c["model"] and c["model"].supported)))
    return out


def describe(cand: dict) -> str:
    model = cand.get("model")
    name = model.name if model else cand.get("product") or "?"
    family = model.family if model else f"0x{cand['usage_page']:04X}"
    state = "已实测" if model and model.hardware_verified else "已适配/未实测" if model and model.supported else "未支持"
    return (f"{name:<24} {cand['vid']:04X}:{cand['pid']:04X}  "
            f"page=0x{cand['usage_page']:04X}/usage=0x{cand.get('usage', 0):02X}  {family}  {state}")


class Keyboard:
    """High level handle: finds the right interface and the right adapter."""

    def __init__(self, path: str | None = None):
        self.info: dict | None = None
        self.adapter: Adapter | None = None
        self.model: Model | None = None

        candidates = lighting_candidates()
        if not candidates:
            raise KeyboardNotFound()
        if path:
            preferred = [c for c in candidates if c["path"] == path]
            candidates = preferred or candidates

        cand = candidates[0]
        self.model = cand["model"]
        self.info = {
            "product": cand.get("product") or (self.model.name if self.model else "AULA"),
            "vid": cand["vid"],
            "pid": cand["pid"],
            "version": cand.get("version", 0),
            "usage_page": cand["usage_page"],
            "usage": cand.get("usage", 0),
            "out_len": cand.get("out_len", 0),
            "path": cand["path"],
            "model": self.model.name if self.model else "?",
            "family": self.model.family if self.model else "?",
            "family_label": self.model.family_label if self.model else "?",
            "supported": bool(self.model and self.model.supported),
            "hardware_verified":bool(self.model and self.model.hardware_verified),
        }

        if not (self.model and self.model.supported):
            raise UnsupportedKeyboard(
                self.model,
                self.model.family if self.model else "?",
                "识别到了这个型号，但该协议族还没有逆向",
            )

        device = hidwin.HidDevice(cand["path"])
        device.open()
        try:
            self.adapter = adapters.build(device, self.model)
        except Exception:
            device.close()
            raise
        self.info["rows"] = self.adapter.rows
        self.info["cols"] = self.adapter.cols
        self.info["row_offset"] = self.adapter.row_offset

    # ------------------------------------------------------------------
    @property
    def rows(self) -> int:
        return self.adapter.rows if self.adapter else 5

    @property
    def cols(self) -> int:
        return self.adapter.cols if self.adapter else 22

    @property
    def row_offset(self) -> int:
        return self.adapter.row_offset if self.adapter else 1

    def send_frame(self, colors) -> None:
        if not self.adapter:
            raise NotSupported(self.model)
        self.adapter.send_frame(colors)

    def release(self) -> None:
        if self.adapter:
            self.adapter.release()

    def save_onboard(self, request: dict, paint: list) -> dict:
        # Restrict persistent settings to the actual verified model/protocol.
        if not self.model or not self.model.hardware_verified or not self.info:
            raise ValueError('此型号尚未验证板载保存，未发送保存命令')
        from .onboard import Lighting
        with Lighting(self.info['path']) as lighting:
            result = lighting.save(request, paint)
            self.release()
            if lighting.read() != result['fields']:
                raise ValueError('退出软件推流后，键盘灯效核对不一致')
        return result

    def close(self) -> None:
        if self.adapter:
            self.adapter.close()
            self.adapter = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def connect() -> Keyboard:
    return Keyboard()
