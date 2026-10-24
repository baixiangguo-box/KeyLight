"""Portable, bounded, data-only preset codes. No account settings or AI history."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import zlib

from . import validation as valid

PREFIX = "KEYLIGHT1"
RENDERER = 1  # Bump when renderer semantics change incompatibly.
MAX_CODE = 16000
MAX_DATA = 24000


def layout(rows: int, cols: int, row_offset: int) -> dict:
    if any(type(v) is not int for v in (rows,cols,row_offset)) or (rows, cols, row_offset) not in ((5,22,1), (6,22,0)):
        raise ValueError("分享码的键盘布局不受支持")
    return {"rows":rows, "cols":cols, "row_offset":row_offset}


def clean_snapshot(value: dict) -> dict:
    try:
        checked, _ = valid.snapshot(value)
    except RecursionError:
        raise ValueError("分享内容嵌套过深") from None
    params = checked["params"]
    result = {"version":2, "params":params}
    if params["effect"] == "paint":
        result["paint"] = checked["paint"]
    if params["effect"] == "ai":
        source = checked["ai_spec"]
        result["ai_spec"] = {"kind":source["kind"], "name":source["name"],
                             "expression":source["expression"],
                             "speed":params["speed"], "brightness":params["brightness"]}
        if source["kind"] == "program":
            result["ai_spec"].update(color=params["color"], color2=params["color2"])
    return result


def encode(value: dict, name: str, geometry: dict) -> str:
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40:
        raise ValueError("分享名称须为 1～40 个字符")
    cleaned = clean_snapshot(value)
    renderer = 2 if (cleaned.get("ai_spec") or {}).get("kind") == "program" else RENDERER
    payload = {"format":1, "renderer":renderer, "name":name.strip(),
               "layout":layout(**geometry), "snapshot":clean_snapshot(value)}
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_DATA:
        raise ValueError("光效内容过大，无法生成分享码")
    packed = zlib.compress(raw, 9)
    text = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    code = f"{PREFIX}.{text}.{hashlib.sha256(packed).hexdigest()[:16]}"
    if len(code) > MAX_CODE:
        raise ValueError("分享码过长")
    return code


def decode(code: str) -> dict:
    if not isinstance(code, str) or len(code) > MAX_CODE * 2:
        raise ValueError("分享码格式错误或过长")
    code = "".join(code.split())
    if len(code) > MAX_CODE:
        raise ValueError("分享码过长")
    parts = code.split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise ValueError("请粘贴完整的 KEYLIGHT1 分享码；其他版本请先更新键光")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", parts[1]) or not re.fullmatch(r"[0-9a-f]{16}", parts[2]):
        raise ValueError("分享码格式错误，请重新复制完整内容")
    try:
        packed = base64.b64decode(parts[1]+"="*((-len(parts[1]))%4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("分享码编码无效") from None
    if not hmac.compare_digest(hashlib.sha256(packed).hexdigest()[:16], parts[2]):
        raise ValueError("分享码校验失败，内容可能未复制完整")
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(packed, MAX_DATA+1)
        if len(raw) > MAX_DATA or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("分享码内容过大或压缩格式无效")
        payload = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("数值无效")))
    except (zlib.error, UnicodeError, RecursionError):
        raise ValueError("分享码内容无效") from None
    if not isinstance(payload, dict) or payload.get("format") != 1 or payload.get("renderer") not in (1,2):
        raise ValueError("此分享码需要其他版本的键光")
    geometry = payload.get("layout")
    if not isinstance(geometry, dict) or set(geometry) != {"rows", "cols", "row_offset"}:
        raise ValueError("分享码缺少有效键盘布局")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40:
        raise ValueError("分享码的光效名称无效")
    snapshot = clean_snapshot(payload.get("snapshot"))
    snapshot, _ = valid.snapshot(snapshot)
    return {"name":name.strip(), "layout":layout(**geometry), "snapshot":snapshot}
