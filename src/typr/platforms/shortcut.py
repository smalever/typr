"""Shared strict single-chord PortableText grammar (no desktop/device access)."""

import re
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence

# Deliberately bounded cross-platform set. OEM punctuation/layout keys are not
# silently converted to unrelated physical keys.
_KEYS = {
    "Space": (0x20, 57), "Return": (0x0D, 28), "Enter": (0x0D, 28),
    "Esc": (0x1B, 1), "Tab": (0x09, 15), "Backspace": (0x08, 14),
    "Del": (0x2E, 111), "Ins": (0x2D, 110), "Home": (0x24, 102),
    "End": (0x23, 107), "PgUp": (0x21, 104), "PgDown": (0x22, 109),
    "Left": (0x25, 105), "Right": (0x27, 106), "Up": (0x26, 103),
    "Down": (0x28, 108),
}
_LETTER_CODES = (30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50,
                 49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44)
_KEYS.update({chr(65 + i): (65 + i, code) for i, code in enumerate(_LETTER_CODES)})
_KEYS.update({str(i): (48 + i, 11 if i == 0 else i + 1) for i in range(10)})
_KEYS.update({f"F{i}": (0x6F + i, 58 + i if i <= 10 else 76 + i)
              for i in range(1, 13)})


@dataclass(frozen=True)
class Shortcut:
    text: str
    modifiers: frozenset[str]
    windows_vk: int
    linux_code: int


def parse_shortcut(text: str) -> Shortcut:
    """Reject empty, invalid, multi-chord and unsupported combinations explicitly."""
    # Qt silently drops a trailing empty chord. Comma as the target key is
    # different ("," / "Ctrl+,") and must reach the supported-key check below.
    if "," in text and not re.fullmatch(r"(?i)(?:(?:Ctrl|Alt|Shift|Meta)\+)*,", text.strip()):
        raise ValueError("Hotkey must contain exactly one non-empty PortableText chord")
    sequence = QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1:
        raise ValueError("Hotkey must contain exactly one PortableText chord")
    combination = sequence[0]
    key = combination.key()
    if key == Qt.Key.Key_unknown or not int(key):
        raise ValueError("Invalid hotkey")
    modifiers = combination.keyboardModifiers()
    allowed = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
               | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.MetaModifier)
    if modifiers.value & ~allowed.value:
        raise ValueError("Unsupported hotkey modifiers")
    name = QKeySequence(int(key)).toString(QKeySequence.SequenceFormat.PortableText)
    if name not in _KEYS:
        raise ValueError(f"Unsupported hotkey key: {name}")
    groups = frozenset(name for flag, name in (
        (Qt.KeyboardModifier.ControlModifier, "ctrl"),
        (Qt.KeyboardModifier.AltModifier, "alt"),
        (Qt.KeyboardModifier.ShiftModifier, "shift"),
        (Qt.KeyboardModifier.MetaModifier, "meta"),
    ) if modifiers & flag)
    vk, code = _KEYS[name]
    return Shortcut(sequence.toString(QKeySequence.SequenceFormat.PortableText), groups, vk, code)
