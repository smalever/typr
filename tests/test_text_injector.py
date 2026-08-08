from unittest.mock import Mock

from typr.core.text_injector import TextInjector


def _injector() -> TextInjector:
    injector = TextInjector.__new__(TextInjector)
    injector._clipboard_restore_timer = None
    injector._clipboard_process = None
    injector._backup_text = "original"
    injector._has_backup = True
    injector._pasted_text = "pasted"
    injector._ui = None
    injector._available = False
    return injector


def test_restore_tracks_replacement_clipboard_process(monkeypatch) -> None:
    injector = _injector()
    restored_process = Mock()
    restored_process.poll.return_value = None
    monkeypatch.setattr(injector, "_detect_clipboard_backend", lambda: "wl-copy")
    monkeypatch.setattr(injector, "_terminate_clipboard_process", Mock())
    monkeypatch.setattr(
        injector,
        "_spawn_clipboard_backend",
        lambda backend, text: restored_process,
    )
    monkeypatch.setattr(
        "typr.core.text_injector.subprocess.run",
        lambda *args, **kwargs: Mock(returncode=0, stdout=b"pasted"),
    )

    injector._restore_clipboard()

    assert injector._clipboard_process is restored_process


def test_restore_preserves_new_user_clipboard_content(monkeypatch) -> None:
    injector = _injector()
    terminate = Mock()
    spawn = Mock()
    monkeypatch.setattr(injector, "_detect_clipboard_backend", lambda: "wl-copy")
    monkeypatch.setattr(injector, "_terminate_clipboard_process", terminate)
    monkeypatch.setattr(injector, "_spawn_clipboard_backend", spawn)
    monkeypatch.setattr(
        "typr.core.text_injector.subprocess.run",
        lambda *args, **kwargs: Mock(returncode=0, stdout=b"new user text"),
    )

    injector._restore_clipboard()

    terminate.assert_called_once_with()
    spawn.assert_not_called()


def test_cleanup_stops_timer_and_clipboard_process(monkeypatch) -> None:
    injector = _injector()
    timer = Mock()
    injector._clipboard_restore_timer = timer
    terminate = Mock()
    monkeypatch.setattr(injector, "_terminate_clipboard_process", terminate)

    injector.cleanup()

    timer.stop.assert_called_once_with()
    timer.deleteLater.assert_called_once_with()
    terminate.assert_called_once_with()
    assert injector._clipboard_restore_timer is None
