"""Writable data paths and offline diagnostics for the packaged application."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_directory(web: Path) -> Path:
    override = os.environ.get("KEYLIGHT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(local) / "KeyLight" / "data"
    return web


def self_test(web: Path) -> dict:
    from . import audio, effects, models, sharing, validation
    from .expr import compile_expression
    import numpy as np

    checks = []
    for filename in ("index.html", "app.js", "splash.js", "style.css", "icon.svg"):
        assert (web / filename).is_file(), filename
    checks.append("bundled UI assets present")
    assert len(models.MODELS) == 127
    checks.append("device database loaded")
    assert audio.AudioAnalyzer.available()
    spectrum = np.abs(np.fft.rfft(np.zeros(audio.FFT_SIZE, dtype=np.float32)))
    assert len(spectrum) == audio.FFT_SIZE // 2 + 1
    checks.append("numpy FFT and WASAPI module import successfully")
    expression = compile_expression("hsv(x+t*.1,.8,1)")
    for effect in validation.EFFECTS:
        frame = effects.render(effect, 1, expr=expression, ripples=[(4,2,.4)], levels=[.4]*22)
        assert len(frame) == 132 and all(0 <= v <= 255 for color in frame for v in color)
    checks.append("all 14 renderers produce valid frames")
    code = sharing.encode({"params":{"effect":"ai"}, "ai_spec":{"expression":"rgb(1,2,3)"}},
                          "打包自检", sharing.layout(5,22,1))
    assert sharing.decode(code)["snapshot"]["ai_spec"]["expression"] == "rgb(1,2,3)"
    checks.append("offline sharing roundtrip")
    if getattr(sys,'frozen',False):
        import hid
        assert callable(hid.device)
        from .onboard import plan
        assert plan({'effect':'ripple'})['fields'][0] == 8
        checks.append('onboard lighting transport and command builders load without opening hardware')
    return {"ok":True, "checks":checks, "frozen":bool(getattr(sys,"frozen",False)),
            "python":sys.version.split()[0], "audio_available":True,
            "database_entries":len(models.MODELS), "hardware_opened":False}
