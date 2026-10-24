"""132-slot RGB wire frame for WIN60/68 HE: index = frame_row*22 + col.

Both supported standard models have five physical rows at wire rows 1..5.
WIN68 adds navigation columns, not a sixth/F-key row. Many of the 132 slots
are unpopulated; the exact 61/68 physical-key indices live in keymap_data.py.
Logical grid labels below are editing coordinates, not Windows keys or the
vendor's physical-key list. Never infer VK mappings from this dense grid.
"""

from __future__ import annotations

LED_COLUMNS = 22
FRAME_ROWS = 6
ROW_OFFSET = 1                      # frame row of physical row 0
LED_ROWS = FRAME_ROWS - ROW_OFFSET  # 5 physical rows
LED_COUNT = FRAME_ROWS * LED_COLUMNS  # slots per frame (132)
LEDS_PER_PACKET = 18

ROW_LABELS = ("Esc/数字", "QWERTY", "ASDF", "ZXCV", "底行")


def led_index(row: int, col: int) -> int:
    """Frame index for physical (row, col)."""
    if not (0 <= row < LED_ROWS and 0 <= col < LED_COLUMNS):
        raise IndexError((row, col))
    return (row + ROW_OFFSET) * LED_COLUMNS + col


def grid_pos(led: int) -> tuple[int, int]:
    """Physical (row, col) for a frame index; row -1 = unused frame row."""
    row, col = divmod(led, LED_COLUMNS)
    return row - ROW_OFFSET, col


def is_real_led(led: int) -> bool:
    row, _ = divmod(led, LED_COLUMNS)
    return row >= ROW_OFFSET


# ---------------------------------------------------------------- key tables
# row -> logical key ids (1-based per cell); row 0 of the frame is unused.
LED_KEY_LAYOUT: tuple[tuple[int, ...], ...] = tuple(
    tuple(-1 for _ in range(LED_COLUMNS)) if row < ROW_OFFSET
    else tuple((row - ROW_OFFSET) * LED_COLUMNS + col + 1 for col in range(LED_COLUMNS))
    for row in range(FRAME_ROWS)
)

KEY_TO_LED: dict[int, int] = {
    key_id: row * LED_COLUMNS + col
    for row, row_ids in enumerate(LED_KEY_LAYOUT)
    for col, key_id in enumerate(row_ids)
    if key_id != -1
}

LED_TO_KEY: dict[int, int] = {led: key for key, led in KEY_TO_LED.items()}

# every physical LED only feeds itself; frame row 0 stays dark
LED_GAP_SOURCES: tuple[int, ...] = tuple(
    led if is_real_led(led) else -1 for led in range(LED_COUNT)
)


def key_label(key_id: int) -> str:
    if key_id <= 0:
        return ""
    row, col = divmod(key_id - 1, LED_COLUMNS)
    return f"{row + 1}-{col + 1}"


_CELL_CACHE: dict[tuple[int, int], list[tuple[int, int, int]]] = {}


def cells(rows: int | None = None, row_offset: int | None = None) -> list[tuple[int, int, int]]:
    """(led, row, col) for every physical LED - parameterised for 60%/65% boards."""
    rows = LED_ROWS if rows is None else int(rows)
    offset = ROW_OFFSET if row_offset is None else int(row_offset)
    key = (rows, offset)
    cached = _CELL_CACHE.get(key)
    if cached is None:
        cached = [((r + offset) * LED_COLUMNS + c, r, c) for r in range(rows) for c in range(LED_COLUMNS)]
        _CELL_CACHE[key] = cached
    return cached


def expand_gaps(frame: list[tuple[int, int, int]], skip: set[int] | None = None):
    """Kept for API compatibility - every physical LED already has its own slot."""
    return frame


def blank_frame() -> list[tuple[int, int, int]]:
    return [(0, 0, 0)] * LED_COUNT


def frame_from_keys(colors: dict[int, tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Build a frame from {logical key id: rgb}."""
    frame = blank_frame()
    for key_id, rgb in colors.items():
        led = KEY_TO_LED.get(key_id)
        if led is not None:
            frame[led] = rgb
    return frame
