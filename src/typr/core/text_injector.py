"""Text injection using evdev UInput for Wayland/X11."""

import os
import shutil
import subprocess
import time
from typing import Optional

from PyQt6.QtCore import QTimer

from typr.utils.logger import logger

try:
    from evdev import UInput, ecodes

    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    logger.warning("evdev not available for text injection")


# Character to key code mapping (US keyboard layout)
CHAR_TO_KEY = {
    "a": (ecodes.KEY_A, False),
    "b": (ecodes.KEY_B, False),
    "c": (ecodes.KEY_C, False),
    "d": (ecodes.KEY_D, False),
    "e": (ecodes.KEY_E, False),
    "f": (ecodes.KEY_F, False),
    "g": (ecodes.KEY_G, False),
    "h": (ecodes.KEY_H, False),
    "i": (ecodes.KEY_I, False),
    "j": (ecodes.KEY_J, False),
    "k": (ecodes.KEY_K, False),
    "l": (ecodes.KEY_L, False),
    "m": (ecodes.KEY_M, False),
    "n": (ecodes.KEY_N, False),
    "o": (ecodes.KEY_O, False),
    "p": (ecodes.KEY_P, False),
    "q": (ecodes.KEY_Q, False),
    "r": (ecodes.KEY_R, False),
    "s": (ecodes.KEY_S, False),
    "t": (ecodes.KEY_T, False),
    "u": (ecodes.KEY_U, False),
    "v": (ecodes.KEY_V, False),
    "w": (ecodes.KEY_W, False),
    "x": (ecodes.KEY_X, False),
    "y": (ecodes.KEY_Y, False),
    "z": (ecodes.KEY_Z, False),
    "A": (ecodes.KEY_A, True),
    "B": (ecodes.KEY_B, True),
    "C": (ecodes.KEY_C, True),
    "D": (ecodes.KEY_D, True),
    "E": (ecodes.KEY_E, True),
    "F": (ecodes.KEY_F, True),
    "G": (ecodes.KEY_G, True),
    "H": (ecodes.KEY_H, True),
    "I": (ecodes.KEY_I, True),
    "J": (ecodes.KEY_J, True),
    "K": (ecodes.KEY_K, True),
    "L": (ecodes.KEY_L, True),
    "M": (ecodes.KEY_M, True),
    "N": (ecodes.KEY_N, True),
    "O": (ecodes.KEY_O, True),
    "P": (ecodes.KEY_P, True),
    "Q": (ecodes.KEY_Q, True),
    "R": (ecodes.KEY_R, True),
    "S": (ecodes.KEY_S, True),
    "T": (ecodes.KEY_T, True),
    "U": (ecodes.KEY_U, True),
    "V": (ecodes.KEY_V, True),
    "W": (ecodes.KEY_W, True),
    "X": (ecodes.KEY_X, True),
    "Y": (ecodes.KEY_Y, True),
    "Z": (ecodes.KEY_Z, True),
    "0": (ecodes.KEY_0, False),
    "1": (ecodes.KEY_1, False),
    "2": (ecodes.KEY_2, False),
    "3": (ecodes.KEY_3, False),
    "4": (ecodes.KEY_4, False),
    "5": (ecodes.KEY_5, False),
    "6": (ecodes.KEY_6, False),
    "7": (ecodes.KEY_7, False),
    "8": (ecodes.KEY_8, False),
    "9": (ecodes.KEY_9, False),
    " ": (ecodes.KEY_SPACE, False),
    "\n": (ecodes.KEY_ENTER, False),
    "\t": (ecodes.KEY_TAB, False),
    ".": (ecodes.KEY_DOT, False),
    ",": (ecodes.KEY_COMMA, False),
    "!": (ecodes.KEY_1, True),
    "@": (ecodes.KEY_2, True),
    "#": (ecodes.KEY_3, True),
    "$": (ecodes.KEY_4, True),
    "%": (ecodes.KEY_5, True),
    "^": (ecodes.KEY_6, True),
    "&": (ecodes.KEY_7, True),
    "*": (ecodes.KEY_8, True),
    "(": (ecodes.KEY_9, True),
    ")": (ecodes.KEY_0, True),
    "-": (ecodes.KEY_MINUS, False),
    "_": (ecodes.KEY_MINUS, True),
    "=": (ecodes.KEY_EQUAL, False),
    "+": (ecodes.KEY_EQUAL, True),
    "[": (ecodes.KEY_LEFTBRACE, False),
    "]": (ecodes.KEY_RIGHTBRACE, False),
    "{": (ecodes.KEY_LEFTBRACE, True),
    "}": (ecodes.KEY_RIGHTBRACE, True),
    "\\": (ecodes.KEY_BACKSLASH, False),
    "|": (ecodes.KEY_BACKSLASH, True),
    ";": (ecodes.KEY_SEMICOLON, False),
    ":": (ecodes.KEY_SEMICOLON, True),
    "'": (ecodes.KEY_APOSTROPHE, False),
    '"': (ecodes.KEY_APOSTROPHE, True),
    "`": (ecodes.KEY_GRAVE, False),
    "~": (ecodes.KEY_GRAVE, True),
    "/": (ecodes.KEY_SLASH, False),
    "?": (ecodes.KEY_SLASH, True),
    "<": (ecodes.KEY_COMMA, True),
    ">": (ecodes.KEY_DOT, True),
} if EVDEV_AVAILABLE else {}


class TextInjector:
    """Injects text using evdev UInput (works on Wayland and X11)."""

    def __init__(self, typing_delay: int = 0):
        """Initialize text injector.

        Args:
            typing_delay: Delay between keystrokes in milliseconds.
        """
        self.typing_delay = typing_delay
        self._ui: Optional["UInput"] = None
        self._available = False
        self._clipboard_restore_timer: Optional[QTimer] = None
        self._clipboard_process: Optional[subprocess.Popen] = None
        self._init_uinput()

    def _init_uinput(self) -> None:
        """Initialize UInput device."""
        if not EVDEV_AVAILABLE:
            logger.error("evdev not available")
            return

        try:
            # Create a virtual keyboard device
            self._ui = UInput(name="typr-keyboard")
            self._available = True
            logger.info("UInput text injector initialized")
        except PermissionError:
            logger.error("No permission for /dev/uinput. Add user to 'input' group.")
        except Exception as e:
            logger.error(f"Failed to create UInput: {e}")

    def is_available(self) -> bool:
        """Check if text injection is available."""
        return self._available and self._ui is not None

    def type_text(self, text: str) -> bool:
        """Type text at current cursor position.

        Args:
            text: The text to type.

        Returns:
            True if successful, False otherwise.
        """
        if not text:
            return True

        if not self.is_available():
            logger.error("Text injector not available")
            return False

        try:
            if self._requires_clipboard_paste(text):
                return self._paste_text(text)

            delay_sec = self.typing_delay / 1000.0 if self.typing_delay > 0 else 0.001

            for char in text:
                if char in CHAR_TO_KEY:
                    key_code, shift = CHAR_TO_KEY[char]
                    self._type_key(key_code, shift)
                else:
                    # Skip unsupported characters
                    logger.debug(f"Skipping unsupported character: {repr(char)}")

                if delay_sec > 0:
                    time.sleep(delay_sec)

            logger.info(f"Typed {len(text)} characters")
            return True

        except Exception as e:
            logger.error(f"Text injection failed: {e}")
            return False

    def _requires_clipboard_paste(self, text: str) -> bool:
        """Return True when text contains characters we cannot type directly."""
        return any(char not in CHAR_TO_KEY for char in text)

    def _paste_text(self, text: str) -> bool:
        """Paste Unicode text through a desktop-specific clipboard backend."""
        backend = self._detect_clipboard_backend()
        if backend is None:
            logger.error("No clipboard backend available for Unicode paste")
            return False

        process = self._spawn_clipboard_backend(backend, text)
        if process is None:
            return False

        self._terminate_clipboard_process()
        self._clipboard_process = process

        time.sleep(0.12)
        if "\n" in text:
            self._type_modified_key(ecodes.KEY_INSERT, shift=True)
        else:
            self._type_modified_key(ecodes.KEY_V, ctrl=True)

        self._schedule_clipboard_release()
        logger.info(f"Pasted {len(text)} characters through {backend}")
        return True

    def _schedule_clipboard_release(self, delay_ms: int = 1500) -> None:
        """Release clipboard backend after targets have had time to consume the paste."""
        if self._clipboard_restore_timer is None:
            self._clipboard_restore_timer = QTimer()
            self._clipboard_restore_timer.setSingleShot(True)
            self._clipboard_restore_timer.timeout.connect(self._on_release_clipboard_timeout)

        self._clipboard_restore_timer.start(delay_ms)

    def _on_release_clipboard_timeout(self) -> None:
        """Release the clipboard helper process after paste completes."""
        self._terminate_clipboard_process()

    def _detect_clipboard_backend(self) -> Optional[str]:
        """Pick the best available clipboard backend for the current session."""
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
            return "wl-copy"
        if os.environ.get("DISPLAY"):
            if shutil.which("xclip"):
                return "xclip"
            if shutil.which("xsel"):
                return "xsel"
        return None

    def _spawn_clipboard_backend(self, backend: str, text: str) -> Optional[subprocess.Popen]:
        """Start a clipboard backend process and feed it text."""
        commands = {
            "wl-copy": ["wl-copy", "--type", "text/plain;charset=utf-8", "--foreground"],
            "xclip": ["xclip", "-selection", "clipboard", "-in"],
            "xsel": ["xsel", "--clipboard", "--input"],
        }
        command = commands.get(backend)
        if command is None:
            logger.error(f"Unsupported clipboard backend: {backend}")
            return None

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=False,
            )
            assert process.stdin is not None
            process.stdin.write(text.encode("utf-8"))
            process.stdin.close()
            return process
        except Exception as e:
            logger.error(f"Failed to start clipboard backend {backend}: {e}")
            return None

    def _terminate_clipboard_process(self) -> None:
        """Stop any running clipboard helper process."""
        if self._clipboard_process is None:
            return
        try:
            if self._clipboard_process.poll() is None:
                self._clipboard_process.terminate()
                self._clipboard_process.wait(timeout=0.2)
        except Exception:
            try:
                self._clipboard_process.kill()
            except Exception:
                pass
        finally:
            self._clipboard_process = None

    def _type_key(self, key_code: int, shift: bool = False) -> None:
        """Type a single key with optional shift modifier."""
        if not self._ui:
            return

        if shift:
            # Press shift
            self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
            self._ui.syn()

        # Press and release key
        self._ui.write(ecodes.EV_KEY, key_code, 1)
        self._ui.syn()
        time.sleep(0.001)
        self._ui.write(ecodes.EV_KEY, key_code, 0)
        self._ui.syn()

        if shift:
            # Release shift
            self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
            self._ui.syn()

    def _type_modified_key(self, key_code: int, shift: bool = False, ctrl: bool = False) -> None:
        """Type a key with Ctrl and/or Shift modifiers."""
        if not self._ui:
            return

        if ctrl:
            self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
            self._ui.syn()
        if shift:
            self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
            self._ui.syn()

        self._ui.write(ecodes.EV_KEY, key_code, 1)
        self._ui.syn()
        time.sleep(0.001)
        self._ui.write(ecodes.EV_KEY, key_code, 0)
        self._ui.syn()

        if shift:
            self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
            self._ui.syn()
        if ctrl:
            self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
            self._ui.syn()

    def type_key(self, key: str) -> bool:
        """Press a special key.

        Args:
            key: Key name (e.g., 'Return', 'Tab', 'BackSpace').

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_available():
            return False

        key_map = {
            "return": ecodes.KEY_ENTER,
            "enter": ecodes.KEY_ENTER,
            "tab": ecodes.KEY_TAB,
            "backspace": ecodes.KEY_BACKSPACE,
            "escape": ecodes.KEY_ESC,
            "space": ecodes.KEY_SPACE,
            "up": ecodes.KEY_UP,
            "down": ecodes.KEY_DOWN,
            "left": ecodes.KEY_LEFT,
            "right": ecodes.KEY_RIGHT,
        }

        key_code = key_map.get(key.lower())
        if key_code is None:
            logger.warning(f"Unknown key: {key}")
            return False

        try:
            self._type_key(key_code)
            return True
        except Exception as e:
            logger.error(f"Key press failed: {e}")
            return False

    def set_typing_delay(self, delay: int) -> None:
        """Set typing delay.

        Args:
            delay: Delay between keystrokes in milliseconds.
        """
        self.typing_delay = delay

    def cleanup(self) -> None:
        """Clean up UInput device."""
        self._terminate_clipboard_process()
        if self._ui:
            try:
                self._ui.close()
            except Exception:
                pass
            self._ui = None
            self._available = False

    def __del__(self):
        self.cleanup()
