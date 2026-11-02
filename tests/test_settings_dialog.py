from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest

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


def test_gigastt_settings_disable_ignored_options() -> None:
    assert settings_dialog._is_gigastt_settings(
        "http://127.0.0.1:9876/v1", "gigaam-v3-rnnt"
    )
    assert not settings_dialog._is_gigastt_settings(
        "http://127.0.0.1:5092/v1", "parakeet-tdt-0.6b-v3"
    )


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
        if request.url.path == "/openapi.json":
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


PARAKEET_SCHEMA = {
    "info": {"title": "Parakeet TDT 0.6B v3 (optimized)"},
    "paths": {
        "/health": {"get": {}}, "/healthz": {"get": {}},
        "/v1/audio/transcriptions": {"post": {"requestBody": {"content": {
            "multipart/form-data": {"schema": {
                "$ref": "#/components/schemas/Body_transcribe_v1_audio_transcriptions_post",
            }},
        }}}},
    },
    "components": {"schemas": {"Body_transcribe_v1_audio_transcriptions_post": {
        "properties": {"model": {"type": "string", "default": "parakeet-tdt-0.6b-v3"}},
    }}},
}
PARAKEET_HEALTH = {
    "ready": True, "models": ["parakeet-tdt-0.6b-v3", "not-loaded"],
    "loaded": ["parakeet-tdt-0.6b-v3"], "default_model": "parakeet-tdt-0.6b-v3",
}


@pytest.mark.parametrize("probe", [False, True])
def test_parakeet_loaded_models_with_deployment_prefix(monkeypatch, probe):
    paths = []

    def handler(request):
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer fake"
        paths.append(request.url.path)
        if request.url.path in ("/stt/v1/models", "/stt/v1/audio/models"):
            return httpx.Response(404)
        if request.url.path == "/stt/openapi.json":
            return httpx.Response(200, json=PARAKEET_SCHEMA)
        assert request.url.path == "/stt/health"
        return httpx.Response(200, json=PARAKEET_HEALTH)

    with _mock_client(monkeypatch, handler):
        if probe:
            assert settings_dialog._probe_api("https://example.test/stt/v1", "fake") is False
        else:
            assert settings_dialog._request_models("https://example.test/stt/v1", "fake") == [
                "parakeet-tdt-0.6b-v3",
            ]
    assert paths[-1] == "/stt/health"


@pytest.mark.parametrize("operation", [settings_dialog._request_models, settings_dialog._probe_api])
@pytest.mark.parametrize("health", [
    [], {}, {**PARAKEET_HEALTH, "ready": False},
    {**PARAKEET_HEALTH, "loaded": []},
    {**PARAKEET_HEALTH, "loaded": ["unknown"]},
    {**PARAKEET_HEALTH, "models": "invalid"},
    {**PARAKEET_HEALTH, "loaded": [None]},
])
def test_parakeet_invalid_or_notready_health(monkeypatch, operation, health):
    def handler(request):
        if request.url.path.endswith("models"):
            return httpx.Response(404)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json=PARAKEET_SCHEMA)
        return httpx.Response(200, json=health)

    with _mock_client(monkeypatch, handler), pytest.raises(ValueError):
        operation("https://example.test/v1", "")


@pytest.mark.parametrize("status", [401, 403, 503])
@pytest.mark.parametrize("operation", [settings_dialog._request_models, settings_dialog._probe_api])
def test_parakeet_health_errors_propagate(monkeypatch, status, operation):
    def handler(request):
        if request.url.path.endswith("models"):
            return httpx.Response(404)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json=PARAKEET_SCHEMA)
        return httpx.Response(status)

    with _mock_client(monkeypatch, handler), pytest.raises(httpx.HTTPStatusError) as error:
        operation("https://example.test/v1", "")
    assert error.value.response.status_code == status


def test_unknown_service_does_not_use_parakeet_health(monkeypatch):
    def handler(request):
        if request.url.path.endswith("models"):
            return httpx.Response(404)
        assert request.url.path == "/openapi.json"
        return httpx.Response(200, json={**PARAKEET_SCHEMA, "info": {"title": "Other"}})

    with _mock_client(monkeypatch, handler):
        assert settings_dialog._request_models("https://example.test/v1", "") == []


def test_generic_404_never_returns_static_models(monkeypatch):
    def handler(request):
        assert request.url.path != "/health"
        return httpx.Response(404)

    with _mock_client(monkeypatch, handler), pytest.raises(httpx.HTTPStatusError):
        settings_dialog._request_models("https://example.test/v1", "")


@pytest.mark.parametrize("path", ["/v1/models", "/openapi.json"])
@pytest.mark.parametrize("operation", [settings_dialog._request_models, settings_dialog._probe_api])
@pytest.mark.parametrize("status", [401, 403])
def test_discovery_auth_error_does_not_fall_back(monkeypatch, path, operation, status):
    def handler(request):
        if request.url.path == path:
            return httpx.Response(status)
        assert request.url.path in ("/v1/models", "/v1/audio/models")
        return httpx.Response(404)

    with _mock_client(monkeypatch, handler), pytest.raises(httpx.HTTPStatusError) as error:
        operation("https://example.test/v1", "fake")
    assert error.value.response.status_code == status


@pytest.mark.parametrize("schema_response", [
    httpx.Response(200, text="<html>Proxy landing page</html>"),
    httpx.Response(503), httpx.Response(200, json=[]),
    httpx.Response(200, json={"info": None}),
    httpx.ConnectError("Optional schema unavailable"),
])
def test_generic_connection_does_not_require_openapi(monkeypatch, schema_response):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/v1/models":
            return httpx.Response(404)
        if request.url.path == "/openapi.json":
            if isinstance(schema_response, Exception):
                raise schema_response
            return schema_response
        assert request.method == "OPTIONS"
        assert request.url.path == "/v1/audio/transcriptions"
        return httpx.Response(405)

    with _mock_client(monkeypatch, handler):
        assert settings_dialog._probe_api("https://example.test/v1", "") is True
    assert paths[-1] == "/v1/audio/transcriptions"


def test_identified_parakeet_health_transport_error_never_probes_options(monkeypatch):
    def handler(request):
        assert request.method == "GET"
        if request.url.path == "/v1/models":
            return httpx.Response(404)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json=PARAKEET_SCHEMA)
        assert request.url.path == "/health"
        raise httpx.ConnectError("Health unavailable")

    with _mock_client(monkeypatch, handler), pytest.raises(httpx.ConnectError):
        settings_dialog._probe_api("https://example.test/v1", "")
