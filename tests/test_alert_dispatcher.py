import pytest

from eve_q.alert_dispatcher import AlertDispatcher, RetryPolicy


class ExplodingSession:
    def post(self, *args, **kwargs):
        raise AssertionError("external HTTP call attempted")


@pytest.mark.asyncio
async def test_shadow_mode_never_sends_external_http():
    dispatcher = AlertDispatcher(
        session=ExplodingSession(),
        config={
            "telegram": {"enabled": True, "bot_token": "token", "chat_id": "chat"},
            "discord": {"enabled": True, "webhook_url": "https://discord.invalid/webhook"},
            "webhook": {"enabled": True, "url": "https://example.invalid/hook"},
        },
        shadow_mode=True,
    )

    results = await dispatcher.send(
        severity="high",
        title="Shadow alert",
        summary="This must not leave process memory.",
        dedupe_key="shadow-alert-1",
    )

    assert len(results) == 1
    assert results[0].channel == "shadow"
    assert results[0].delivered is True
    assert results[0].response == "shadow_mode_no_external_send"


@pytest.mark.asyncio
async def test_non_shadow_mode_requires_enabled_channel_config():
    dispatcher = AlertDispatcher(
        session=ExplodingSession(),
        config={
            "telegram": {"enabled": False, "bot_token": "token", "chat_id": "chat"},
            "discord": {"enabled": False, "webhook_url": "https://discord.invalid/webhook"},
            "webhook": {"enabled": False, "url": "https://example.invalid/hook"},
        },
        shadow_mode=False,
    )

    results = await dispatcher.send(
        severity="low",
        title="Disabled channels",
        summary="No enabled channel should produce an external effect.",
    )

    assert results == []


@pytest.mark.asyncio
async def test_deduplication_suppresses_repeat_shadow_alert():
    dispatcher = AlertDispatcher(
        session=ExplodingSession(),
        config={"webhook": {"enabled": True, "url": "https://example.invalid/hook"}},
        shadow_mode=True,
    )

    first = await dispatcher.send("low", "Once", "First", dedupe_key="same")
    second = await dispatcher.send("low", "Twice", "Second", dedupe_key="same")

    assert len(first) == 1
    assert second == []


@pytest.mark.asyncio
async def test_retry_policy_zero_retries_fails_closed_without_credentials():
    dispatcher = AlertDispatcher(
        session=ExplodingSession(),
        config={"telegram": {"enabled": True}},
        retry_policy=RetryPolicy(max_retries=0),
        shadow_mode=False,
    )

    results = await dispatcher.send("medium", "Missing creds", "Should fail closed")

    assert len(results) == 1
    assert results[0].channel == "telegram"
    assert results[0].delivered is False
    assert results[0].error == "missing_credentials"
