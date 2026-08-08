"""Contract tests for the project-level Kilo skills."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROJECT_ROOT / ".kilo" / "skills"
FRONTMATTER_PATTERN = re.compile(r"\A---\n(?P<header>.*?)\n---\n", re.DOTALL)


def _frontmatter(skill_file: Path) -> dict[str, str]:
    content = skill_file.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(content)
    assert match is not None, f"Missing YAML frontmatter: {skill_file}"

    values: dict[str, str] = {}
    for line in match.group("header").splitlines():
        key, separator, value = line.partition(":")
        assert separator, f"Invalid frontmatter line in {skill_file}: {line}"
        values[key.strip()] = value.strip()
    return values


def test_kilo_config_registers_project_skills() -> None:
    config = json.loads((PROJECT_ROOT / "kilo.json").read_text(encoding="utf-8"))

    assert "./.kilo/skills" in config["skills"]["paths"]
    assert config["permission"]["skill"]["*"] == "allow"


def test_skills_have_unique_matching_frontmatter() -> None:
    skill_files = sorted(SKILLS_ROOT.glob("*/SKILL.md"))
    assert skill_files

    names = []
    for skill_file in skill_files:
        metadata = _frontmatter(skill_file)
        assert metadata.get("name") == skill_file.parent.name
        assert metadata.get("description")
        names.append(metadata["name"])

    assert len(names) == len(set(names))


def test_documentation_map_references_registered_skills() -> None:
    docs_map = (PROJECT_ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    for skill_file in SKILLS_ROOT.glob("*/SKILL.md"):
        relative_path = Path(os.path.relpath(skill_file, PROJECT_ROOT / "docs")).as_posix()
        assert relative_path in docs_map


def test_git_commit_skill_requires_semantic_version_bump() -> None:
    commit_skill = (SKILLS_ROOT / "git-commit" / "SKILL.md").read_text(encoding="utf-8")

    assert "scripts/bump_version.py patch" in commit_skill
    assert "minor / major" in commit_skill
    assert "непосредственно перед staging" in commit_skill


def test_application_versions_are_synchronized() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (PROJECT_ROOT / "src" / "typr" / "__init__.py").read_text(encoding="utf-8")
    translations = (
        PROJECT_ROOT / "src" / "typr" / "utils" / "i18n.py"
    ).read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    version = re.search(r'(?m)^version = "(\d+\.\d+\.\d+)"$', pyproject)
    assert version is not None
    expected = version.group(1)

    assert f'__version__ = "{expected}"' in package
    assert f'"settings.about.version": "Version {expected}"' in translations
    assert f'"settings.about.version": "Версия {expected}"' in translations
    assert f"badge/version-{expected}-brightgreen.svg" in readme

    result = subprocess.run(
        [sys.executable, "scripts/bump_version.py", "--check"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == expected
