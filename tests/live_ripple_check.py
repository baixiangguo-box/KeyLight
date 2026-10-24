"""Explicit live ripple check: inject Left Shift only; no text, audio or AI calls."""
import argparse
import ctypes
import json
import time
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--allow-hardware", action="store_true")
parser.add_argument("--output", required=True)
args = parser.parse_args()
if not args.allow_hardware:
    parser.error("Pass --allow-hardware to test the selected ripple effect")
BASE = "http://127.0.0.1:8787"


def state():
    with urllib.request.urlopen(BASE + "/api/state", timeout=5) as response:
        return json.load(response)


initial = state()
assert initial["build"] in ("20261021-ui3", "20261021-ui4", "20261021-ui5", "20261021-ui6", "20261021-ui7", "20261021-ui8", "20261022-onboard1")
assert initial["params"]["effect"] == "ripple"
assert initial["device"]["connected"] and initial["device"]["hook"]["started"]
emit = ctypes.WinDLL("user32").keybd_event
emit.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_size_t]
emit.restype = None
samples = []
with urllib.request.urlopen(BASE + "/api/stream", timeout=8) as stream:
    before = state()["device"]["hook"]["events"]
    try:
        for _ in range(4):
            emit(0xA0, 0x2A, 0, 0)
            time.sleep(.04)
        held = state()["device"]["hook"]["events"]
    finally:
        emit(0xA0, 0x2A, 2, 0)
    assert held - before == 1, (before, held)
    time.sleep(.05)
    try:
        emit(0xA0, 0x2A, 0, 0)
        time.sleep(.05)
    finally:
        emit(0xA0, 0x2A, 2, 0)
    second = state()["device"]["hook"]["events"]
    assert second - held == 1, (held, second)
    end = time.perf_counter() + 1.9 / initial["params"]["speed"] + .5
    while time.perf_counter() < end:
        line = stream.readline()
        if not line.startswith(b"data: "):
            continue
        packet = json.loads(line[6:])
        assert packet["c"] and not packet["e"]
        raw = bytes.fromhex(packet["f"])
        # The physical Left Shift is at row 3, column 1 in the current map.
        radial = [max(raw[((4*22+c)*3):((4*22+c)*3+3)]) for c in range(1, 22)]
        samples.append({"radius": max(range(21), key=radial.__getitem__),
                        "peak": max(raw), "frame": packet["n"]})

final = state()
assert final["params"] == initial["params"]
assert final["device"]["hook"]["ripples"] == 0
assert samples[-1]["peak"] < max(s["peak"] for s in samples)
assert max(s["radius"] for s in samples if s["peak"] > samples[-1]["peak"] + 3) >= 5
assert final["device"]["frames_sent"] > initial["device"]["frames_sent"]
report = {"build": final["build"], "device": final["device"]["name"],
          "checks": ["held Shift triggers once", "release and repress triggers again",
                     "ring expands and fades in last-sent frames", "events expire",
                     "parameters preserved", "device remains connected without error"],
          "samples": samples, "visual_acceptance": False,
          "hardware_receipt_acknowledged": False}
Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"build": report["build"], "checks": report["checks"],
                  "sample_count": len(samples)}, indent=2))
