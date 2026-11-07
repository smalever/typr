"""Executable Windows PowerShell 5.1 installer contract tests, without Pester."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = Path(os.environ.get("SystemRoot", "C:/Windows")) / (
    "System32/WindowsPowerShell/v1.0/powershell.exe"
)


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell 5.1 required")
def test_mocked_windows_installer(tmp_path):
    result = subprocess.run(
        [
            str(POWERSHELL), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "tests/windows/installer_harness.ps1"),
            "-Repository", str(ROOT), "-Sandbox", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL MOCKED INSTALLER TESTS PASSED" in result.stdout


def test_delivery_contract():
    scripts = ROOT / "scripts/windows"
    build = (scripts / "Build-Payload.ps1").read_text(encoding="utf-8")
    module = (scripts / "TyprInstaller.ps1").read_text(encoding="utf-8")
    assert "3.15.2" in build
    assert "--no-index" in build
    assert "--only-binary=:all:" in build
    assert "-m','pip','wheel'" in build
    assert "-m pip check" in build
    assert "qualification = 'OPEN'" in build
    assert "--host $endpoint" in module
    assert "unless-stopped" not in module
    assert "Stop-Process" not in module
    assert "config.json" not in module
    assert "-B -m typr" in module
    assert "-Uninstall" in (scripts / "Uninstall.bat").read_text()
    assert "payload.json" in build


def test_final_zip_includes_payload_json(tmp_path):
    import zipfile
    zip_path = tmp_path / "typr-final.zip"
    import shutil
    source = Path("C:/Users/smale/AppData/Local/Temp/kilo/Typr-Windows-x64-20261107-final.zip")
    if not source.exists():
        pytest.skip("Final ZIP not available at expected location")
    shutil.copy(source, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        assert any(n == "Typr/payload.json" for n in names), "payload.json must be included in final ZIP"


@pytest.mark.skipif(os.name != "nt", reason="Windows data directory safety checks")
def test_fresh_config_never_reads_or_overwrites_existing(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'src'))
    spec = importlib.util.spec_from_file_location(
        "typr_installer_config", ROOT / "scripts/windows/Initialize-Config.py"
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    data = tmp_path / "Typr"
    data.mkdir()
    config = data / "config.json"
    config.write_bytes(b"secret fixture - intentionally not valid JSON")
    monkeypatch.setattr(
        helper.subprocess, "run",
        lambda *a, **kw: pytest.fail("existing config must not invoke ACL changes"),
    )
    helper.initialize("GigaSTT")
    assert config.read_bytes() == b"secret fixture - intentionally not valid JSON"


@pytest.mark.skipif(os.name != "nt", reason="Windows data directory safety checks")
def test_fresh_gigastt_config_and_create_race(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'src'))
    spec = importlib.util.spec_from_file_location(
        "typr_installer_config", ROOT / "scripts/windows/Initialize-Config.py"
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    checked = []
    monkeypatch.setattr(helper, 'check_private_path', lambda path: checked.append(path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    data = tmp_path / "Typr"
    data.mkdir()
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **kw: None)
    helper.initialize("GigaSTT")
    import json

    config = data / "config.json"
    value = json.loads(config.read_text())
    assert value["api_base_url"] == "http://127.0.0.1:9876/v1"
    assert value["transcription"]["model"] == "gigaam-v3-rnnt"
    assert data in checked
    assert any(path.name.startswith('.typr-initial-config-') for path in checked)
    config.unlink()

    def race(*args, **kwargs):
        config.write_bytes(b"concurrent writer preserved")

    monkeypatch.setattr(helper.subprocess, "run", race)
    helper.initialize("GigaSTT")
    assert config.read_bytes() == b"concurrent writer preserved"
