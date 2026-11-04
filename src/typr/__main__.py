"""Entry point for Typr application."""

import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from typr.app import TyprApp
from typr.utils.logger import logger


def _cleanup(typr: TyprApp) -> None:
    """Use the controller barrier even after startup/outer event-loop failure."""
    typr._quit()
    if typr._quit_completed:
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if typr._quit_completed else None)
    poll.start()
    try:
        # No join or forced timeout: the existing barrier owns completion.
        while not typr._quit_completed:
            loop.exec()
    finally:
        poll.stop()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Typr")
    app.setOrganizationName("Typr")

    typr = TyprApp()
    try:
        typr.start()
        exit_code = app.exec()
    except Exception:
        logger.exception("Typr startup/event loop failed")
        raise
    finally:
        _cleanup(typr)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
