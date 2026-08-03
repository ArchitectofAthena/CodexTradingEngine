import os

import pytest

from eve_q.ipfs_adapters import DEFAULT_KUBO_API_URL, KuboHttpIpfsWriter


def test_live_kubo_http_roundtrip() -> None:
    if os.environ.get("EVEQ_LIVE_KUBO_TEST") != "1":
        pytest.skip("set EVEQ_LIVE_KUBO_TEST=1 for local Kubo exercise")

    writer = KuboHttpIpfsWriter(
        api_url=os.environ.get("EVEQ_KUBO_API_URL", DEFAULT_KUBO_API_URL),
        timeout_seconds=20,
        max_add_bytes=1024,
        max_response_bytes=1024,
    )
    payload = b"eve-q-live-kubo-integration-v0.2"
    cid = writer.add_and_pin(payload)

    assert writer.is_pinned(cid) is True
    assert writer.cat(cid) == payload
