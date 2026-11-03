"""Installer regressions: all external/system commands run as isolated mocks."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":
    pytest.skip("Linux shell installer tests", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text(encoding="utf-8")
FUNCTIONS = INSTALLER.split("DRY_RUN=false", 1)[0]


@pytest.fixture
def shell(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    binary = tmp_path / "bin"
    binary.mkdir()
    log = tmp_path / "commands"
    env = dict(os.environ, HOME=str(home), LANG="en_US.UTF-8", LC_ALL="C",
               PATH=f"{binary}:/usr/bin:/bin", LOG=str(log), XDG_CURRENT_DESKTOP="KDE")
    env.pop("DOCKER_HOST", None)
    env.pop("DOCKER_CONTEXT", None)

    def mock(name, body):
        file = binary / name
        file.write_text(f'#!/bin/bash\nprintf "%s\\n" "{name} $*" >> "$LOG"\n{body}\n',
                        encoding="utf-8")
        file.chmod(0o755)

    mock("id", "printf '1000\\n'")
    mock("sudo", "exit 90")
    mock("systemctl", "exit 1")
    env["DOCKER_CONFIG"] = str(home / ".docker")

    def run(code, answers="", main=False):
        if main:
            release = tmp_path / "os-release"
            release.write_text('ID=debian\nNAME=Debian\n', encoding="utf-8")
            code = code.replace("/etc/os-release", str(release))
        result = subprocess.run(["bash", "-c", code], input=answers, encoding="utf-8",
                                capture_output=True, env=env, timeout=10)
        return result, log.read_text(encoding="utf-8") if log.exists() else ""

    return run, mock, home, env


def test_root_refused_before_selection(shell):
    run, mock, _, _ = shell
    mock("id", "printf '0\\n'")
    result, log = run(INSTALLER, main=True)
    assert result.returncode == 1
    assert "without sudo" in result.stderr
    assert "sudo " not in log


@pytest.mark.parametrize("choice,package", [("1", "git"), ("2", "docker.io"), ("3", "git")])
def test_dry_run_reports_packages_services_without_mutations(shell, choice, package):
    run, mock, home, env = shell
    # Missing Docker regardless of host installation; command -v is a shell builtin.
    code = INSTALLER.replace('command -v docker', 'command -v absent_typr_docker')
    mock("dpkg-query", "exit 1")
    result, log = run('set -- --dry-run\n' + code, choice + "\n", main=True)
    assert result.returncode == 0, result.stderr
    assert f"  - {package}" in result.stdout
    assert "docker.service" in result.stdout
    assert "typr-uinput.conf" in result.stdout
    assert not any(word in log for word in ("sudo ", "docker ", "git ", "pip ", "systemctl "))
    assert "docker group" not in result.stdout
    assert "root-equivalent" not in result.stdout
    assert list(home.iterdir()) == []


def test_no_local_does_not_require_docker_or_git(shell):
    run, mock, _, _ = shell
    mock("dpkg-query", "exit 1")
    result, log = run('set -- --dry-run\n' + INSTALLER, "4\n", main=True)
    assert result.returncode == 0
    assert "docker.service" not in result.stdout
    assert "  - docker" not in result.stdout
    assert "  - git" not in result.stdout
    assert "docker " not in log


def test_missing_packages_confirmation_precedes_any_backend(shell):
    run, mock, _, _ = shell
    mock("dpkg-query", "exit 1")
    mock("docker", "exit 93")
    mock("git", "exit 94")
    result, log = run(INSTALLER, "3\nn\n", main=True)
    assert result.returncode == 1
    assert "aborted" in result.stdout
    assert "docker " not in log and "git " not in log and "sudo " not in log


def test_main_preflight_and_confirmation_before_backend(shell):
    run, mock, _, _ = shell
    mock("dpkg-query", "exit 1")
    # Stop at the first backend, never run real installer operations.
    overrides = '''
install_packages() { printf 'packages accepted\\n'; SYSTEM_AUTHORIZED=true; }
authorize_system_changes() { :; }
prepare_docker() { printf 'prepare\\n'; }
setup_parakeet() { printf 'backend\\n'; exit 42; }
'''
    marker = "# 5. Full dependency preflight check"
    code = INSTALLER.replace(marker, overrides + "\n" + marker, 1)
    result, _ = run(code, "1\ny\n", main=True)
    assert result.returncode == 42
    assert result.stdout.index("Detected OS") < result.stdout.index("Missing packages")
    assert result.stdout.index("Missing packages") < result.stdout.index("packages accepted")
    assert result.stdout.index("packages accepted") < result.stdout.index("prepare")
    assert result.stdout.index("prepare") < result.stdout.index("backend")


def test_active_custom_docker_untouched(shell):
    run, mock, _, env = shell
    env["DOCKER_HOST"] = "unix:///run/user/1000/docker.sock"
    mock("docker", "exit 0")
    result, log = run(FUNCTIONS + "\nprepare_docker")
    assert result.returncode == 0
    assert log == "docker --host unix:///run/user/1000/docker.sock info\n"


def test_unavailable_custom_docker_never_elevates(shell):
    run, mock, _, env = shell
    env["DOCKER_HOST"] = "unix:///run/user/1000/docker.sock"
    mock("docker", "printf 'Cannot connect' >&2; exit 1")
    result, log = run(FUNCTIONS + "\nprepare_docker")
    assert result.returncode == 1
    assert "endpoint unavailable" in result.stderr
    assert "sudo" not in log and "systemctl" not in log


@pytest.mark.parametrize("permission", [True, False])
def test_stopped_local_docker_starts_once_and_verifies(shell, permission):
    run, mock, home, env = shell
    env.pop("DOCKER_HOST", None)
    env.pop("DOCKER_CONTEXT", None)
    mock("docker", f'''
if [[ "$1" = context ]]; then printf 'unix:///var/run/docker.sock\\n'; exit 0; fi
if [ -e "$HOME/started" ]; then
    {'printf "permission denied" >&2; exit 1' if permission else 'exit 0'}
fi
printf 'Cannot connect to the Docker daemon' >&2; exit 1
''')
    mock("systemctl", 'if [[ "$1" = is-* ]]; then exit 1; fi; exit 0')
    mock("sudo", '''
if [[ "$1" = systemctl ]]; then touch "$HOME/started"; fi
exit 0
''')
    result, log = run(FUNCTIONS + '\nprepare_docker\nprintf "%s\\n" "${docker_cmd[*]}"', "y\n")
    assert result.returncode == 0, result.stderr
    assert log.count("sudo systemctl enable --now docker.service") == 1
    elevated_info = ("sudo env -u DOCKER_CONTEXT -u DOCKER_HOST docker "
                     "--host unix:///var/run/docker.sock info")
    assert (elevated_info in log) is permission
    assert ("sudo env" in result.stdout) is permission
    assert (home / "started").exists()


def test_daemon_error_not_masked_by_sudo(shell):
    run, mock, _, _ = shell
    mock("docker", "printf 'API version mismatch' >&2; exit 1")
    result, log = run(FUNCTIONS + "\nprepare_docker")
    assert result.returncode != 0
    assert "sudo " not in log


def test_readiness_failure_has_logs_and_no_success(shell):
    run, mock, _, _ = shell
    mock("docker", '''
if [[ "$1" = container ]]; then printf 'false\\n'; fi
if [[ "$1" = logs ]]; then printf 'model load failed\\n'; fi
''')
    result, log = run(FUNCTIONS + "\nwait_for_stt parakeet-tdt http://localhost:5092/healthz")
    assert result.returncode == 1
    assert "docker logs --tail 50 parakeet-tdt" in log
    assert "model load failed" in result.stderr
    assert "is ready" not in result.stdout


def test_parakeet_uses_healthz_not_models():
    assert 'wait_for_stt "$parakeet_container" http://localhost:5092/healthz' in INSTALLER
    assert "/v1/models" not in INSTALLER


@pytest.mark.parametrize("field,value", [
    (None, None), ("ready", False), ("default_model", "other"),
    ("loaded", []), ("runtime", {"parakeet-tdt-0.6b-v3": {
        "backend": "cpu", "encoder_precision": "fp32",
    }}), ("runtime", {"parakeet-tdt-0.6b-v3": {
        "backend": "cuda", "encoder_precision": "int8",
    }}),
])
def test_parakeet_health_verification(field, value):
    model = "parakeet-tdt-0.6b-v3"
    health = {"ready": True, "default_model": model, "models": [model],
              "loaded": [model], "runtime": {model: {
                  "backend": "cpu", "encoder_precision": "int8",
              }}}
    if field:
        health[field] = value
    code = FUNCTIONS.split('verify_parakeet_model() {', 1)[1].split("python -c '", 1)[1]
    code = code.split("\n' ||", 1)[0]
    setup = ("import io, urllib.request\n"
             f"urllib.request.urlopen = lambda *a, **k: io.StringIO({json.dumps(health)!r})\n")
    result = subprocess.run([str(ROOT / ".venv/bin/python"), "-c", setup + code],
                            capture_output=True, encoding="utf-8")
    assert (result.returncode == 0) is (field is None)


@pytest.mark.parametrize("owned,mount_ok,mismatch", [
    (True, True, "image"), (True, True, "env"),
    (False, True, "image"), (True, False, "image"),
])
def test_parakeet_recreation_preserves_models_and_requires_ownership(
    shell, owned, mount_ok, mismatch,
):
    run, mock, home, env = shell
    directory = home / "docker/parakeet-tdt"
    directory.mkdir(parents=True)
    env["STATE"] = str(home / "removed")
    mount = f"bind:{directory}/models:true" if mount_ok else "volume:other:true"
    current_id = "old" if mismatch == "image" else "new"
    model = "wrong" if mismatch == "env" else "parakeet-tdt-0.6b-v3"
    mock("docker", f'''
if [[ "$1" = image ]]; then printf 'new\\n'; exit; fi
if [[ "$1" = port ]]; then printf '127.0.0.1:5092\\n'; exit; fi
if [[ "$1" = rm ]]; then touch "$STATE"; exit; fi
if [[ "$1" = container && "$2" = inspect ]]; then
    if [[ "$*" != *--format* ]]; then test ! -e "$STATE"; exit; fi
    case "$*" in
        *Config.Image*) printf 'parakeet-tdt:cpu\\n' ;;
        *Config.Labels*) printf '{"parakeet" if owned else "<no value>"}\\n' ;;
        *Config.Env*) printf '%s\\n' 'PARAKEET_USE_GPU=false' \
            'PARAKEET_DEFAULT_MODEL={model}' 'PARAKEET_BATCHED=0' ;;
        *Mounts*) printf '%s\\n' '{mount}' ;;
        *) printf '{current_id}\\n' ;;
    esac
fi
''')
    result, log = run(FUNCTIONS + '''
wait_for_stt() { :; }
verify_parakeet_model() { printf 'verified\\n'; }
setup_parakeet
''')
    recreate = owned and mount_ok
    assert (result.returncode == 0) is recreate, result.stderr
    assert ("docker rm -f parakeet-tdt" in log) is recreate
    if recreate:
        assert f"-v {directory}/models:/app/models" in log
        assert "-p 127.0.0.1:5092:5092" in log
        assert "verified" in result.stdout


def test_runtime_checks_and_safe_uinput_contract():
    assert '"$VENV_PIP" check' in INSTALLER
    assert "from PyQt6 import QtCore, QtGui, QtWidgets" in INSTALLER
    assert "Interpreter version mismatch" in INSTALLER
    assert "sudo modprobe uinput" in INSTALLER
    assert "MODULE_LOAD_FILE=/etc/modules-load.d/typr-uinput.conf" in INSTALLER
    assert 'if [ ! -e "$UDEV_RULE_FILE" ] && [ ! -L "$UDEV_RULE_FILE" ]; then' in INSTALLER
    assert "stat -c '%G:%a' /dev/uinput" in INSTALLER


@pytest.mark.parametrize("builtin,existing", [(False, False), (True, False), (False, True)])
def test_module_loading_persistence_preserves_existing(shell, builtin, existing):
    run, mock, home, _ = shell
    # Execute the actual module block, redirecting all resource paths into HOME.
    code = INSTALLER.split("sudo modprobe uinput", 1)[1].split("getent group input", 1)[0]
    code = "sudo modprobe uinput\n" + code
    code = code.replace("/etc/modules-load.d", str(home))
    code = code.replace("/usr/lib/modules-load.d", str(home / "absent"))
    code = code.replace("/run/modules-load.d", str(home / "absent"))
    if existing:
        (home / "other.conf").write_text("# shared setting\nuinput\n", encoding="utf-8")
    mock("modinfo", f"printf '{'(builtin)' if builtin else '/lib/modules/uinput.ko'}\\n'")
    mock("sudo", '"$@"')
    mock("modprobe", "exit 0")
    result, log = run(FUNCTIONS + "\n" + code)
    assert result.returncode == 0, result.stderr
    assert "sudo modprobe uinput" in log
    created = home / "typr-uinput.conf"
    assert created.exists() is (not builtin and not existing)
    if created.exists():
        assert created.read_text(encoding="utf-8") == "uinput\n"
    if existing:
        assert (home / "other.conf").read_text(encoding="utf-8") == "# shared setting\nuinput\n"


def test_readiness_success_uses_bounded_health_request(shell):
    run, mock, _, _ = shell
    mock("docker", 'if [[ "$1" = container ]]; then printf "true\\n"; fi; exit 0')
    result, log = run(FUNCTIONS + "\nwait_for_stt parakeet-tdt http://localhost:5092/healthz")
    assert result.returncode == 0
    assert "timeout=2" in log and "/healthz" in log
    assert "docker logs" not in log


def test_local_daemon_requires_running_systemd(shell):
    run, mock, _, _ = shell
    mock("docker", '''
if [[ "$1" = context ]]; then printf 'unix:///var/run/docker.sock\\n'; exit 0; fi
printf 'Cannot connect' >&2; exit 1
''')
    mock("systemctl", "exit 1")
    result, log = run(FUNCTIONS + "\nprepare_docker")
    assert result.returncode == 1
    assert "No running systemd" in result.stderr
    assert "sudo " not in log


@pytest.mark.parametrize("image,label", [("foreign:latest", "parakeet"),
                                         ("parakeet-tdt:cpu", "<no value>")])
def test_parakeet_conflict_does_not_remove_foreign_container(shell, image, label):
    run, mock, home, _ = shell
    (home / "docker" / "parakeet-tdt").mkdir(parents=True)
    mock("docker", f'''
if [[ "$*" = *'.Config.Image'* ]]; then printf '{image}\\n'; fi
if [[ "$*" = *'.Config.Labels'* ]]; then printf '{label}\\n'; fi
if [[ "$1" = port ]]; then printf '0.0.0.0:5092\\n'; fi
exit 0
''')
    result, log = run(FUNCTIONS + "\nsetup_parakeet")
    assert result.returncode == 1
    assert "docker rm" not in log
    assert "docker start" not in log


def test_local_daemon_failure_after_start_not_masked_by_sudo(shell):
    run, mock, _, _ = shell
    mock("docker", '''
if [[ "$1" = context ]]; then printf 'unix:///var/run/docker.sock\\n'; exit 0; fi
printf 'Cannot connect' >&2; exit 1
''')
    mock("systemctl", 'if [[ "$1" = is-* ]]; then exit 1; fi; exit 0')
    mock("sudo", "exit 0")
    result, log = run(FUNCTIONS + "\nprepare_docker", "y\n")
    assert result.returncode == 1
    assert "sudo systemctl enable --now docker.service" in log
    assert "sudo docker info" not in log


def test_active_disabled_standard_daemon_enabled(shell):
    run, mock, _, _ = shell
    mock("docker", "exit 0")
    mock("systemctl", 'if [[ "$1" = is-enabled ]]; then exit 1; fi; exit 0')
    mock("sudo", "exit 0")
    result, log = run(FUNCTIONS + "\nprepare_docker", "y\n")
    assert result.returncode == 0
    assert "sudo systemctl enable --now docker.service" in log


def test_active_enabled_standard_daemon_needs_no_sudo(shell):
    run, mock, _, _ = shell
    mock("docker", "exit 0")
    mock("systemctl", "exit 0")
    result, log = run(FUNCTIONS + "\nprepare_docker")
    assert result.returncode == 0
    assert "sudo " not in log


def test_cli_only_engine_is_in_preflight(shell):
    run, mock, _, _ = shell
    mock("docker", "exit 0")
    mock("dpkg-query", "exit 1")
    result, log = run(INSTALLER, "2\nn\n", main=True)
    assert result.returncode == 1
    assert "  - docker.io" in result.stdout
    assert "docker info" not in log


@pytest.mark.parametrize("dry", [False, True])
def test_available_remote_rejected_without_docker_commands(shell, dry):
    run, mock, _, env = shell
    env["DOCKER_HOST"] = "tcp://remote:2376"
    mock("docker", "exit 0")
    mock("dpkg-query", "exit 1")
    code = ('set -- --dry-run\n' if dry else '') + INSTALLER
    result, log = run(code, "2\n", main=True)
    assert result.returncode == 1
    assert "Local STT requires a local Docker unix endpoint" in result.stderr
    assert "docker " not in log and "sudo " not in log
    if dry:
        assert "Missing packages" in result.stdout


def test_context_precedence_and_rootless_preflight(shell):
    import json

    run, mock, home, env = shell
    env["DOCKER_HOST"] = "tcp://remote:2376"
    env["DOCKER_CONTEXT"] = "rootless"
    meta = home / ".docker/contexts/meta/example"
    meta.mkdir(parents=True)
    (meta / "meta.json").write_text(json.dumps({
        "Name": "rootless", "Endpoints": {"docker": {"Host": "unix:///run/user/1000/docker.sock"}}
    }), encoding="utf-8")
    mock("docker", "exit 0")
    mock("dpkg-query", "exit 1")
    result, log = run(FUNCTIONS + "\nprepare_docker")
    assert result.returncode == 0
    assert log == "docker --host unix:///run/user/1000/docker.sock info\n"
    result, _ = run('set -- --dry-run\n' + INSTALLER, "2\n", main=True)
    assert result.returncode == 0
    assert "  - docker.io" not in result.stdout


def test_prepare_rejects_available_remote_before_info(shell):
    run, mock, _, env = shell
    env["DOCKER_HOST"] = "ssh://docker.example"
    mock("docker", "exit 0")
    result, log = run(FUNCTIONS + "\nprepare_docker")
    assert result.returncode == 1
    assert "Local STT requires a local Docker unix endpoint" in result.stderr
    assert log == ""


def test_selected_context_from_config_is_used_without_docker(shell):
    import json

    run, mock, home, _ = shell
    meta = home / ".docker/contexts/meta/remote"
    meta.mkdir(parents=True)
    (home / ".docker/config.json").write_text(json.dumps({"currentContext": "remote"}),
                                             encoding="utf-8")
    (meta / "meta.json").write_text(json.dumps({
        "Name": "remote", "Endpoints": {"docker": {"Host": "tcp://remote:2376"}}
    }), encoding="utf-8")
    mock("docker", "exit 0")
    result, log = run(FUNCTIONS + "\nprepare_docker")
    assert result.returncode == 1
    assert "Local STT requires" in result.stderr
    assert log == ""


def test_default_context_pins_host_and_clears_remote_environment(shell):
    run, mock, _, env = shell
    env["DOCKER_CONTEXT"] = "default"
    env["DOCKER_HOST"] = "ssh://remote"
    mock("systemctl", "exit 0")
    mock("docker", '''
if [ -n "${DOCKER_CONTEXT:-}${DOCKER_HOST:-}" ]; then exit 91; fi
if [[ "$1" != --host || "$2" != unix:///var/run/docker.sock ]]; then exit 92; fi
exit 0
''')
    result, log = run(FUNCTIONS + '\nprepare_docker\n"${docker_cmd[@]}" version')
    assert result.returncode == 0, result.stderr
    assert "docker --host unix:///var/run/docker.sock info" in log
    assert "docker --host unix:///var/run/docker.sock version" in log
    assert "sudo " not in log


@pytest.mark.parametrize("context", [None, "custom"])
def test_no_python_bootstrap_full_preflight_without_mutations(shell, context):
    run, mock, home, env = shell
    if context:
        env["DOCKER_CONTEXT"] = context
    mock("dpkg-query", "exit 1")
    # Make Python unavailable to command discovery, and fail loudly if invoked.
    mock("python3", "exit 127")
    code = INSTALLER.replace("command -v python3", "command -v absent_typr_python3")
    result, log = run('set -- --dry-run\n' + code, "2\n", main=True)
    assert result.returncode == 0, result.stderr
    assert "  - python3" in result.stdout
    assert "  - docker.io" in result.stdout
    assert "  - udev" in result.stdout
    if context:
        assert "context validation deferred" in result.stderr
    assert not any(word in log for word in ("python3 ", "docker ", "sudo "))
    assert list(home.iterdir()) == []


def test_new_engine_installed_never_adds_docker_group(shell):
    run, mock, _, _ = shell
    mock("sudo", '''
if [[ "$1" = apt-get ]]; then touch "$HOME/packages_installed"; exit 0; fi
if [[ "$1" = usermod ]]; then exit 0; fi
exit 0
''')
    mock("dpkg-query", '''
if [ -f "$HOME/packages_installed" ]; then
    printf 'ok installed\\n'
    exit 0
fi
exit 1
''')
    marker = 'authorize_system_changes\nif [ "$stt_choice" != 4 ]; then'
    code = INSTALLER.replace(marker, "exit 42\n")
    result, log = run(code, "2\ny\n", main=True)
    assert result.returncode == 42
    assert "sudo usermod -aG docker" not in log
    assert "root-equivalent access" not in result.stdout
    assert "to the 'docker' group" not in result.stdout
    assert "usermod -aG docker" not in INSTALLER
    assert 'sudo usermod -aG input "$USER"' in INSTALLER


@pytest.mark.parametrize("already_in_group", [False, True])
def test_existing_engine_or_existing_group_does_not_modify_group(shell, already_in_group):
    run, mock, _, _ = shell
    mock("sudo", '''
if [[ "$1" = apt-get ]]; then touch "$HOME/packages_installed"; exit 0; fi
exit 0
''')
    if already_in_group:
        # Engine was missing and installed, but user is already in docker group.
        mock("id", '''
if [[ "$*" =~ [Gg] ]]; then
    printf 'docker other\\n'
else
    printf '1000\\n'
fi
''')
        mock("dpkg-query", '''
if [ -f "$HOME/packages_installed" ]; then
    printf 'ok installed\\n'
    exit 0
fi
exit 1
''')
    else:
        # Engine is already installed before preflight.
        mock("dpkg-query", '''
if [[ "$*" = *"docker.io"* ]]; then
    printf 'ok installed\\n'
    exit 0
fi
if [ -f "$HOME/packages_installed" ]; then
    printf 'ok installed\\n'
    exit 0
fi
exit 1
''')
    marker = 'authorize_system_changes\nif [ "$stt_choice" != 4 ]; then'
    code = INSTALLER.replace(marker, "exit 42\n")
    result, log = run(code, "2\ny\n", main=True)
    assert result.returncode == 42
    assert "sudo usermod -aG docker" not in log
    assert "root-equivalent access" not in result.stdout


def test_other_deps_or_no_local_never_adds_docker_group(shell):
    run, mock, _, env = shell
    mock("sudo", '''
if [[ "$1" = apt-get ]]; then touch "$HOME/packages_installed"; exit 0; fi
exit 0
''')
    mock("dpkg-query", '''
if [ -f "$HOME/packages_installed" ]; then
    printf 'ok installed\\n'
    exit 0
fi
exit 1
''')
    marker = 'authorize_system_changes\nif [ "$stt_choice" != 4 ]; then'
    code = INSTALLER.replace(marker, "exit 42\n")

    # 1. No local STT (choice 4)
    result, log = run(code, "4\ny\n", main=True)
    assert result.returncode == 42
    assert "sudo usermod -aG docker" not in log
    assert "root-equivalent access" not in result.stdout

    # 2. Custom rootless endpoint with local STT
    env["DOCKER_HOST"] = "unix:///run/user/1000/docker.sock"
    mock("docker", "exit 0")
    result2, log2 = run(code, "2\ny\n", main=True)
    assert result2.returncode == 42
    assert "sudo usermod -aG docker" not in log2
    assert "root-equivalent access" not in result2.stdout
