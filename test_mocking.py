"""
Black-box testing has almost nothing safe to mock -- the only legitimate
target is this project's OWN test-infrastructure code, never the real app
under test. These tests prove a small retry helper behaves correctly under
conditions a real, healthy server won't reliably produce on demand.
"""
import httpx
import respx


def resilient_get(url: str, retries: int = 1) -> httpx.Response:
    last_error = None
    for _ in range(retries + 1):
        try:
            return httpx.get(url)
        except httpx.ConnectError as exc:
            last_error = exc
    raise last_error


def resilient_post(url: str, json: dict, retries: int = 1) -> httpx.Response:
    last_error = None
    for _ in range(retries + 1):
        try:
            return httpx.post(url, json=json)
        except httpx.ConnectError as exc:
            last_error = exc
    raise last_error


@respx.mock
def test_resilient_get_retries_once_after_a_connection_error():
    route = respx.get("http://fake-service.test/ping")
    route.side_effect = [
        httpx.ConnectError("simulated network failure"),
        httpx.Response(200, json={"ok": True}),
    ]

    response = resilient_get("http://fake-service.test/ping")

    assert response.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_resilient_post_retries_once_after_a_connection_error():
    route = respx.post("http://fake-service.test/submit")
    route.side_effect = [
        httpx.ConnectError("simulated network failure"),
        httpx.Response(201, json={"created": True}),
    ]

    response = resilient_post("http://fake-service.test/submit", json={"a": 1})

    assert response.status_code == 201
    assert route.call_count == 2
