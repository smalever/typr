"""Sequential Linux worker: owns uinput, helpers, backup and restore deadlines."""

import importlib.util
import os
import queue
import select
import shutil
import subprocess
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

from typr.utils.logger import logger


class LinuxInjector(QObject):
    result = pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = None

    def is_available(self):
        # Nonblocking preflight only; actual device opening happens in worker.
        return (not self._stop.is_set() and importlib.util.find_spec("evdev") is not None
                and LinuxSession.detect_backend() is not None)

    def request(self, serial, text, typing_delay, restore_delay):
        if self._stop.is_set():
            return
        if self._thread is not None and not self._thread.is_alive():
            raise RuntimeError("Linux injection worker has stopped")
        self._queue.put((serial, text, typing_delay, restore_delay))
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="typr-injection", daemon=True)
            self._thread.start()

    def cleanup(self):
        if self._stop.is_set():
            return
        self._stop.set()
        self._queue.put(None)  # Wake deadline/queue wait; never join the Qt thread.

    def is_cleanup_complete(self):
        # is_alive becomes False only AFTER session.close() and worker finally.
        return self._stop.is_set() and (self._thread is None or not self._thread.is_alive())

    def _run(self):
        session = None
        serial = None
        try:
            session = LinuxSession(self._stop)
            while not self._stop.is_set():
                timeout = (None if session.deadline is None
                           else max(0, session.deadline - time.monotonic()))
                try:
                    command = self._queue.get(timeout=timeout)
                except queue.Empty:
                    try:
                        session.restore()
                    except Exception as exc:
                        logger.error(f"Linux clipboard restore failed: {exc}")
                        session.release_helper()
                    finally:
                        session.deadline = None
                    continue
                if command is None or self._stop.is_set():
                    break
                serial, text, typing_delay, restore_delay = command
                error = ""
                try:
                    session.paste(text, typing_delay, restore_delay)
                except Exception as exc:  # Worker operation boundary
                    error = str(exc)
                    logger.error(f"Linux text injection failed: {exc}")
                    session.release_helper()
                if not self._stop.is_set():
                    self.result.emit(serial, error)
                serial = None
        except Exception as exc:  # Terminal worker boundary, including initialization.
            logger.error(f"Linux injection worker stopped: {exc}")
            if serial is not None and not self._stop.is_set():
                self.result.emit(serial, str(exc))
            while not self._stop.is_set():
                try:
                    pending = self._queue.get_nowait()
                except queue.Empty:
                    break
                if pending is not None:
                    self.result.emit(pending[0], str(exc))
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception as exc:  # Worker cleanup boundary
                    logger.error(f"Linux injection cleanup failed: {exc}")


class LinuxSession:
    """Mutable state is private to exactly one worker, never Settings or Qt."""

    def __init__(self, stop):
        self.stop = stop
        self.ui = None
        self.codes = None
        self.process = None
        self.backend = None
        self.backup = None
        self.pasted = ""
        self.deadline = None

    @staticmethod
    def detect_backend():
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
            return "wl-copy"
        if os.environ.get("DISPLAY"):
            for backend in ("xclip", "xsel"):
                if shutil.which(backend):
                    return backend
        return None

    def check_cancelled(self):
        if self.stop.is_set():
            raise RuntimeError("Injection cancelled")

    def read(self):
        commands = {"wl-copy": ["wl-paste", "-n"],
                    "xclip": ["xclip", "-selection", "clipboard", "-o"],
                    "xsel": ["xsel", "--clipboard", "--output"]}
        res = subprocess.run(commands[self.backend], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=0.5)
        return res.stdout.decode("utf-8", errors="replace") if res.returncode == 0 else None

    def spawn(self, text):
        commands = {"wl-copy": ["wl-copy", "--type", "text/plain;charset=utf-8", "--foreground"],
                    "xclip": ["xclip", "-selection", "clipboard", "-in", "-quiet"],
                    "xsel": ["xsel", "--clipboard", "--input", "--nodetach"]}
        self.check_cancelled()
        process = subprocess.Popen(commands[self.backend], stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            # Helper retains clipboard ownership; communicate() would await its exit.
            # Nonblocking pipe writes bound even a helper that never reads stdin.
            fd = process.stdin.fileno()
            os.set_blocking(fd, False)
            data = memoryview(text.encode("utf-8"))
            deadline = time.monotonic() + 1.0
            while data:
                self.check_cancelled()
                if time.monotonic() >= deadline:
                    raise TimeoutError("Clipboard helper input timed out")
                if select.select([], [fd], [], 0.05)[1]:
                    try:
                        data = data[os.write(fd, data[:4096]):]
                    except BlockingIOError:
                        continue
            process.stdin.close()
            if process.poll() not in (None, 0):
                raise RuntimeError("Clipboard helper exited unsuccessfully")
            return process
        except BaseException:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            self.terminate(process)
            raise

    @staticmethod
    def terminate(process):
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=0.2)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.error(f"Clipboard helper cleanup failed: {exc}")

    def release_helper(self):
        if self.process is not None:
            self.terminate(self.process)
            self.process = None

    def restore(self):
        self.deadline = None
        self.check_cancelled()
        current = self.read()
        if current is None:
            logger.warning("Clipboard verification failed; restore skipped")
            self.release_helper()
            return
        if current != self.pasted:
            self.release_helper()
            return
        self.release_helper()
        self.check_cancelled()
        if self.backup is not None or self.backend == "xclip":
            # Empty X selection also needs a foreground owner; track it like restore.
            self.process = self.spawn(self.backup if self.backup is not None else "")
        else:
            commands = {"wl-copy": ["wl-copy", "--clear"],
                        "xsel": ["xsel", "--clipboard", "--clear", "--nodetach"]}
            subprocess.run(commands[self.backend], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=0.5, check=True)

    def paste(self, text, typing_delay, restore_delay):
        self.check_cancelled()
        if not text:
            return
        if self.ui is None:
            from evdev import UInput, ecodes

            self.codes = ecodes
            self.ui = UInput(name="typr-keyboard")
        self.check_cancelled()
        if self.process is not None and self.deadline is not None:
            self.restore()
        self.backend = self.detect_backend()
        if self.backend is None:
            raise RuntimeError("No clipboard backend (wl-copy/xclip/xsel)")
        try:
            self.backup = self.read()
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(f"Clipboard backup failed: {exc}")
            self.backup = None
        self.check_cancelled()
        self.pasted = text
        self.release_helper()
        self.process = self.spawn(text)
        if self.stop.wait(0.12):
            return
        self.check_cancelled()  # No paste if shutdown preceded sending.
        held = []
        cleanup_errors = []
        try:
            for code in (self.codes.KEY_LEFTSHIFT, self.codes.KEY_INSERT):
                self.ui.write(self.codes.EV_KEY, code, 1)
                held.append(code)
                self.ui.syn()
            self.stop.wait(0.001)
        finally:
            for code in reversed(held):
                try:
                    self.ui.write(self.codes.EV_KEY, code, 0)
                    self.ui.syn()
                except Exception as exc:
                    logger.error(f"Synthetic uinput key cleanup failed: {exc}")
                    cleanup_errors.append(str(exc))
        if cleanup_errors:
            raise RuntimeError("Synthetic uinput key cleanup failed: " + "; ".join(cleanup_errors))
        self.deadline = time.monotonic() + max(0, restore_delay)/1000

    def close(self):
        try:
            self.release_helper()
        finally:
            if self.ui is not None:
                try:
                    self.ui.close()
                except Exception as exc:
                    logger.error(f"UInput cleanup failed: {exc}")
