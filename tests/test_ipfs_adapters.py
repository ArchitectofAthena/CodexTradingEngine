import json

from eve_q.ipfs_adapters import (
    KuboHttpIpfsWriter,
    multipart_body,
)

CID = "b" + "a" * 40


def test_multipart_body_contains_receipt_bytes():
    body = multipart_body(
        boundary="BOUNDARY",
        field_name="file",
        filename="receipt.json",
        data=b'{"ok":true}',
        content_type="application/json",
    )

    assert b"--BOUNDARY" in body
    assert b'name="file"' in body
    assert b'filename="receipt.json"' in body
    assert b"Content-Type: application/json" in body
    assert b'{"ok":true}' in body
    assert body.endswith(b"--BOUNDARY--\r\n")


def test_kubo_endpoint_normalizes_url():
    writer = KuboHttpIpfsWriter(api_url="http://127.0.0.1:5001/")

    assert writer.endpoint("/api/v0/cat") == (
        "http://127.0.0.1:5001/api/v0/cat"
    )


def test_kubo_add_and_pin_uses_hash_response(monkeypatch):
    calls = []

    def fake_post_bytes(url, data, headers, timeout_seconds, **kwargs):
        calls.append(
            {
                "url": url,
                "data": data,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
                **kwargs,
            }
        )
        return json.dumps({"Hash": CID}).encode("utf-8")

    monkeypatch.setattr(
        "eve_q.ipfs_adapters.post_bytes",
        fake_post_bytes,
    )

    writer = KuboHttpIpfsWriter(api_url="http://127.0.0.1:5001")
    cid = writer.add_and_pin(b'{"receipt":true}')

    assert cid == CID
    assert calls[0]["url"] == (
        "http://127.0.0.1:5001/api/v0/add?pin=true&cid-version=1"
    )
    assert "multipart/form-data" in calls[0]["headers"]["Content-Type"]
    assert b'{"receipt":true}' in calls[0]["data"]
    assert calls[0]["allow_remote"] is False


def test_kubo_cat_posts_to_local_api(monkeypatch):
    calls = []

    def fake_post_bytes(url, data, headers, timeout_seconds, **kwargs):
        calls.append(
            {
                "url": url,
                "data": data,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
                **kwargs,
            }
        )
        return b"receipt-bytes"

    monkeypatch.setattr(
        "eve_q.ipfs_adapters.post_bytes",
        fake_post_bytes,
    )

    writer = KuboHttpIpfsWriter()
    result = writer.cat(CID)

    assert result == b"receipt-bytes"
    assert calls[0]["url"] == (
        f"http://127.0.0.1:5001/api/v0/cat?arg={CID}"
    )
    assert calls[0]["data"] == b""


def test_kubo_pin_check_returns_true_when_cid_present(monkeypatch):
    def fake_post_bytes(url, data, headers, timeout_seconds, **kwargs):
        payload = {
            "Keys": {
                CID: {
                    "Type": "recursive",
                }
            }
        }
        return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(
        "eve_q.ipfs_adapters.post_bytes",
        fake_post_bytes,
    )

    writer = KuboHttpIpfsWriter()

    assert writer.is_pinned(CID) is True


def test_kubo_pin_check_returns_false_when_cid_missing(monkeypatch):
    def fake_post_bytes(url, data, headers, timeout_seconds, **kwargs):
        return json.dumps({"Keys": {}}).encode("utf-8")

    monkeypatch.setattr(
        "eve_q.ipfs_adapters.post_bytes",
        fake_post_bytes,
    )

    writer = KuboHttpIpfsWriter()

    assert writer.is_pinned(CID) is False


def test_kubo_pin_check_returns_false_on_api_error(monkeypatch):
    def fake_post_bytes(url, data, headers, timeout_seconds, **kwargs):
        raise RuntimeError("local daemon unavailable")

    monkeypatch.setattr(
        "eve_q.ipfs_adapters.post_bytes",
        fake_post_bytes,
    )

    writer = KuboHttpIpfsWriter()

    assert writer.is_pinned(CID) is False
