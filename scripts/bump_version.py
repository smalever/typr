#!/usr/bin/env python3
"""Bump and synchronize the Typr application version."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

VERSION_FILES = {
    PROJECT_ROOT / "pyproject.toml": re.compile(r'(?m)^version = "(?P<version>\d+\.\d+\.\d+)"$'),
    PROJECT_ROOT / "src" / "typr" / "__init__.py": re.compile(
        r'(?m)^__version__ = "(?P<version>\d+\.\d+\.\d+)"$'
    ),
    PROJECT_ROOT / "src" / "typr" / "utils" / "i18n.py": re.compile(
        r'(?P<prefix>settings\.about\.version": "(?:Version|Версия) )'
        r'(?P<version>\d+\.\d+\.\d+)'
        r'(?P<suffix>")'
    ),
    PROJECT_ROOT / "README.md": re.compile(
        r'(?P<prefix>img\.shields\.io/badge/version-)'
        r'(?P<version>\d+\.\d+\.\d+)'
        r'(?P<suffix>-brightgreen\.svg)'
    ),
}


def bump(version: str, level: str) -> str:
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(f"Invalid semantic version: {version}")

    major, minor, patch = map(int, match.groups())
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def versions_by_file() -> dict[Path, set[str]]:
    versions: dict[Path, set[str]] = {}
    for path, pattern in VERSION_FILES.items():
        content = path.read_text(encoding="utf-8")
        matches = {match.group("version") for match in pattern.finditer(content)}
        if not matches:
            raise RuntimeError(f"Version not found in {path.relative_to(PROJECT_ROOT)}")
        versions[path] = matches
    return versions


def current_version() -> str:
    versions = versions_by_file()
    found = {version for file_versions in versions.values() for version in file_versions}
    if len(found) != 1 or any(len(file_versions) != 1 for file_versions in versions.values()):
        details = ", ".join(
            f"{path.relative_to(PROJECT_ROOT)}={sorted(file_versions)}"
            for path, file_versions in versions.items()
        )
        raise RuntimeError(f"Application versions are not synchronized: {details}")
    return found.pop()


def replace_version(path: Path, old_version: str, new_version: str) -> None:
    pattern = VERSION_FILES[path]
    content = path.read_text(encoding="utf-8")

    def replacement(match: re.Match[str]) -> str:
        groups = match.groupdict()
        if "prefix" in groups:
            return f"{groups['prefix']}{new_version}{groups['suffix']}"
        return match.group(0).replace(old_version, new_version, 1)

    updated, count = pattern.subn(replacement, content)
    if count == 0:
        raise RuntimeError(f"Version not updated in {path.relative_to(PROJECT_ROOT)}")
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("level", choices=("patch", "minor", "major"), nargs="?")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that all application version declarations match",
    )
    args = parser.parse_args()

    old_version = current_version()
    if args.check:
        print(old_version)
        return
    if args.level is None:
        parser.error("level is required unless --check is used")

    new_version = bump(old_version, args.level)
    for path in VERSION_FILES:
        replace_version(path, old_version, new_version)
    print(f"{old_version} -> {new_version}")


if __name__ == "__main__":
    main()
