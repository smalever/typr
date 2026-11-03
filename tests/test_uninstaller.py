"""Exercise permission cleanup only, with temporary resources and mocked sudo."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":
    pytest.skip("Linux shell uninstaller tests", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
UNINSTALLER = (ROOT / "uninstall.sh").read_text(encoding="utf-8")


@pytest.mark.parametrize("content", ["uinput\n", "uinput", "uinput\n\n",
                                     "# shared\nuinput\n", "uinput\nother\n", None])
@pytest.mark.parametrize("consent", ["y", "n"])
def test_module_cleanup_exact_content_and_consent(tmp_path, content, consent):
    module = tmp_path / "typr-uinput.conf"
    if content is not None:
        module.write_text(content, encoding="utf-8")
    log = tmp_path / "commands"
    prefix = UNINSTALLER.split('echo "========================================="', 1)[0]
    cleanup = UNINSTALLER.split("# Clean up udev rules interactively", 1)[1]
    cleanup = cleanup.split('echo "========================================="', 1)[0]
    cleanup = cleanup.replace("/etc/modules-load.d/typr-uinput.conf", str(module))
    cleanup = cleanup.replace("/etc/udev/rules.d/99-uinput.rules", str(tmp_path / "missing"))
    mocks = '''
sudo() {
    printf '%s\n' "$*" >> "$LOG"
    if [ "$1" = rm ]; then command "$@"; fi
}
'''
    result = subprocess.run(["bash", "-c", prefix + mocks + cleanup],
                            input=consent + "\n", encoding="utf-8", capture_output=True,
                            env=dict(os.environ, HOME=str(tmp_path), LOG=str(log)), timeout=5)
    assert result.returncode == 0, result.stderr
    removed = content == "uinput\n" and consent == "y"
    assert module.exists() is (content is not None and not removed)
    if module.exists():
        assert module.read_text(encoding="utf-8") == content
    commands = log.read_text(encoding="utf-8") if log.exists() else ""
    assert (f"rm -f {module}" in commands) is removed
    if content != "uinput\n" or consent == "n":
        assert not commands


def test_module_cleanup_preserves_symlink(tmp_path):
    target = tmp_path / "shared.conf"
    target.write_text("uinput\n", encoding="utf-8")
    module = tmp_path / "typr-uinput.conf"
    module.symlink_to(target)
    block = UNINSTALLER.split("managed_module_entry()", 1)[1].split(
        'if [ -f "$UDEV_RULE_FILE" ] || managed_module_entry;', 1
    )[0]
    result = subprocess.run(["bash", "-c", f'MODULE_LOAD_FILE="{module}"\n'
                             + "managed_module_entry()" + block + "\nmanaged_module_entry"],
                            capture_output=True, timeout=5)
    assert result.returncode != 0
    assert module.is_symlink()
    assert target.read_text(encoding="utf-8") == "uinput\n"
