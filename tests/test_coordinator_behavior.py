from common.types import FreezeAck, TransferAck
from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness
from sim.process import Process


class Inbox(Process):
    def __init__(self, node_id: str):
        super().__init__(node_id)
        self.messages = []

    def on_message(self, src, message):
        self.messages.append((src, message))


def setup_coordinator_only():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord")
    a = Inbox("A")
    b = Inbox("B")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)
    return h, coord, a, b


def test_reassign_sends_freeze_to_old_owner():
    h, coord, a, b = setup_coordinator_only()

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    assert len(a.messages) == 1
    src, msg = a.messages[0]
    assert src == "coord"
    assert msg.__class__.__name__ == "FreezeShard"
    assert msg.shard_id == "s1"
    assert msg.epoch == 1


def test_freeze_ack_moves_to_transfer_and_sends_begin_transfer():
    h, coord, a, b = setup_coordinator_only()

    coord.reassign("s1", "B")
    h.schedule(1, coord.on_message, "A", FreezeAck(shard_id="s1", epoch=1))
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "TRANSFER"

    assert len(a.messages) >= 2
    src, msg = a.messages[-1]
    assert src == "coord"
    assert msg.__class__.__name__ == "BeginTransfer"
    assert msg.target == "B"


def test_transfer_ack_commits_new_owner_and_bumps_epoch():
    h, coord, a, b = setup_coordinator_only()

    coord.reassign("s1", "B")
    coord.on_message("A", FreezeAck(shard_id="s1", epoch=1))
    h.schedule(1, coord.on_message, "B", TransferAck(shard_id="s1", epoch=1))
    h.run()

    meta = coord.store.get("s1")
    assert meta["owner"] == "B"
    assert meta["epoch"] == 2
    assert meta["state"].value == "STABLE"


def test_freeze_timeout_retries_freeze_message_once():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord", freeze_timeout=2, max_retries=1)
    a = Inbox("A")
    b = Inbox("B")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    # Initial FreezeShard + one retry FreezeShard (then abort on exhaustion)
    assert len(a.messages) == 3
    assert a.messages[0][1].__class__.__name__ == "FreezeShard"
    assert a.messages[1][1].__class__.__name__ == "FreezeShard"
    assert a.messages[2][1].__class__.__name__ == "AbortReconfiguration"

    events = [e["event"] for e in coord.event_log]
    assert "phase_timeout" in events
    assert "phase_retry_send" in events
    assert "reassign_abort" in events

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["epoch"] == 2


def test_freeze_timeout_canceled_after_ack():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord", freeze_timeout=5, max_retries=1)
    a = Inbox("A")
    b = Inbox("B")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(2, coord.on_message, "A", FreezeAck(shard_id="s1", epoch=1))
    h.run()

    # Timeout callback should be stale once ack is accepted and timer canceled.
    events = [e["event"] for e in coord.event_log]
    assert "phase_timer_started" in events
    assert "phase_timer_canceled" in events
    assert events.count("phase_timeout") == 0

    meta = coord.store.get("s1")
    assert meta["state"].value == "TRANSFER"


def test_freeze_timeout_exhausted_aborts_reconfiguration():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord", freeze_timeout=2, max_retries=0)
    a = Inbox("A")
    b = Inbox("B")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["owner"] == "A"
    assert meta["state"].value == "STABLE"
    assert meta["epoch"] == 2
    assert meta["target"] is None

    events = [e["event"] for e in coord.event_log]
    assert "phase_retry_exhausted" in events
    assert "reassign_abort" in events


def test_transfer_timeout_exhausted_aborts_reconfiguration():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord", transfer_timeout=2, max_retries=0)
    a = Inbox("A")
    b = Inbox("B")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(2, coord.on_message, "A", FreezeAck(shard_id="s1", epoch=1))
    h.run()

    meta = coord.store.get("s1")
    assert meta["owner"] == "A"
    assert meta["state"].value == "STABLE"
    assert meta["epoch"] == 2
    assert meta["target"] is None

    events = [e["event"] for e in coord.event_log]
    assert "phase_retry_exhausted" in events
    assert "reassign_abort" in events


def test_participant_crash_during_transfer_aborts_reconfiguration():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord")
    a = Inbox("A")
    b = Inbox("B")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(2, coord.on_message, "A", FreezeAck(shard_id="s1", epoch=1))
    h.schedule(3, h.crash_node, "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["owner"] == "A"
    assert meta["state"].value == "STABLE"
    assert meta["epoch"] == 2
    assert meta["target"] is None

    events = [e["event"] for e in coord.event_log]
    assert "participant_crash_detected" in events
    assert "reassign_abort" in events