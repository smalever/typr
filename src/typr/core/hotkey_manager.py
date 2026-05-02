"""Global hotkey management using evdev for direct keyboard access."""

import threading
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from typr.config import HotkeyConfig
from typr.utils.logger import logger

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes

    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    logger.warning("evdev not available - install with: pip install evdev")


# Key code mappings
KEY_NAMES = {
    "space": ecodes.KEY_SPACE if EVDEV_AVAILABLE else 57,
    "enter": ecodes.KEY_ENTER if EVDEV_AVAILABLE else 28,
    "return": ecodes.KEY_ENTER if EVDEV_AVAILABLE else 28,
    "escape": ecodes.KEY_ESC if EVDEV_AVAILABLE else 1,
    "tab": ecodes.KEY_TAB if EVDEV_AVAILABLE else 15,
    "backspace": ecodes.KEY_BACKSPACE if EVDEV_AVAILABLE else 14,
    "f1": ecodes.KEY_F1 if EVDEV_AVAILABLE else 59,
    "f2": ecodes.KEY_F2 if EVDEV_AVAILABLE else 60,
    "f3": ecodes.KEY_F3 if EVDEV_AVAILABLE else 61,
    "f4": ecodes.KEY_F4 if EVDEV_AVAILABLE else 62,
    "f5": ecodes.KEY_F5 if EVDEV_AVAILABLE else 63,
    "f6": ecodes.KEY_F6 if EVDEV_AVAILABLE else 64,
    "f7": ecodes.KEY_F7 if EVDEV_AVAILABLE else 65,
    "f8": ecodes.KEY_F8 if EVDEV_AVAILABLE else 66,
    "f9": ecodes.KEY_F9 if EVDEV_AVAILABLE else 67,
    "f10": ecodes.KEY_F10 if EVDEV_AVAILABLE else 68,
    "f11": ecodes.KEY_F11 if EVDEV_AVAILABLE else 87,
    "f12": ecodes.KEY_F12 if EVDEV_AVAILABLE else 88,
}

# Modifier key codes
if EVDEV_AVAILABLE:
    MODIFIER_KEYS = {
        ecodes.KEY_LEFTMETA: "meta",
        ecodes.KEY_RIGHTMETA: "meta",
        ecodes.KEY_LEFTSHIFT: "shift",
        ecodes.KEY_RIGHTSHIFT: "shift",
        ecodes.KEY_LEFTCTRL: "ctrl",
        ecodes.KEY_RIGHTCTRL: "ctrl",
        ecodes.KEY_LEFTALT: "alt",
        ecodes.KEY_RIGHTALT: "alt",
    }
else:
    MODIFIER_KEYS = {}


class HotkeyManager(QObject):
    """Manages global hotkeys using evdev for direct keyboard access."""

    # Signals
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    hotkey_error = pyqtSignal(str)

    def __init__(self, config: Optional[HotkeyConfig] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config or HotkeyConfig()
        self._devices: list = []
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._registered = False

        # Current modifier state
        self._modifiers: set[str] = set()

        # Parse the configured hotkey
        self._target_modifiers: set[str] = set()
        self._target_key: int = 0
        self._key_pressed = False

        self._parse_hotkey(self.config.push_to_talk)

    def _parse_hotkey(self, hotkey_str: str) -> None:
        """Parse hotkey string like 'Meta+Shift+Space' into components."""
        parts = hotkey_str.lower().replace(" ", "").split("+")

        self._target_modifiers = set()
        self._target_key = 0

        for part in parts:
            if part in ("meta", "super", "win"):
                self._target_modifiers.add("meta")
            elif part in ("shift",):
                self._target_modifiers.add("shift")
            elif part in ("ctrl", "control"):
                self._target_modifiers.add("ctrl")
            elif part in ("alt",):
                self._target_modifiers.add("alt")
            elif part in KEY_NAMES:
                self._target_key = KEY_NAMES[part]
            elif len(part) == 1 and part.isalpha():
                # Single letter key
                if EVDEV_AVAILABLE:
                    key_name = f"KEY_{part.upper()}"
                    self._target_key = getattr(ecodes, key_name, 0)
            else:
                logger.warning(f"Unknown key in hotkey: {part}")

        logger.info(f"Parsed hotkey: modifiers={self._target_modifiers}, key={self._target_key}")

    def initialize(self) -> bool:
        """Initialize evdev keyboard listeners.

        Returns:
            True if initialization was successful.
        """
        if not EVDEV_AVAILABLE:
            self.hotkey_error.emit("evdev not installed. Run: pip install evdev")
            return False

        try:
            # Find all keyboard devices
            self._devices = []
            input_dir = Path("/dev/input")

            for event_file in sorted(input_dir.glob("event*")):
                try:
                    device = InputDevice(str(event_file))
                    capabilities = device.capabilities()

                    # Check if device has keyboard keys (EV_KEY with typical keyboard codes)
                    if ecodes.EV_KEY in capabilities:
                        keys = capabilities[ecodes.EV_KEY]
                        # Check for common keyboard keys
                        if ecodes.KEY_SPACE in keys or ecodes.KEY_A in keys:
                            self._devices.append(device)
                            logger.debug(f"Found keyboard: {device.name} ({device.path})")
                except PermissionError:
                    logger.debug(f"No permission for {event_file}")
                except Exception as e:
                    logger.debug(f"Error opening {event_file}: {e}")

            if not self._devices:
                error_msg = "No keyboard devices found. Make sure you're in the 'input' group."
                self.hotkey_error.emit(error_msg)
                return False

            logger.info(f"Found {len(self._devices)} keyboard device(s)")

            # Start listener thread
            self._running = True
            self._thread = threading.Thread(target=self._event_loop, daemon=True)
            self._thread.start()

            self._registered = True
            logger.info(f"Hotkey manager initialized: {self.config.push_to_talk}")
            return True

        except Exception as e:
            error_msg = f"Failed to initialize hotkeys: {e}"
            logger.error(error_msg)
            self.hotkey_error.emit(error_msg)
            return False

    def _event_loop(self) -> None:
        """Main event loop reading from all keyboard devices."""
        import select
        import time

        devices_by_fd = {dev.fd: dev for dev in self._devices}

        while self._running:
            try:
                # Wait for events with timeout
                r, _, _ = select.select(devices_by_fd.keys(), [], [], 0.1)

                for fd in r:
                    device = devices_by_fd.get(fd)
                    if not device:
                        continue

                    try:
                        for event in device.read():
                            if event.type == ecodes.EV_KEY:
                                self._handle_key_event(event)
                    except BlockingIOError:
                        pass
                    except OSError as e:
                        # Device disconnected - remove from tracking
                        logger.warning(f"Device {device.path} disconnected: {e}")
                        del devices_by_fd[fd]
                        try:
                            device.close()
                        except Exception:
                            pass
                    except Exception as e:
                        logger.debug(f"Error reading from {device.path}: {e}")

            except OSError as e:
                # select() failed - likely bad file descriptor
                logger.error(f"Event loop select error: {e}")
                # Remove all invalid fds
                valid_fds = {}
                for fd, dev in devices_by_fd.items():
                    try:
                        select.select([fd], [], [], 0)  # Quick test
                        valid_fds[fd] = dev
                    except Exception:
                        logger.warning(f"Removing invalid device: {dev.path}")
                        try:
                            dev.close()
                        except Exception:
                            pass
                devices_by_fd = valid_fds
                time.sleep(0.1)  # Prevent tight loop even if all devices gone

            except Exception as e:
                if self._running:
                    logger.error(f"Event loop error: {e}")
                    time.sleep(0.1)  # Prevent tight loop on unexpected errors

    def _handle_key_event(self, event) -> None:
        """Handle a key press/release event."""
        key_code = event.code
        key_state = event.value  # 0=release, 1=press, 2=repeat

        # Update modifier state
        if key_code in MODIFIER_KEYS:
            modifier = MODIFIER_KEYS[key_code]
            if key_state == 1:  # Press
                self._modifiers.add(modifier)
            elif key_state == 0:  # Release
                self._modifiers.discard(modifier)

                # If we were recording and a modifier was released, stop
                if self._key_pressed and modifier in self._target_modifiers:
                    self._key_pressed = False
                    logger.debug("Hotkey released (modifier)")
                    self.recording_stopped.emit()
            return

        # Check for target key
        if key_code == self._target_key:
            if key_state == 1:  # Press
                # Check if all required modifiers are held
                if self._target_modifiers <= self._modifiers:
                    if not self._key_pressed:
                        self._key_pressed = True
                        logger.debug("Hotkey pressed")
                        self.recording_started.emit()

            elif key_state == 0:  # Release
                if self._key_pressed:
                    self._key_pressed = False
                    logger.debug("Hotkey released")
                    self.recording_stopped.emit()

    def update_shortcut(self, shortcut: str) -> bool:
        """Update the push-to-talk shortcut."""
        self.config.push_to_talk = shortcut
        self._parse_hotkey(shortcut)
        return True

    def is_registered(self) -> bool:
        """Check if hotkeys are registered."""
        return self._registered

    def cleanup(self) -> None:
        """Clean up resources."""
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        for device in self._devices:
            try:
                device.close()
            except Exception:
                pass

        self._devices = []
        self._registered = False
        logger.info("Hotkey manager cleaned up")
