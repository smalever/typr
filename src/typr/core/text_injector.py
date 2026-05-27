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


# CHAR_TO_KEY dictionary is removed to get rid of keyboard layout binding legacy.



class TextInjector:
    """Injects text using evdev UInput (works on Wayland and X11)."""

    def __init__(self, typing_delay: int = 0, restore_delay: int = 3000):
        """Initialize text injector.

        Args:
            typing_delay: Delay between keystrokes in milliseconds.
            restore_delay: Delay before restoring clipboard in milliseconds.
        """
        self.typing_delay = typing_delay
        self.restore_delay = restore_delay
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
            backend = self._detect_clipboard_backend()
            if backend is None:
                logger.error("No clipboard backend (wl-clipboard/xclip/xsel) available. Cannot paste text.")
                return False
            return self._paste_text(text)

        except Exception as e:
            logger.error(f"Text injection failed: {e}")
            return False


    def _backup_clipboard(self) -> None:
        """Back up the current clipboard text."""
        self._backup_text = ""
        self._has_backup = False
        
        backend = self._detect_clipboard_backend()
        if backend is None:
            return

        try:
            if backend == "wl-copy":
                # wl-paste exits with code 1 if empty or if clipboard format is not text
                res = subprocess.run(
                    ["wl-paste", "-n"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5,
                )
                if res.returncode == 0:
                    self._backup_text = res.stdout.decode("utf-8", errors="replace")
                    self._has_backup = True
            elif backend == "xclip":
                res = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5,
                )
                if res.returncode == 0:
                    self._backup_text = res.stdout.decode("utf-8", errors="replace")
                    self._has_backup = True
            elif backend == "xsel":
                res = subprocess.run(
                    ["xsel", "--clipboard", "--output"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5,
                )
                if res.returncode == 0:
                    self._backup_text = res.stdout.decode("utf-8", errors="replace")
                    self._has_backup = True
            
            if self._has_backup:
                logger.debug(f"Clipboard backed up successfully ({len(self._backup_text)} chars)")
        except subprocess.TimeoutExpired:
            logger.warning("Clipboard backup timed out")
        except Exception as e:
            logger.debug(f"Failed to backup clipboard: {e}")

    def _restore_clipboard(self) -> None:
        """Restore the original clipboard content if the user hasn't overwritten it."""
        backend = self._detect_clipboard_backend()
        if backend is None:
            return

        # Check if the clipboard still has the pasted text
        current_text = ""
        try:
            if backend == "wl-copy":
                res = subprocess.run(["wl-paste", "-n"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=0.5)
                if res.returncode == 0:
                    current_text = res.stdout.decode("utf-8", errors="replace")
            elif backend == "xclip":
                res = subprocess.run(["xclip", "-selection", "clipboard", "-o"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=0.5)
                if res.returncode == 0:
                    current_text = res.stdout.decode("utf-8", errors="replace")
            elif backend == "xsel":
                res = subprocess.run(["xsel", "--clipboard", "--output"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=0.5)
                if res.returncode == 0:
                    current_text = res.stdout.decode("utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Failed to read clipboard for verification: {e}")
            return

        # If the clipboard text is different from what we pasted, the user copied something new. Do not overwrite it!
        pasted_text = getattr(self, "_pasted_text", "")
        if current_text != pasted_text:
            logger.debug("Clipboard content changed by user, skipping restore")
            return

        # Perform restore
        if not getattr(self, "_has_backup", False):
            # Clear clipboard
            try:
                if backend == "wl-copy":
                    subprocess.run(["wl-copy", "--clear"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif backend == "xclip":
                    subprocess.run(["xclip", "-selection", "clipboard", "/dev/null"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif backend == "xsel":
                    subprocess.run(["xsel", "--clipboard", "--clear"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.debug("Clipboard cleared (no backup existed)")
            except Exception as e:
                logger.debug(f"Failed to clear clipboard: {e}")
            return

        try:
            # Restore original clipboard
            backup_text = getattr(self, "_backup_text", "")
            self._spawn_clipboard_backend(backend, backup_text)
            logger.debug(f"Clipboard restored ({len(backup_text)} chars)")
        except Exception as e:
            logger.error(f"Failed to restore clipboard: {e}")

    def _paste_text(self, text: str) -> bool:
        """Paste Unicode text through a desktop-specific clipboard backend."""
        backend = self._detect_clipboard_backend()
        if backend is None:
            logger.error("No clipboard backend available for Unicode paste")
            return False

        # Backup clipboard first
        self._backup_clipboard()
        self._pasted_text = text

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

        self._schedule_clipboard_release(self.restore_delay)  # Wait restore_delay before releasing/restoring
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
        """Release the clipboard helper process after paste completes and restore original clipboard."""
        self._terminate_clipboard_process()
        self._restore_clipboard()


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

    def set_typing_delay(self, delay: int) -> None:
        """Set typing delay.

        Args:
            delay: Delay between keystrokes in milliseconds.
        """
        self.typing_delay = delay

    def set_restore_delay(self, delay: int) -> None:
        """Set the clipboard restore delay in milliseconds.

        Args:
            delay: Delay before restoring clipboard in milliseconds.
        """
        self.restore_delay = delay

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
