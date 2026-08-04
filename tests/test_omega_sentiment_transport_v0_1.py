from __future__ import annotations

import json

import pytest

from omega_telemetry.sentiment_tracker import (
    FeedAdapter,
    FeedBoundaryError,
    build_sources,
    ip_is_public,
    read_bounded_body,
    validate_feed_url,
    validate_source_config,
)


class FakeContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def iter_chunked(self, size: int):
        del size
        for chunk in self.chunks:
            yield chunk


class FakeResponse:
    def __init__(self, chunks: list[bytes], content_length: str | None = None) -> None:
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.content = FakeContent(chunks)


def source(**overrides):
    payload = {
        "name": "fixture",
        "type": "json",
        "url": "https://feeds.example.com/signals.json",
        "allowed_hosts": ["feeds.example.com"],
        "items_path": ["items"],
        "timeout_seconds": 10,
        "max_response_bytes": 4096,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "url",
    [
        "http://feeds.example.com/signals.json",
        "file:///tmp/feed.json",
        "https://user:secret@feeds.example.com/signals.json",
        "https://other.example.com/signals.json",
    ],
)
def test_feed_url_validation_fails_closed(url):
    with pytest.raises(FeedBoundaryError):
        validate_feed_url(url, ["feeds.example.com"])


def test_feed_url_requires_exact_host_not_suffix_match():
    with pytest.raises(FeedBoundaryError, match="not allowlisted"):
        validate_feed_url(
            "https://attacker-feeds.example.com/signals.json",
            ["feeds.example.com"],
        )


def test_private_and_loopback_ip_literals_are_rejected():
    cases = [
        ("127.0.0.1", "https://127.0.0.1/signals.json"),
        ("10.0.0.1", "https://10.0.0.1/signals.json"),
        ("169.254.1.1", "https://169.254.1.1/signals.json"),
        ("::1", "https://[::1]/signals.json"),
    ]
    for value, url in cases:
        assert ip_is_public(value) is False
        with pytest.raises(FeedBoundaryError, match="not public"):
            validate_feed_url(url, [value])


def test_source_policy_requires_bounds_and_allowlist():
    with pytest.raises(FeedBoundaryError, match="allowlist"):
        validate_source_config(source(allowed_hosts=[]))
    with pytest.raises(FeedBoundaryError, match="at most 60"):
        validate_source_config(source(timeout_seconds=61))
    with pytest.raises(FeedBoundaryError, match="max_response_bytes"):
        validate_source_config(source(max_response_bytes=20_000_000))


@pytest.mark.asyncio
async def test_bounded_body_accepts_payload_at_limit():
    response = FakeResponse([b"ab", b"cd"], content_length="4")

    body = await read_bounded_body(response, 4)  # type: ignore[arg-type]

    assert body == b"abcd"


@pytest.mark.asyncio
async def test_bounded_body_rejects_declared_or_streamed_overflow():
    declared = FakeResponse([b"abcd"], content_length="5")
    with pytest.raises(FeedBoundaryError, match="exceeds"):
        await read_bounded_body(declared, 4)  # type: ignore[arg-type]

    streamed = FakeResponse([b"abc", b"de"])
    with pytest.raises(FeedBoundaryError, match="exceeds"):
        await read_bounded_body(streamed, 4)  # type: ignore[arg-type]


def test_json_feed_parser_requires_list_of_objects():
    adapter = FeedAdapter(object(), source())  # type: ignore[arg-type]
    good = adapter._parse_json(json.dumps({"items": [{"id": "one"}]}).encode())
    assert good == [{"id": "one"}]

    with pytest.raises(FeedBoundaryError, match="list of objects"):
        adapter._parse_json(json.dumps({"items": ["one"]}).encode())


def test_build_sources_validates_every_entry():
    copied = build_sources([source()])
    assert copied[0]["allowed_hosts"] == ["feeds.example.com"]

    with pytest.raises(FeedBoundaryError):
        build_sources([source(url="http://feeds.example.com/signals.json")])
