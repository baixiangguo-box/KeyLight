"""AULA device database, extracted from the official web driver (see THIRD_PARTY_NOTICES.md)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_DB = Path(__file__).with_name("devices.json")

# protocol families that this project can actually drive
SUPPORTED_FAMILIES: tuple[str, ...] = ("0xFF1B",)

FAMILY_LABELS = {
    "0xFF1B": "RuiLianWei（帧推流协议）",
    "0xFF00": "RuiLianWei-SE",
    "0xFF68": "AULA 8K 系列",
    "0xFF60": "HERO / Neos 系列",
    "0xFFB0": "AG / WIN EVO 系列",
    "0xFFA8": "L 系列 / 接收器",
    "0xFF1C": "V9 系列",
    "0xFFA0": "HERO ULTRA",
    "0xFF80": "接收器",
    "0xFF02": "2.4G 接收器",
    "0x000C": "G10",
}


@dataclass(frozen=True)
class Model:
    name: str
    vid: int
    pid: int
    usage: int
    page: int
    family: str
    wireless: bool = False

    @property
    def supported(self) -> bool:
        return self.family in SUPPORTED_FAMILIES

    @property
    def hardware_verified(self) -> bool:
        return (self.name, self.vid, self.pid, self.page) == ("WIN 60 HE", 0x2E3C, 0xC365, 0xFF1B)

    @property
    def family_label(self) -> str:
        return FAMILY_LABELS.get(self.family, self.family)

    @property
    def id_text(self) -> str:
        return f"{self.vid:04X}:{self.pid:04X}"

    def as_dict(self) -> dict:
        return {
            "name": self.name, "vid": self.vid, "pid": self.pid,
            "usage": self.usage, "page": self.page, "family": self.family,
            "family_label": self.family_label, "wireless": self.wireless,
            "supported": self.supported, "hardware_verified":self.hardware_verified, "id": self.id_text,
        }


def _load() -> tuple[Model, ...]:
    try:
        raw = json.loads(_DB.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ()
    return tuple(Model(
        name=item["name"], vid=int(item["vid"]), pid=int(item["pid"]),
        usage=int(item["usage"]), page=int(item["page"]),
        family=str(item["family"]), wireless=bool(item.get("wireless")),
    ) for item in raw)


MODELS: tuple[Model, ...] = _load()


def by_id(vid: int, pid: int) -> list[Model]:
    return [m for m in MODELS if m.vid == vid and m.pid == pid]


def guess_model(vid: int, pid: int, product: str | None, page: int | None = None) -> Model | None:
    """Pick the model row that best matches a HID interface."""
    candidates = by_id(vid, pid)
    if not candidates:
        return None
    if product:
        product_l = re.sub(r"[^a-z0-9]", "", product.lower())
        aliases = {"si2825heargb":"win60he","si2825kzheargb":"win60he",
                   "si2828heargb":"win68he","si2828kzheargb":"win68he"}
        product_l = aliases.get(product_l,product_l)
        if (vid,pid) == (0x2E3C,0xC365):
            product_l = product_l.removeprefix("aula")
            named = [m for m in candidates if m.name and re.sub(r"[^a-z0-9]", "", m.name.lower()) == product_l]
        else:
            named = [m for m in candidates if m.name and re.sub(r"[^a-z0-9]", "", m.name.lower()) in product_l]
        if named:
            candidates = named
        elif (vid,pid) == (0x2E3C,0xC365):
            return None  # Shared USB identity alone does not identify a layout.
    elif (vid,pid) == (0x2E3C,0xC365):
        return None
    if page is not None:
        paged = [m for m in candidates if m.page == page]
        if paged:
            candidates = paged
    return candidates[0]


def families() -> dict[str, int]:
    out: dict[str, int] = {}
    for m in MODELS:
        out[m.family] = out.get(m.family, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
