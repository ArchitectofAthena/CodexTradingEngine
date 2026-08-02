import json
from urllib import request

import pytest

from eve_q.ipfs_adapters import (
    KuboHttpIpfsWriter,
    post_bytes,
    validate_cid,
    validate_kubo_api_url,
)

CID = "b" + "a" * 40


class FakeResponse:
    def __init__(self, payload: bytes, *, content_length: int | None = None):
        self.payload = payload
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit: int = -1) -> bytes:
        return self.payload if limit < 0 else self.payload[:limit]


def test_kubo_url_is_loopback_only_by_default():
    assert validate_kubo_api_url("http://127.0.0.1:5001")
    assert validate_kubo_api_url("http://localhost:5001")
    assert validate_kubo_api_url("http://[::1]:5001")

    with pytest.raises(ValueError, match="must be loopback"):
        KuboHttpIpfsWriter(api_url="http://192.0.2.10:5001")


def test_remote_kubo_requires_explicit_override():
    writer = KuboHttpIpfsWriter(
        api_url="https://kubo.example.test:5001",
        allow_remote=True,
    )
    assert writer.endpoint("/api/v0/version").startswith(
        "https://kubo.example.test:5001/"
    )


def test_kubo_url_rejects_embedded_credentials():
    with pytest.raises(ValueError, match="must not contain credentials"):
        KuboHttpIpfsWriter(api_url="http://user:pass@127.0.0.1:5001")


def test_cid_validation_is_fail_closed():
    assert validate_cid(CID) == CID
    with pytest.raises(ValueError, match="CIDv1 base32"):
        validate_cid("not-a-cid")


def test_add_rejects_oversized_payload_before_network(monkeypatch):
    called = False

    def fail_urlopen(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be reached")

    monkeypatch.setattr(request, "urlopen", fail_urlopen)
    writer = KuboHttpIpfsWriter(max_add_bytes=4)

    with pytest.raises(ValueError, match="max_add_bytes=4"):
        writer.add_and_pin(b"12345")
    assert called is False


def test_add_returns_validated_cid(monkeypatch):
    observed = {}

    def fake_urlopen(req, timeout):
        observed["url"] = req.full_url
        observed["timeout"] = timeout
        return FakeResponse(json.dumps({"Hash": CID}).encode())

    monkeypatch.setattr(request, "urlopen", fake_urlopen)
    writer = KuboHttpIpfsWriter(timeout_seconds=3)

    assert writer.add_and_pin(b"receipt") == CID
    assert "pin=true" in observed["url"]
    assert "cid-version=1" in observed["url"]
    assert observed["timeout"] == 3


def test_add_rejects_malformed_cid_from_kubo(monkeypatch):
    monkeypatch.setattr(
        request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b'{"Hash":"malformed"}'),
    )

    with pytest.raises(ValueError, match="CIDv1 base32"):
        KuboHttpIpfsWriter().add_and_pin(b"receipt")


def test_cat_enforces_response_ceiling(monkeypatch):
    monkeypatch.setattr(
        request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b"12345"),
    )

    with pytest.raises(ValueError, match="max_response_bytes=4"):
        KuboHttpIpfsWriter(max_response_bytes=4).cat(CID)


def test_content_length_is_checked_before_body_read(monkeypatch):
    monkeypatch.setattr(
        request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b"x", content_length=100),
    )

    with pytest.raises(ValueError, match="max_response_bytes=4"):
        post_bytes(
            "http://127.0.0.1:5001/api/v0/version",
            b"",
            {},
            timeout_seconds=1,
            max_response_bytes=4,
        )


def test_pin_check_requires_recursive_key(monkeypatch):
    responses = [
        FakeResponse(json.dumps({"Keys": {CID: {"Type": "recursive"}}}).encode()),
        FakeResponse(json.dumps({"Keys": {}}).encode()),
    ]

    monkeypatch.setattr(
        request,
        "urlopen",
        lambda *args, **kwargs: responses.pop(0),
    )
    writer = KuboHttpIpfsWriter()

    assert writer.is_pinned(CID) is True
    assert writer.is_pinned(CID) is False
