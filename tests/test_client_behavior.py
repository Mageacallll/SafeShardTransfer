from client.client import Client
from common.types import ClientReply
from shardserver.server import ShardServer
from sim.harness import Harness


def setup_client_server_system():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    client = Client("client1", default_server_id="A", max_retries=2, retry_delay=1)
    server_a = ShardServer("A", coordinator_id="coord")
    server_b = ShardServer("B", coordinator_id="coord")

    h.add_node(client)
    h.add_node(server_a)
    h.add_node(server_b)

    return h, client, server_a, server_b


# --------------------------------------------------
# Basic request behavior
# --------------------------------------------------

def test_client_get_success():
    h, client, server_a, _ = setup_client_server_system()
    server_a.init_shard("s1", epoch=1, data={"x": 42})
    client.set_shard_owner("s1", "A")

    client.get("s1", epoch=1, key="x")
    h.run()

    assert client.pending_request is None
    assert len(client.replies) == 1

    src, reply = client.replies[0]
    assert src == "A"
    assert reply.success is True
    assert reply.value == 42
    assert reply.error is None

    events = [e["event"] for e in client.event_log]
    assert "request_start" in events
    assert "request_sent" in events
    assert "request_success" in events


def test_client_put_success():
    h, client, server_a, _ = setup_client_server_system()
    server_a.init_shard("s1", epoch=1, data={})
    client.set_shard_owner("s1", "A")

    client.put("s1", epoch=1, key="x", value=99)
    h.run()

    assert client.pending_request is None
    assert server_a.shards["s1"]["data"]["x"] == 99
    assert len(client.replies) == 1

    src, reply = client.replies[0]
    assert src == "A"
    assert reply.success is True
    assert reply.error is None


def test_client_request_fails_without_route():
    h, client, _, _ = setup_client_server_system()
    client.default_server_id = None

    ok = client.get("s1", epoch=1, key="x")

    assert ok is False
    assert client.pending_request is None
    assert client.event_log[-1]["event"] == "request_failed_no_route"


# --------------------------------------------------
# Single in-flight safety
# --------------------------------------------------

def test_client_rejects_second_inflight_request():
    h, client, server_a, _ = setup_client_server_system()
    server_a.init_shard("s1", epoch=1, data={"x": 1})
    client.set_shard_owner("s1", "A")

    client.get("s1", epoch=1, key="x")

    try:
        client.get("s1", epoch=1, key="x")
        assert False, "Expected RuntimeError for second in-flight request"
    except RuntimeError as e:
        assert "one in-flight request" in str(e)


# --------------------------------------------------
# Reply handling edge cases
# --------------------------------------------------

def test_client_ignores_orphan_reply():
    h, client, _, _ = setup_client_server_system()

    client.on_message("A", ClientReply(success=True, value=123, error=None))

    assert client.pending_request is None
    assert len(client.replies) == 1
    assert client.event_log[-1]["event"] == "orphan_reply"


def test_client_ignores_reply_from_wrong_source():
    h, client, server_a, _ = setup_client_server_system()
    server_a.init_shard("s1", epoch=1, data={"x": 7})
    client.set_shard_owner("s1", "A")

    client.get("s1", epoch=1, key="x")

    # Fake a reply from B while request expects A
    client.on_message("B", ClientReply(success=True, value=7, error=None))

    assert client.pending_request is not None
    assert client.event_log[-1]["event"] == "reply_wrong_source"


# --------------------------------------------------
# Retry behavior
# --------------------------------------------------

def test_client_retries_on_reconfiguring():
    h, client, server_a, _ = setup_client_server_system()
    server_a.init_shard("s1", epoch=1, data={"x": 1})
    server_a.shards["s1"]["state"] = server_a.shards["s1"]["state"].FREEZE
    client.set_shard_owner("s1", "A")

    client.get("s1", epoch=1, key="x")
    h.run()

    events = [e["event"] for e in client.event_log]
    assert "request_error" in events
    assert "request_retry_scheduled" in events
    assert "request_failed" in events
    assert client.pending_request is None


def test_client_retries_on_missing_shard():
    h, client, server_a, _ = setup_client_server_system()
    # no shard initialized on A
    client.set_shard_owner("s1", "A")

    client.get("s1", epoch=1, key="x")
    h.run()

    events = [e["event"] for e in client.event_log]
    assert "request_error" in events
    assert "request_retry_scheduled" in events
    assert "request_failed" in events
    assert client.pending_request is None


def test_client_retries_on_epoch_mismatch():
    h, client, server_a, _ = setup_client_server_system()
    server_a.init_shard("s1", epoch=2, data={"x": 8})
    client.set_shard_owner("s1", "A")

    client.get("s1", epoch=1, key="x")
    h.run()

    events = [e["event"] for e in client.event_log]
    assert "request_error" in events
    assert "request_retry_scheduled" in events
    assert "request_failed" in events
    assert client.pending_request is None


def test_client_stops_after_max_retries():
    h, client, server_a, _ = setup_client_server_system()
    client.max_retries = 1
    client.set_shard_owner("s1", "A")
    # no shard on A -> retryable error every time

    client.get("s1", epoch=1, key="x")
    h.run()

    retry_events = [e for e in client.event_log if e["event"] == "request_retry_scheduled"]
    failed_events = [e for e in client.event_log if e["event"] == "request_failed"]

    assert len(retry_events) == 1
    assert len(failed_events) == 1
    assert client.pending_request is None


# --------------------------------------------------
# Route invalidation behavior
# --------------------------------------------------

def test_client_invalidates_route_on_retryable_error():
    h, client, _, _ = setup_client_server_system()
    client.set_shard_owner("s1", "A")

    client.get("s1", epoch=1, key="x")
    h.run()

    # After retryable wrong_owner_or_missing_shard, route should be invalidated
    assert "s1" not in client.routing_table

    events = [e["event"] for e in client.event_log]
    assert "route_invalidated" in events


# --------------------------------------------------
# Unknown message handling
# --------------------------------------------------

def test_client_logs_unknown_message():
    h, client, _, _ = setup_client_server_system()

    class DummyMessage:
        pass

    client.on_message("A", DummyMessage())

    assert client.event_log[-1]["event"] == "unknown_message"