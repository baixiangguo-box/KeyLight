"""Frame generators + animation engine for the WIN 60 HE."""

from __future__ import annotations

import colorsys
import math
import random
import threading
import time

from .layout import LED_COLUMNS, LED_COUNT, LED_ROWS, cells as layout_cells

Color = tuple[int, int, int]
RIPPLE_LIFETIME = 1.9  # Seconds at 1x speed; shared with event cleanup.

PRESETS: dict[str, str] = {
    "绾?: "#FF2B2B", "姗?: "#FF8A00", "榛?: "#FFD400", "缁?: "#22DD55",
    "闈?: "#00E5D0", "钃?: "#1E7BFF", "绱?: "#8B5CF6", "绮?: "#FF4FA3",
    "鐧?: "#FFFFFF",
}

EFFECT_NAMES = (
    "static", "breathe", "rainbow", "wave", "chase", "sparkle",
    "ripple", "audio", "meteor", "plasma", "fire", "aurora", "ai",
)

# LED cells are fetched per frame through layout.cells(rows, row_offset) so the
# same renderer works for 60% (5 rows) and 68% (6 rows) boards.


# ------------------------------------------------------------------ helpers
def hex_to_rgb(value: str) -> Color:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f"bad colour: {value!r}")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def rgb_to_hex(rgb: Color) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(c) & 0xFF for c in rgb))


def scale(rgb: Color, factor: float) -> Color:
    factor = max(0.0, min(1.0, factor))
    return tuple(int(max(0, min(255, c * factor))) for c in rgb)  # type: ignore[return-value]


def mix(a: Color, b: Color, f: float) -> Color:
    f = max(0.0, min(1.0, f))
    return tuple(int(a[i] * (1 - f) + b[i] * f) for i in range(3))  # type: ignore[return-value]


def hsv(h: float, s: float = 1.0, v: float = 1.0) -> Color:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return (int(r * 255), int(g * 255), int(b * 255))


def _hash(x: float) -> float:
    v = math.sin(x * 12.9898) * 43758.5453
    return v - math.floor(v)


# ------------------------------------------------------------------ effects
def render(
    name: str,
    t: float,
    *,
    color: Color = (255, 60, 60),
    color2: Color = (0, 120, 255),
    speed: float = 1.0,
    brightness: float = 1.0,
    paint: list[Color] | None = None,
    paint_mask: set[int] | None = None,
    ripples: list[tuple[int, int, float]] | None = None,
    levels: list[float] | None = None,
    audio_pulse: float | None = None,
    audio_energy: float | None = None,
    audio_beat: int = 0,
    audio_style: str = "staggered",
    audio_center: tuple[int, int] | None = None,
    expr=None,
    active_keys: dict[int, float] | None = None,
    key_state: dict | None = None,
    rows: int | None = None,
    row_offset: int | None = None,
) -> list[Color]:
    """Return a full 132-slot frame (row 0 is dark on 60% boards)."""
    name = (name or "static").lower()
    t = t * max(0.05, speed)
    cells = layout_cells(rows, row_offset)
    physical_rows = LED_ROWS if rows is None else rows
    frame: list[Color] = [(0, 0, 0)] * LED_COUNT

    if name in ("static", "solid", "paint"):
        if paint:
            frame = list(paint)
        else:
            frame = [color] * LED_COUNT

    elif name == "breathe":
        level = 0.5 - 0.5 * math.cos(2 * math.pi * t / 2.4)
        frame = [scale(color, 0.05 + 0.95 * level)] * LED_COUNT

    elif name == "rainbow":
        for led, row, col in cells:
            frame[led] = hsv(col / LED_COLUMNS * 0.85 + t * 0.25, 1.0, 1.0)

    elif name == "wave":
        for led, row, col in cells:
            phase = (col / LED_COLUMNS) - t * 0.35
            k = 0.5 + 0.5 * math.sin(2 * math.pi * phase)
            frame[led] = mix(color, color2, k)

    elif name == "chase":
        head = (t * 14.0) % LED_COLUMNS
        for led, row, col in cells:
            dist = min(abs(col - head), LED_COLUMNS - abs(col - head))
            level = max(0.0, 1.0 - dist / 2.2)
            frame[led] = scale(color, 0.06 + 0.94 * level)

    elif name == "sparkle":
        rng = random.Random(int(t * 12))
        frame = [scale(color, 0.14)] * LED_COUNT
        for _ in range(12):
            led = cells[rng.randrange(len(cells))][0]
            frame[led] = color2

    elif name == "ripple":
        speed_k = max(0.05, speed)
        events = ripples or []
        base = scale(color, 0.20)  # Main-color floor is 20% of the selected brightness.
        frame = [base] * LED_COUNT
        for led, row, col in cells:
            acc = 0.0
            for (ecol, erow, age) in events:
                age = age * speed_k
                if age < 0 or age >= RIPPLE_LIFETIME:
                    continue
                front = age * 12.0
                dx = col - ecol
                dy = (row - erow) * 1.35
                dist = math.sqrt(dx * dx + dy * dy)
                # One soft annulus per press, with no trailing repeated rings.
                ring = math.exp(-((dist - front) ** 2) / (2 * 0.8 ** 2))
                fade = (1.0 - age / RIPPLE_LIFETIME) ** 1.4
                acc = max(acc, ring * fade)
            frame[led] = mix(base, color2, acc)

    elif name == "audio":
        lv = levels or [0.0] * LED_COLUMNS
        # Separate cells respond to different bands; beats swap the lit checkerboard.
        pulse = max(0.0, min(1.0, max(lv) if audio_pulse is None else audio_pulse))
        energy = max(0.0, min(1.0, max(lv) if audio_energy is None else audio_energy))
        for led, row, col in cells:
            level = lv[min(len(lv) - 1, int(col * len(lv) / LED_COLUMNS))]
            if audio_style == "radial":
                cx, cy = audio_center or ((LED_COLUMNS - 1) / 2, (physical_rows - 1) / 2)
                distance = math.hypot(col - cx, (row - cy) * 1.35)
                falloff = math.exp(-distance / 2.8)
                tint = mix(color, color2, min(1, distance / 7))
                strength = (.72 * pulse + .20 * level ** 1.6 + .08 * energy) * falloff
            else:
                band = (col * 5 + row * 3) % len(lv)
                level = max(0, min(1, lv[band]))
                parity = (col + row) % 2
                mask = 1.0 if parity == audio_beat % 2 else .02
                tint = mix(color, color2, band / max(1, len(lv) - 1))
                strength = (.42 * pulse + .50 * level ** 1.6 + .08 * energy) * mask
            frame[led] = scale(tint, strength)

    elif name == "meteor":
        head = (t * 0.32) % 1.5 - 0.25
        for led, row, col in cells:
            x = col / (LED_COLUMNS - 1)
            d = head - x
            if d >= 0:
                tail = math.exp(-d * 7.0)
            else:
                tail = math.exp(d * 25.0) * 0.6
            wobble = 0.75 + 0.25 * math.sin(row * 1.7 + t * 3)
            frame[led] = scale(mix(color, color2, 1 - tail), tail * wobble)

    elif name == "plasma":
        for led, row, col in cells:
            x = col / LED_COLUMNS
            y = row / physical_rows
            v = (math.sin(x * 6.0 + t) + math.sin(y * 9.0 - t * 1.3)
                 + math.sin((x + y) * 5.0 + t * 0.7))
            v = (v + 3.0) / 6.0
            frame[led] = hsv(0.55 + v * 0.3, 0.85, 0.25 + 0.75 * v)

    elif name == "fire":
        for led, row, col in cells:
            flicker = _hash(col * 3.1 + row * 7.7 + math.floor(t * 12) * 1.37)
            heat = (1.0 - row / physical_rows) ** 1.4 * (0.55 + 0.55 * flicker)
            heat = max(0.0, min(1.0, heat))
            frame[led] = mix((30, 0, 0), color, heat)
            frame[led] = scale(frame[led], 0.25 + 0.75 * heat)

    elif name == "aurora":
        for led, row, col in cells:
            x = col / LED_COLUMNS
            y = row / physical_rows
            wave = math.sin(x * 3.2 + math.sin(t * 0.4) * 1.8 + y * 2.4 + t * 0.55)
            curtain = 0.5 + 0.5 * math.sin(y * 5.0 - t * 0.8 + x * 2.0)
            v = max(0.0, wave) * (0.35 + 0.65 * curtain)
            frame[led] = mix(scale(color2, 0.12), color, v)
            frame[led] = scale(frame[led], 0.35 + 0.65 * v)

    elif name == "ai":
        if getattr(expr, "is_program", False):
            frame = expr.frame(cells, t, physical_rows, max(.05,speed), color, color2, key_state,
                               {"levels":levels, "pulse":audio_pulse or 0, "energy":audio_energy or 0, "beat":audio_beat})
        elif expr is None:
            frame = [scale(color, 0.12)] * LED_COUNT
        else:
            for led, row, col in cells:
                frame[led] = expr(col / (LED_COLUMNS - 1), row / max(1, physical_rows - 1),
                                  led, row, col, t, rows=physical_rows)

    elif name == "typing":
        now = t
        keys = active_keys or {}
        for led, row, col in cells:
            boost = 0.0
            key = (row + ROW_OFFSET) * LED_COLUMNS + col + 1
            if key in keys:
                age = now - keys[key]
                if age < 0.9:
                    boost = 1.0 - age / 0.9
            frame[led] = mix(scale(color, 0.06), color2, boost)

    else:
        raise ValueError(f"unknown effect: {name}")

    if brightness < 1.0:
        frame = [scale(c, brightness) for c in frame]
    return frame


# ------------------------------------------------------------------- engine
class Engine:
    """Runs an effect on a background thread and streams frames to the keyboard."""

    def __init__(self, keyboard, fps: float = 45.0):
        self.keyboard = keyboard
        self.fps = fps
        self.params: dict = {
            "name": "static",
            "color": (255, 60, 60),
            "color2": (0, 120, 255),
            "speed": 1.0,
            "brightness": 1.0,
            "paint": None,
            "paint_mask": None,
            "ripples": (),
            "levels": None,
            "expr": None,
            "active_keys": {},
            "rows": None,
            "row_offset": None,
        }
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.error: str | None = None
        self.frames_sent = 0
        self.running = False
        self.t0 = time.time()

    def update(self, **params) -> None:
        with self._lock:
            self.params.update(params)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.params)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.t0 = time.perf_counter()
        self._thread = threading.Thread(target=self._run, name="kb-engine", daemon=True)
        self._thread.start()
        self.running = True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None
        self.running = False

    def _run(self) -> None:
        period = 1.0 / max(5.0, self.fps)
        while not self._stop.is_set():
            started = time.perf_counter()
            params = self.snapshot()
            try:
                frame = render(
                    params["name"],
                    time.perf_counter() - self.t0,
                    color=params["color"],
                    color2=params["color2"],
                    speed=params["speed"],
                    brightness=params["brightness"],
                    paint=params["paint"],
                    paint_mask=params["paint_mask"],
                    ripples=params["ripples"],
                    levels=params["levels"],
                    expr=params["expr"],
                    active_keys=params["active_keys"],
                    rows=params.get("rows"),
                    row_offset=params.get("row_offset"),
                )
                self.keyboard.send_frame(frame)
                self.frames_sent += 1
                self.error = None
            except Exception as exc:  # noqa: BLE001
                self.error = f"{type(exc).__name__}: {exc}"
                time.sleep(0.5)
            spent = time.perf_counter() - started
            time.sleep(max(0.0, period - spent))
