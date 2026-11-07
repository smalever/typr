"""Create a fresh per-user config exclusively; never load/overwrite existing config."""

import base64
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from typr.config import AppConfig
from typr.platforms.windows_security import check_private_path


def assert_no_reparse(path):
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError("Reparse point in configuration path")


def initialize(kind):
    if sys.platform != "win32" or kind not in ("Parakeet", "GigaSTT"):
        raise RuntimeError("Windows and a known STT kind required")
    directory = Path(os.environ["LOCALAPPDATA"]) / "Typr"
    assert_no_reparse(directory)
    # No config contents are read, even for an existing file.
    config_path = directory / "config.json"
    if os.path.lexists(config_path):
        print("Existing configuration preserved. Select endpoint/model in Typr Settings.")
        return
    # Create/protect only a NEW directory. Existing ACLs are inspected, never changed.
    command = r"""
$ErrorActionPreference = 'Stop'
$p = Join-Path $env:LOCALAPPDATA 'Typr'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
if (-not (Test-Path -LiteralPath $p)) {
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetOwner($sid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($id in @($sid.Value, 'S-1-5-18')) {
        $identity = New-Object Security.Principal.SecurityIdentifier($id)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    [IO.Directory]::CreateDirectory($p, $acl) | Out-Null
}
$acl = Get-Acl -LiteralPath $p
if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value) {
    throw 'Foreign data directory owner'
}
foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
    if ($rule.AccessControlType -eq 'Allow' -and
        $rule.IdentityReference.Value -notin @($sid.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        throw 'Data directory accessible by another identity; review permissions manually'
    }
}
"""
    encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        check=True, capture_output=True, timeout=30,
    )
    assert_no_reparse(directory)
    check_private_path(directory)
    config = AppConfig()
    if kind == "GigaSTT":
        config.api_base_url = "http://127.0.0.1:9876/v1"
        config.transcription.model = "gigaam-v3-rnnt"
    payload = (json.dumps(config._to_dict(), ensure_ascii=False, indent=2) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=".typr-initial-config-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as output:
            check_private_path(Path(temporary))
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        assert_no_reparse(directory)
        check_private_path(directory)
        try:
            # On Windows os.rename is atomic and refuses an existing destination.
            os.rename(temporary, config_path)
        except FileExistsError:
            print("Configuration created concurrently; preserved unchanged.")
            return
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
    print("Fresh STT configuration initialized; no existing configuration was read.")


if __name__ == "__main__":
    initialize(sys.argv[1])
