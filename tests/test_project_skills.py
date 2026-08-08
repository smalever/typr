"""Contract tests for the project-level Kilo skills."""

import json
import os
import re
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
