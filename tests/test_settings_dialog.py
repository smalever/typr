from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from typr.config import AppConfig
from typr.ui import settings_dialog


@contextmanager
def _mock_client(monkeypatch, handler) -> Iterator[None]:
    transport = httpx.MockTransport(handler)
    client_class = httpx.Client

    def client_factory(*args, **kwargs):
        return client_class(transport=transport, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(settings_dialog.httpx, "Client", client_factory)
    yield


def test_app_config_uses_local_parakeet_defaults() -> None:
    config = AppConfig()

    assert config.api_base_url == "http://127.0.0.1:5092/v1"
    assert config.transcription.model == "parakeet-tdt-0.6b-v3"
    assert config.hotkeys.push_to_talk == "Ctrl+Alt+Z"
    assert settings_dialog.SettingsDialog.DEFAULT_MODELS[0][0] == config.transcription.model


def test_request_models_falls_back_to_openapi_schema(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("/v1/models", "/v1/audio/models"):
            return httpx.Response(404, request=request)
        assert request.url.path == "/openapi.json"
        return httpx.Response(
            200,
            request=request,
            json={
                "paths": {
                    "/v1/audio/transcriptions": {
                        "post": {
                            "requestBody": {
                                "content": {
                                    "multipart/form-data": {
                                        "schema": {
                                            "properties": {
                                                "model": {"enum": ["model-b", "model-a"]}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
        )

    with _mock_client(monkeypatch, handler):
        models = settings_dialog._request_models("https://example.test/v1", "secret")

    assert models == ["model-a", "model-b"]


def test_request_models_accepts_single_model_object(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "gigaam-v3-rnnt",
                "name": "GigaAM v3 RNN-T",
                "variant": "rnnt",
            },
        )

    with _mock_client(monkeypatch, handler):
        models = settings_dialog._request_models("http://127.0.0.1:9876/v1", "")

    assert models == ["gigaam-v3-rnnt"]


def test_probe_api_accepts_transcription_fallback(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(404, request=request)
        assert request.method == "OPTIONS"
        assert request.url.path == "/v1/audio/transcriptions"
        return httpx.Response(405, request=request)

    with _mock_client(monkeypatch, handler):
        used_fallback = settings_dialog._probe_api("https://example.test/v1", "")

    assert used_fallback is True


def test_api_request_reports_background_errors() -> None:
    worker = settings_dialog._ApiRequest(lambda: 1 / 0)
    errors: list[object] = []
    worker.signals.failed.connect(errors.append)

    worker.run()

    assert len(errors) == 1
    assert isinstance(errors[0], ZeroDivisionError)
