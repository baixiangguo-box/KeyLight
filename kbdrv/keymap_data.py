"""Per-model firmware indices from the vendor key tables.

Source: hed.aulacn.com config/keys/SI2825HEARGB.json and SI2828HEARGB.json,
archived in MrWhosNexus/Aether-HE commit 99bee574abb67aea5912c5b513a69a3408c7683d.
Wire indices are not keycap-width projections or sequential key IDs.
"""

KEYMAPS = {
  "win60": [
    {
      "code": "Escape",
      "vk": 27,
      "led": 22,
      "label": "Esc",
      "x": 10,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit1",
      "vk": 49,
      "led": 23,
      "label": "1!",
      "x": 48,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit2",
      "vk": 50,
      "led": 24,
      "label": "2@",
      "x": 86,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit3",
      "vk": 51,
      "led": 25,
      "label": "3#",
      "x": 124,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit4",
      "vk": 52,
      "led": 26,
      "label": "4$",
      "x": 162,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit5",
      "vk": 53,
      "led": 27,
      "label": "5%",
      "x": 200,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit6",
      "vk": 54,
      "led": 28,
      "label": "6^",
      "x": 238,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit7",
      "vk": 55,
      "led": 29,
      "label": "7&",
      "x": 276,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit8",
      "vk": 56,
      "led": 30,
      "label": "8*",
      "x": 314,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit9",
      "vk": 57,
      "led": 31,
      "label": "9(",
      "x": 352,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit0",
      "vk": 48,
      "led": 32,
      "label": "0)",
      "x": 390,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Minus",
      "vk": 189,
      "led": 33,
      "label": "-_",
      "x": 428,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Equal",
      "vk": 187,
      "led": 34,
      "label": "=+",
      "x": 466,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Backspace",
      "vk": 8,
      "led": 36,
      "label": "Back",
      "x": 504,
      "y": 15,
      "width": 73,
      "height": 35
    },
    {
      "code": "Tab",
      "vk": 9,
      "led": 44,
      "label": "Tab",
      "x": 10,
      "y": 53,
      "width": 54,
      "height": 35
    },
    {
      "code": "KeyQ",
      "vk": 81,
      "led": 45,
      "label": "Q",
      "x": 67,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyW",
      "vk": 87,
      "led": 46,
      "label": "W",
      "x": 105,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyE",
      "vk": 69,
      "led": 47,
      "label": "E",
      "x": 143,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyR",
      "vk": 82,
      "led": 48,
      "label": "R",
      "x": 181,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyT",
      "vk": 84,
      "led": 49,
      "label": "T",
      "x": 219,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyY",
      "vk": 89,
      "led": 50,
      "label": "Y",
      "x": 257,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyU",
      "vk": 85,
      "led": 51,
      "label": "U",
      "x": 295,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyI",
      "vk": 73,
      "led": 52,
      "label": "I",
      "x": 333,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyO",
      "vk": 79,
      "led": 53,
      "label": "O",
      "x": 371,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyP",
      "vk": 80,
      "led": 54,
      "label": "P",
      "x": 409,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "BracketLeft",
      "vk": 219,
      "led": 55,
      "label": "[{",
      "x": 447,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "BracketRight",
      "vk": 221,
      "led": 56,
      "label": "]}",
      "x": 485,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "Backslash",
      "vk": 220,
      "led": 58,
      "label": "\\|",
      "x": 523,
      "y": 53,
      "width": 54,
      "height": 35
    },
    {
      "code": "CapsLock",
      "vk": 20,
      "led": 66,
      "label": "Caps",
      "x": 10,
      "y": 91,
      "width": 63,
      "height": 35
    },
    {
      "code": "KeyA",
      "vk": 65,
      "led": 68,
      "label": "A",
      "x": 76,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyS",
      "vk": 83,
      "led": 69,
      "label": "S",
      "x": 114,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyD",
      "vk": 68,
      "led": 70,
      "label": "D",
      "x": 152,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyF",
      "vk": 70,
      "led": 71,
      "label": "F",
      "x": 190,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyG",
      "vk": 71,
      "led": 72,
      "label": "G",
      "x": 228,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyH",
      "vk": 72,
      "led": 73,
      "label": "H",
      "x": 266,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyJ",
      "vk": 74,
      "led": 74,
      "label": "J",
      "x": 304,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyK",
      "vk": 75,
      "led": 75,
      "label": "K",
      "x": 342,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyL",
      "vk": 76,
      "led": 76,
      "label": "L",
      "x": 380,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "Semicolon",
      "vk": 186,
      "led": 77,
      "label": ";:",
      "x": 418,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "Quote",
      "vk": 222,
      "led": 78,
      "label": "\" '",
      "x": 456,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "Enter",
      "vk": 13,
      "led": 80,
      "label": "Enter",
      "x": 494,
      "y": 91,
      "width": 83,
      "height": 35
    },
    {
      "code": "ShiftLeft",
      "vk": 160,
      "led": 88,
      "label": "L-Shift",
      "x": 10,
      "y": 129,
      "width": 83,
      "height": 35
    },
    {
      "code": "KeyZ",
      "vk": 90,
      "led": 90,
      "label": "Z",
      "x": 96,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyX",
      "vk": 88,
      "led": 91,
      "label": "X",
      "x": 134,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyC",
      "vk": 67,
      "led": 92,
      "label": "C",
      "x": 172,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyV",
      "vk": 86,
      "led": 93,
      "label": "V",
      "x": 210,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyB",
      "vk": 66,
      "led": 94,
      "label": "B",
      "x": 248,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyN",
      "vk": 78,
      "led": 95,
      "label": "N",
      "x": 286,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyM",
      "vk": 77,
      "led": 96,
      "label": "M",
      "x": 324,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "Comma",
      "vk": 188,
      "led": 97,
      "label": ",<",
      "x": 362,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "Period",
      "vk": 190,
      "led": 98,
      "label": ".>",
      "x": 400,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "Slash",
      "vk": 191,
      "led": 99,
      "label": "/?",
      "x": 438,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "ShiftRight",
      "vk": 161,
      "led": 100,
      "label": "R-Shift",
      "x": 476,
      "y": 129,
      "width": 101,
      "height": 35
    },
    {
      "code": "ControlLeft",
      "vk": 162,
      "led": 110,
      "label": "L-Ctrl",
      "x": 10,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "MetaLeft",
      "vk": 91,
      "led": 111,
      "label": "L-Win",
      "x": 60,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "AltLeft",
      "vk": 164,
      "led": 112,
      "label": "L-Alt",
      "x": 110,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "Space",
      "vk": 32,
      "led": 116,
      "label": "Space",
      "x": 160,
      "y": 167,
      "width": 217,
      "height": 35
    },
    {
      "code": "AltRight",
      "vk": 165,
      "led": 119,
      "label": "R-Alt",
      "x": 380,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "ContextMenu",
      "vk": 93,
      "led": 120,
      "label": "Menu",
      "x": 430,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "ControlRight",
      "vk": 163,
      "led": 121,
      "label": "R-Ctrl",
      "x": 480,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "KeyFn",
      "vk": None,
      "led": 122,
      "label": "Fn",
      "x": 530,
      "y": 167,
      "width": 47,
      "height": 35
    }
  ],
  "win68": [
    {
      "code": "Escape",
      "vk": 27,
      "led": 22,
      "label": "Esc",
      "x": 10,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit1",
      "vk": 49,
      "led": 23,
      "label": "1!",
      "x": 48,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit2",
      "vk": 50,
      "led": 24,
      "label": "2@",
      "x": 86,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit3",
      "vk": 51,
      "led": 25,
      "label": "3#",
      "x": 124,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit4",
      "vk": 52,
      "led": 26,
      "label": "4$",
      "x": 162,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit5",
      "vk": 53,
      "led": 27,
      "label": "5%",
      "x": 200,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit6",
      "vk": 54,
      "led": 28,
      "label": "6^",
      "x": 238,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit7",
      "vk": 55,
      "led": 29,
      "label": "7&",
      "x": 276,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit8",
      "vk": 56,
      "led": 30,
      "label": "8*",
      "x": 314,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit9",
      "vk": 57,
      "led": 31,
      "label": "9(",
      "x": 352,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Digit0",
      "vk": 48,
      "led": 32,
      "label": "0)",
      "x": 390,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Minus",
      "vk": 189,
      "led": 33,
      "label": "-_",
      "x": 428,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Equal",
      "vk": 187,
      "led": 34,
      "label": "=+",
      "x": 466,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Backspace",
      "vk": 8,
      "led": 36,
      "label": "Back",
      "x": 504,
      "y": 15,
      "width": 73,
      "height": 35
    },
    {
      "code": "Insert",
      "vk": 45,
      "led": 38,
      "label": "Ins",
      "x": 580,
      "y": 15,
      "width": 35,
      "height": 35
    },
    {
      "code": "Tab",
      "vk": 9,
      "led": 44,
      "label": "Tab",
      "x": 10,
      "y": 53,
      "width": 54,
      "height": 35
    },
    {
      "code": "KeyQ",
      "vk": 81,
      "led": 45,
      "label": "Q",
      "x": 67,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyW",
      "vk": 87,
      "led": 46,
      "label": "W",
      "x": 105,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyE",
      "vk": 69,
      "led": 47,
      "label": "E",
      "x": 143,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyR",
      "vk": 82,
      "led": 48,
      "label": "R",
      "x": 181,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyT",
      "vk": 84,
      "led": 49,
      "label": "T",
      "x": 219,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyY",
      "vk": 89,
      "led": 50,
      "label": "Y",
      "x": 257,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyU",
      "vk": 85,
      "led": 51,
      "label": "U",
      "x": 295,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyI",
      "vk": 73,
      "led": 52,
      "label": "I",
      "x": 333,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyO",
      "vk": 79,
      "led": 53,
      "label": "O",
      "x": 371,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyP",
      "vk": 80,
      "led": 54,
      "label": "P",
      "x": 409,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "BracketLeft",
      "vk": 219,
      "led": 55,
      "label": "[{",
      "x": 447,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "BracketRight",
      "vk": 221,
      "led": 56,
      "label": "]}",
      "x": 485,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "Backslash",
      "vk": 220,
      "led": 58,
      "label": "\\|",
      "x": 523,
      "y": 53,
      "width": 54,
      "height": 35
    },
    {
      "code": "Delete",
      "vk": 46,
      "led": 60,
      "label": "Del",
      "x": 580,
      "y": 53,
      "width": 35,
      "height": 35
    },
    {
      "code": "CapsLock",
      "vk": 20,
      "led": 66,
      "label": "Caps",
      "x": 10,
      "y": 91,
      "width": 63,
      "height": 35
    },
    {
      "code": "KeyA",
      "vk": 65,
      "led": 68,
      "label": "A",
      "x": 76,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyS",
      "vk": 83,
      "led": 69,
      "label": "S",
      "x": 114,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyD",
      "vk": 68,
      "led": 70,
      "label": "D",
      "x": 152,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyF",
      "vk": 70,
      "led": 71,
      "label": "F",
      "x": 190,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyG",
      "vk": 71,
      "led": 72,
      "label": "G",
      "x": 228,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyH",
      "vk": 72,
      "led": 73,
      "label": "H",
      "x": 266,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyJ",
      "vk": 74,
      "led": 74,
      "label": "J",
      "x": 304,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyK",
      "vk": 75,
      "led": 75,
      "label": "K",
      "x": 342,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyL",
      "vk": 76,
      "led": 76,
      "label": "L",
      "x": 380,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "Semicolon",
      "vk": 186,
      "led": 77,
      "label": ";:",
      "x": 418,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "Quote",
      "vk": 222,
      "led": 78,
      "label": "\" '",
      "x": 456,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "Enter",
      "vk": 13,
      "led": 80,
      "label": "Enter",
      "x": 494,
      "y": 91,
      "width": 83,
      "height": 35
    },
    {
      "code": "PageUp",
      "vk": 33,
      "led": 82,
      "label": "PgUp",
      "x": 580,
      "y": 91,
      "width": 35,
      "height": 35
    },
    {
      "code": "ShiftLeft",
      "vk": 160,
      "led": 88,
      "label": "L-Shift",
      "x": 10,
      "y": 129,
      "width": 83,
      "height": 35
    },
    {
      "code": "KeyZ",
      "vk": 90,
      "led": 90,
      "label": "Z",
      "x": 96,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyX",
      "vk": 88,
      "led": 91,
      "label": "X",
      "x": 134,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyC",
      "vk": 67,
      "led": 92,
      "label": "C",
      "x": 172,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyV",
      "vk": 86,
      "led": 93,
      "label": "V",
      "x": 210,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyB",
      "vk": 66,
      "led": 94,
      "label": "B",
      "x": 248,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyN",
      "vk": 78,
      "led": 95,
      "label": "N",
      "x": 286,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyM",
      "vk": 77,
      "led": 96,
      "label": "M",
      "x": 324,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "Comma",
      "vk": 188,
      "led": 97,
      "label": ",<",
      "x": 362,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "Period",
      "vk": 190,
      "led": 98,
      "label": ".>",
      "x": 400,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "Slash",
      "vk": 191,
      "led": 99,
      "label": "/?",
      "x": 438,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "ShiftRight",
      "vk": 161,
      "led": 101,
      "label": "R-Shift",
      "x": 476,
      "y": 129,
      "width": 63,
      "height": 35
    },
    {
      "code": "ArrowUp",
      "vk": 38,
      "led": 103,
      "label": "Up",
      "x": 542,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "PageDown",
      "vk": 34,
      "led": 104,
      "label": "PgDn",
      "x": 580,
      "y": 129,
      "width": 35,
      "height": 35
    },
    {
      "code": "ControlLeft",
      "vk": 162,
      "led": 110,
      "label": "L-Ctrl",
      "x": 10,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "MetaLeft",
      "vk": 91,
      "led": 111,
      "label": "L-Win",
      "x": 60,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "AltLeft",
      "vk": 164,
      "led": 112,
      "label": "L-Alt",
      "x": 110,
      "y": 167,
      "width": 47,
      "height": 35
    },
    {
      "code": "Space",
      "vk": 32,
      "led": 116,
      "label": "Space",
      "x": 160,
      "y": 167,
      "width": 227,
      "height": 35
    },
    {
      "code": "AltRight",
      "vk": 165,
      "led": 119,
      "label": "R-Alt",
      "x": 390,
      "y": 167,
      "width": 35,
      "height": 35
    },
    {
      "code": "KeyFn",
      "vk": None,
      "led": 121,
      "label": "Fn",
      "x": 428,
      "y": 167,
      "width": 35,
      "height": 35
    },
    {
      "code": "ControlRight",
      "vk": 163,
      "led": 122,
      "label": "R-Ctrl",
      "x": 466,
      "y": 167,
      "width": 35,
      "height": 35
    },
    {
      "code": "ArrowLeft",
      "vk": 37,
      "led": 124,
      "label": "Left",
      "x": 504,
      "y": 167,
      "width": 35,
      "height": 35
    },
    {
      "code": "ArrowDown",
      "vk": 40,
      "led": 125,
      "label": "Down",
      "x": 542,
      "y": 167,
      "width": 35,
      "height": 35
    },
    {
      "code": "ArrowRight",
      "vk": 39,
      "led": 126,
      "label": "Right",
      "x": 580,
      "y": 167,
      "width": 35,
      "height": 35
    }
  ]
}

