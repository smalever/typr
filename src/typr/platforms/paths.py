"""Application paths and private atomic persistence (no device dependencies)."""

import os
import stat
import sys
import tempfile
from pathlib import Path


def config_dir() -> Path:
    if sys.platform == "win32":
        value = os.environ.get("LOCALAPPDATA")
        if not value or not Path(value).is_absolute():
            raise OSError("Typr requires an absolute LOCALAPPDATA path")
        return Path(value) / "Typr"
    if sys.platform == "linux":
        return Path.home() / ".config" / "typr"
    raise OSError(f"Unsupported Typr platform: {sys.platform}")


def history_dir() -> Path:
    if sys.platform == "win32":
        return config_dir()
    if sys.platform == "linux":
        return Path.home() / ".local" / "share" / "typr"
    raise OSError(f"Unsupported Typr platform: {sys.platform}")


def log_dir() -> Path:
    return config_dir() / "logs"


def prepare_private_directory(directory: Path) -> None:
    """Fail closed before writing secrets, including on inherited Windows ACLs."""
    if sys.platform == "win32":
        from typr.platforms.windows_security import check_private_path

        # Check the existing ancestry BEFORE mkdir, then the resulting directory.
        check_private_path(directory, allow_missing=True)
        directory.mkdir(parents=True, exist_ok=True)
        check_private_path(directory)
    else:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o022):
            raise OSError(f"Unsafe private Typr directory: {directory}")


def atomic_write(path: Path, content: bytes) -> None:
    """Create a fresh private inode, write, then atomically replace the target.

    Never open predictable .tmp/.bak names for writing. The old target survives
    any failure before replace; even an existing permissive backup is replaced.
    """
    prepare_private_directory(path.parent)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            if sys.platform == "win32":
                from typr.platforms.windows_security import check_private_path

                check_private_path(temporary)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
