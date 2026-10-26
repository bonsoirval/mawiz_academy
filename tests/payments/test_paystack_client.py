"""Unit tests for Paystack's HTTP adapter; these tests never call the network."""

import io
import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.learning.routes import _minor_units, _paystack_request, _validated_paystack_checkout_url


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_minor_units_converts_naira_to_kobo():
    assert _minor_units("12500.00") == 1_250_000
    assert _minor_units("0.01") == 1
    assert _minor_units("0") == 0


def test_paystack_request_parses_successful_response(app, monkeypatch):
    app.config["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test_key"
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["authorization"] = request.get_header("Authorization")
        captured["user_agent"] = request.get_header("User-agent")
        captured["connection"] = request.get_header("Connection")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"status": True, "data": {"reference": "test-ref"}})

    monkeypatch.setattr("app.learning.routes.urlopen", fake_urlopen)
    with app.test_request_context("/test"):
        result = _paystack_request("/transaction/initialize", "POST", {"amount": 10000})
    assert result == {"reference": "test-ref"}
    assert captured["url"] == "https://api.paystack.co/transaction/initialize"
    assert captured["method"] == "POST"
    assert captured["authorization"] == "Bearer sk_test_unit_test_key"
    assert captured["user_agent"] == "MawizAcademy-Payments/1.0"
    assert captured["connection"] == "close"
    assert captured["body"] == {"amount": 10000}
    assert captured["timeout"] == app.config["PAYSTACK_TIMEOUT_SECONDS"]


def test_paystack_request_fails_when_secret_is_missing(app):
    app.config["PAYSTACK_SECRET_KEY"] = ""
    with app.test_request_context("/test"):
        with pytest.raises(RuntimeError, match="PAYSTACK_SECRET_KEY"):
            _paystack_request("/transaction/initialize", "POST", {"amount": 10000})


def test_paystack_request_rejects_non_https_api_base_url(app):
    app.config["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test_key"
    app.config["PAYSTACK_API_BASE_URL"] = "http://api.paystack.co"
    with app.test_request_context("/test"):
        with pytest.raises(RuntimeError, match="HTTPS"):
            _paystack_request("/transaction/initialize")


def test_paystack_request_handles_invalid_json(app, monkeypatch):
    class InvalidJsonResponse(FakeResponse):
        def read(self):
            return b"not-json"

    app.config["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test_key"
    monkeypatch.setattr("app.learning.routes.urlopen", lambda *_a, **_k: InvalidJsonResponse({}))
    with app.test_request_context("/test"):
        with pytest.raises(RuntimeError, match="invalid response"):
            _paystack_request("/transaction/initialize")


def test_paystack_request_handles_transport_errors(app, monkeypatch):
    app.config["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test_key"
    monkeypatch.setattr(
        "app.learning.routes.urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(URLError("DNS unavailable")),
    )
    with app.test_request_context("/test"):
        with pytest.raises(RuntimeError, match="Could not connect to Paystack"):
            _paystack_request("/transaction/initialize")



def test_checkout_url_accepts_paystack_https_checkout():
    assert _validated_paystack_checkout_url(
        "https://checkout.paystack.com/session-token"
    ) == "https://checkout.paystack.com/session-token"


@pytest.mark.parametrize("url", [
    "http://checkout.paystack.com/session-token",
    "https://evil.example/session-token",
    "https://checkout.paystack.com.evil.example/session-token",
    "https://user@checkout.paystack.com/session-token",
    "",
])
def test_checkout_url_rejects_untrusted_destinations(url):
    with pytest.raises(RuntimeError, match="invalid secure checkout URL"):
        _validated_paystack_checkout_url(url)


def test_paystack_request_reports_non_json_403_as_possible_gateway_or_network_block(app, monkeypatch):
    app.config["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test_key"
    headers = Message()
    headers.add_header("Content-Type", "text/html; charset=utf-8")

    def rejected_request(*_args, **_kwargs):
        raise HTTPError(
            "https://api.paystack.co/transaction/initialize",
            403,
            "Forbidden",
            headers,
            BytesIO(b"<html>blocked</html>"),
        )

    monkeypatch.setattr("app.learning.routes.urlopen", rejected_request)
    with app.test_request_context("/test"):
        with pytest.raises(RuntimeError, match="non-JSON HTTP 403.*outbound proxy/WAF"):
            _paystack_request("/transaction/initialize", "POST", {"amount": 10000})


def test_paystack_request_preserves_json_provider_error_message(app, monkeypatch):
    app.config["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test_key"
    headers = Message()
    headers.add_header("Content-Type", "application/json")

    def rejected_request(*_args, **_kwargs):
        raise HTTPError(
            "https://api.paystack.co/transaction/initialize",
            403,
            "Forbidden",
            headers,
            BytesIO(json.dumps({"status": False, "message": "API access denied"}).encode("utf-8")),
        )

    monkeypatch.setattr("app.learning.routes.urlopen", rejected_request)
    with app.test_request_context("/test"):
        with pytest.raises(RuntimeError, match="API access denied"):
            _paystack_request("/transaction/initialize", "POST", {"amount": 10000})
