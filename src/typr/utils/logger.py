"""Logging configuration for Typr."""

import logging
import sys

from typr.platforms.paths import log_dir


def setup_logger(name: str = "typr", level: int = logging.INFO) -> logging.Logger:
    """Set up and return a logger with console and file handlers."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Prepare file first: failure must not leave a partly initialized logger that
    # silently skips the file on the next call. No cwd/temporary log fallback.
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(directory / "typr.log", encoding="utf-8")
    except OSError as error:
        raise OSError(f"Cannot initialize Typr log file: {error}") from error
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    # pythonw may have neither stdout nor stderr: the UTF-8 file is the sink.
    stream = sys.stdout if sys.stdout is not None else sys.stderr
    if stream is not None:
        console_handler = logging.StreamHandler(stream)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
        ))
        logger.addHandler(console_handler)

    return logger


# Default logger instance
logger = setup_logger()
