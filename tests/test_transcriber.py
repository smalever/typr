import httpx

from typr.core.transcriber import _api_error_message, _request_timeout


def _response(payload: object) -> httpx.Response:
    request = httpx.Request("POST", "http://127.0.0.1/v1/audio/transcriptions")
    return httpx.Response(400, request=request, json=payload)


def test_api_error_message_accepts_openai_shape() -> None:
    response = _response({"error": {"message": "bad audio"}})

    assert _api_error_message(response, "fallback") == "bad audio"


def test_api_error_message_accepts_gigastt_shape() -> None:
    response = _response({"error": "pool exhausted", "code": "busy"})

    assert _api_error_message(response, "fallback") == "pool exhausted (busy)"


def test_api_error_message_tolerates_other_shapes() -> None:
    assert _api_error_message(_response({"error": ["bad"]}), "fallback") == "fallback"
    assert _api_error_message(_response("bad"), "fallback") == "fallback"


def test_local_gigastt_uses_longer_read_timeout() -> None:
    gigastt = _request_timeout("http://127.0.0.1:9876/v1", "gigaam-v3-rnnt")
    parakeet = _request_timeout("http://127.0.0.1:5092/v1", "parakeet-tdt-0.6b-v3")

    assert gigastt.connect == 10.0
    assert gigastt.read == 120.0
    assert parakeet.read == 30.0
