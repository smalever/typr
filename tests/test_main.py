"""Entrypoint lifecycle tests: no QApplication/widgets or native components."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QCoreApplication, QTimer


@pytest.fixture
def entrypoint(monkeypatch):
    boundary = ModuleType("typr.app")
    boundary.TyprApp = Mock()
    monkeypatch.setitem(sys.modules, "typr.app", boundary)
    path = Path(__file__).parents[1] / "src/typr/__main__.py"
    spec = importlib.util.spec_from_file_location("typr._main_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "QApplication", Mock())
    return module


@pytest.mark.parametrize("failure", ["start", "exec", None])
def test_main_finally_always_uses_cleanup(entrypoint, failure):
    module = entrypoint
    app, typr = module.QApplication.return_value, module.TyprApp.return_value
    cleanup = Mock()
    module._cleanup = cleanup
    app.exec.return_value = 7
    if failure:
        target = typr.start if failure == "start" else app.exec
        target.side_effect = RuntimeError("mock lifecycle failure")
        with pytest.raises(RuntimeError, match="mock lifecycle failure"):
            module.main()
    else:
        with pytest.raises(SystemExit) as exit_info:
            module.main()
        assert exit_info.value.code == 7
    cleanup.assert_called_once_with(typr)


@pytest.mark.parametrize("outer_loop_exited", [False, True])
def test_cleanup_pumps_qt_until_controller_barrier_completes(entrypoint, outer_loop_exited):
    core = QCoreApplication.instance() or QCoreApplication([])
    if outer_loop_exited:
        QTimer.singleShot(0, core.quit)
        core.exec()
    typr = Mock(_quit_completed=False)

    def quit_request():
        QTimer.singleShot(0, lambda: setattr(typr, "_quit_completed", True))

    typr._quit.side_effect = quit_request
    entrypoint._cleanup(typr)
    assert core is not None
    assert typr._quit_completed
    typr._quit.assert_called_once()
