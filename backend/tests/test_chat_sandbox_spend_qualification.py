import asyncio

from backend.scripts import qualify_chat_sandbox_spend


def test_deliver_all_spend_alerts_drains_bounded_batches(monkeypatch):
    batches = iter((10, 2, 0))

    class Manager:
        def __init__(self, settings):
            assert settings is sentinel

        async def deliver_spend_alerts(self):
            return next(batches)

    sentinel = object()
    monkeypatch.setattr(qualify_chat_sandbox_spend, "SandboxSessionManager", Manager)

    assert (
        asyncio.run(qualify_chat_sandbox_spend.deliver_all_spend_alerts(sentinel)) == 12
    )
