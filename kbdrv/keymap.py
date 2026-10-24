"""One exact physical-key / firmware-LED mapping shared by all input paths."""
from __future__ import annotations

from .keymap_data import KEYMAPS

SCAN_CODES = {}
for start, codes in (
    (1, ["Escape",*["Digit"+str(i) for i in range(1,10)],"Digit0","Minus","Equal","Backspace","Tab"]),
    (0x10, ["Key"+k for k in "QWERTYUIOP"]+["BracketLeft","BracketRight","Enter","ControlLeft"]),
    (0x1e, ["Key"+k for k in "ASDFGHJKL"]+["Semicolon","Quote","Backquote","ShiftLeft","Backslash"]),
    (0x2c, ["Key"+k for k in "ZXCVBNM"]+["Comma","Period","Slash","ShiftRight"]),
):
    SCAN_CODES.update({(start+i,False):code for i,code in enumerate(codes)})
SCAN_CODES.update({(0x38,False):"AltLeft",(0x39,False):"Space",(0x3a,False):"CapsLock",
    (0x1d,True):"ControlRight",(0x38,True):"AltRight",(0x5b,True):"MetaLeft",(0x5c,True):"MetaRight",
    (0x5d,True):"ContextMenu",(0x52,True):"Insert",(0x53,True):"Delete",(0x49,True):"PageUp",
    (0x51,True):"PageDown",(0x4b,True):"ArrowLeft",(0x48,True):"ArrowUp",(0x4d,True):"ArrowRight",
    (0x50,True):"ArrowDown",(0x1c,True):"NumpadEnter"})


def profile_id(model):
    name = str(model or "").upper().replace(" ","")
    if name in ("WIN60HE","SI2825HEARGB","SI2825KZHEARGB","WIN60"):
        return "win60"
    if name in ("WIN68HE","SI2828HEARGB","SI2828KZHEARGB","WIN68"):
        return "win68"
    return None


class KeyMap:
    def __init__(self, model="WIN 60 HE", overrides=None):
        self.profile = profile_id(model)
        self.model = str(model)
        self.overrides = {}
        self._base = [dict(k) for k in KEYMAPS.get(self.profile,())]
        self._rebuild(overrides or {})

    def _rebuild(self, overrides):
        physical = {k["vk"] for k in self._base if k["vk"] is not None}
        if not isinstance(overrides,dict):
            raise ValueError("键灯校准必须是对象")
        checked = {}
        for vk,led in overrides.items():
            if not str(vk).isdigit() or int(vk) not in physical or type(led) is not int or not 22<=led<132:
                raise ValueError("键灯校准包含无效键或灯位编号")
            checked[int(vk)] = led
        entries = [{**k,"led":checked.get(k["vk"],k["led"])} for k in self._base]
        indices = [k["led"] for k in entries]
        if len(indices) != len(set(indices)):
            raise ValueError("两个物理键不能对应同一灯位，请使用交换校准")
        self.overrides = checked
        self.entries = entries
        self.by_vk = {k["vk"]:k for k in entries if k["vk"] is not None}
        self.by_code = {k["code"]:k for k in entries}

    @property
    def cells(self):
        return {vk:(k["led"]//22-1,k["led"]%22) for vk,k in self.by_vk.items()}

    def resolve(self, vk, scan=0, extended=False):
        if scan:
            return self.by_code.get(SCAN_CODES.get((scan,bool(extended))))
        # Synthetic zero-scan events and old callers retain explicit VK lookup.
        return self.by_vk.get(vk)

    def swap(self, vk, led):
        if type(vk) is not int or vk not in self.by_vk or type(led) is not int or not 22<=led<132:
            raise ValueError("请选择有效物理键和22～131之间的灯位编号")
        changed = dict(self.overrides)
        old = self.by_vk[vk]["led"]
        occupant = next((k for k in self.entries if k["led"]==led),None)
        if occupant and occupant["vk"] is None:
            raise ValueError("该灯位属于Fn固件键，不能用系统键码覆盖")
        if occupant:
            changed[occupant["vk"]] = old
        changed[vk] = led
        return KeyMap(self.model,changed)

    def describe(self):
        return {"profile":self.profile,"model":self.model,"rows":5,"cols":22,"row_offset":1,
                "source":"厂商逐键索引表" if self.profile else "此型号尚无键灯映射",
                "source_verified_locally":False,"calibrated":bool(self.overrides),
                "keys":self.entries,"mapped_keys":len(self.by_vk),"physical_keys":len(self.entries),
                "note":"Fn由固件处理，不向Windows上报独立键码。87/104及其他未知配列不使用猜测映射。"}


DEFAULT_MAP = KeyMap()
