import asyncio
import json
import httpx
import pytest
from claros_sdk import ClarOSClient, EventEmitter, InboundMessageEvent


@pytest.mark.asyncio
async def test_event_emitter():
    emitter = EventEmitter()
    received_sync = []
    received_async = []

    def sync_handler(data):
        received_sync.append(data)

    async def async_handler(data):
        received_async.append(data)

    emitter.on("test.event", sync_handler)
    emitter.on("test.event", async_handler)

    await emitter.emit("test.event", {"msg": "hello"})

    assert received_sync == [{"msg": "hello"}]
    assert received_async == [{"msg": "hello"}]

    # Test off
    emitter.off("test.event", sync_handler)
    await emitter.emit("test.event", {"msg": "world"})
    assert len(received_sync) == 1
    assert len(received_async) == 2


@pytest.mark.asyncio
async def test_sse_inbound_stream_scoped_bots_and_reply():
    received_global_slack: list[InboundMessageEvent] = []
    received_abc_bot: list[InboundMessageEvent] = []
    received_xyz_bot: list[InboundMessageEvent] = []
    reply_requests = []

    raw_abc_event = {
        "event_id": "evt-123",
        "tenant_id": "tenant-uuid",
        "config_key": "ABC-bot",
        "channel_type": "slack",
        "received_at": "2026-08-26T12:00:00Z",
        "source": {
            "channel_id": "C123",
            "user_id": "U456",
            "message_id": "171000.1",
        },
        "message": {
            "text": "help me with my order",
        },
    }

    raw_xyz_event = {
        "event_id": "evt-456",
        "tenant_id": "tenant-uuid",
        "config_key": "XYZ-bot",
        "channel_type": "slack",
        "received_at": "2026-08-26T12:00:05Z",
        "source": {
            "channel_id": "C789",
            "user_id": "U999",
            "message_id": "171000.2",
        },
        "message": {
            "text": "where is my invoice?",
        },
    }

    stream_active = asyncio.Event()

    async def sse_generator():
        yield b": ping\n\n"
        await asyncio.sleep(0.01)
        # Send event 123
        yield f"id: evt-123\nevent: message\ndata: {json.dumps(raw_abc_event)}\n\n".encode("utf-8")
        await asyncio.sleep(0.01)
        # Send event 123 AGAIN to test automatic event deduplication
        yield f"id: evt-123\nevent: message\ndata: {json.dumps(raw_abc_event)}\n\n".encode("utf-8")
        await asyncio.sleep(0.01)
        # Send event 456
        yield f"id: evt-456\nevent: message\ndata: {json.dumps(raw_xyz_event)}\n\n".encode("utf-8")
        stream_active.set()
        while True:
            await asyncio.sleep(1)
            yield b": keepalive\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/oauth/token":
            return httpx.Response(
                200,
                json={"access_token": "mock-m2m-token-999", "expires_in": 3600},
            )
        elif request.url.path == "/api/v1/comm/inbound/stream":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=sse_generator(),
            )
        elif request.url.path == "/api/v1/comm/slack":
            reply_requests.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "delivered"})
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    client = ClarOSClient(
        base_url="https://api.claros.ai",
        client_id="sa_test_123",
        client_secret="sec_test_456",
        httpx_client=httpx_client,
    )

    # 1. Global Slack Listener
    @client.slack.on_message
    async def on_global_slack(event: InboundMessageEvent):
        received_global_slack.append(event)

    # 2. Scoped Bot Listeners
    @client.slack.bot("ABC-bot").on_message
    async def on_abc_bot(event: InboundMessageEvent):
        received_abc_bot.append(event)
        # 3. Contextual Auto-Reply
        await event.reply("Thanks! Looking into your order.")

    @client.slack.bot("XYZ-bot").on_message
    async def on_xyz_bot(event: InboundMessageEvent):
        received_xyz_bot.append(event)
        # Contextual Auto-Reply for billing bot
        await event.reply("Invoice sent to your email.")

    # Start stream task
    await client.start_stream()
    await asyncio.wait_for(stream_active.wait(), timeout=2.0)
    await asyncio.sleep(0.05)
    await client.stop_stream()

    # Verify Global listener received both (and deduplicated the duplicate evt-123)
    assert len(received_global_slack) == 2

    # Verify Scoped ABC-bot received ONLY its event ONCE (deduplicated)
    assert len(received_abc_bot) == 1
    assert received_abc_bot[0].config_key == "ABC-bot"
    assert received_abc_bot[0].message.text == "help me with my order"

    # Verify Scoped XYZ-bot received ONLY its event
    assert len(received_xyz_bot) == 1
    assert received_xyz_bot[0].config_key == "XYZ-bot"
    assert received_xyz_bot[0].message.text == "where is my invoice?"

    # Verify contextual auto-replies were dispatched exactly once per unique event
    assert len(reply_requests) == 2
    assert reply_requests[0] == {
        "recipient": "C123",
        "message": "Thanks! Looking into your order.",
        "config_key": "ABC-bot",
    }
    assert reply_requests[1] == {
        "recipient": "C789",
        "message": "Invoice sent to your email.",
        "config_key": "XYZ-bot",
    }

    await client.close()
