from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness
from tests.helpers import (
    assert_at_most_one_stable_holder,
    event_names,
    merged_events,
    has_event,
)


def setup_basic_system():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord")
    a = ShardServer("A", coordinator_id="coord")
    b = ShardServer("B", coordinator_id="coord")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)
    a.init_shard("s1", epoch=1, data={"k": "v"})

    return h, coord, a, b


def test_drop_transfer_shard_message():
    """
    Safety-only scenario:
    If TransferShard is dropped, the new owner must not activate and
    the coordinator must not complete reconfiguration.
    """

    h, coord, a, b = setup_basic_system()

    def drop_transfer(src, dst, msg):
        return msg.__class__.__name__ == "TransferShard"

    h.add_drop_rule(drop_transfer)

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")

    assert meta["state"].value == "TRANSFER"
    assert meta["owner"] == "A"
    assert meta["epoch"] == 1

    assert_at_most_one_stable_holder("s1", a, b)

    events = merged_events(coord, a, b)
    names = event_names(events)

    assert "reassign_start" in names
    assert "freeze_enter" in names
    assert "freeze_ack_accepted" in names
    assert "transfer_out_start" in names

    assert "transfer_in_received" not in names
    assert "transfer_ack_accepted" not in names
    assert "activate_complete" not in names
    assert "cleanup_complete" not in names
    assert "reassign_complete" not in names


def test_old_owner_crash_during_freeze():
    """
    Safety-only scenario:
    If the old owner crashes during FREEZE, reconfiguration should not
    complete incorrectly and dual ownership must not occur.
    """

    h, coord, a, b = setup_basic_system()

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(2, h.crash_node, "A")
    h.run()

    meta = coord.store.get("s1")

    assert meta["owner"] == "A"
    assert meta["epoch"] == 1
    assert meta["state"].value == "FREEZE"

    assert_at_most_one_stable_holder("s1", a, b)

    events = merged_events(coord, a, b)
    names = event_names(events)

    assert "reassign_start" in names
    assert "freeze_enter" not in names
    assert "freeze_ack_accepted" not in names
    assert "transfer_ack_accepted" not in names
    assert "reassign_complete" not in names


def test_new_owner_crash_before_transfer_ack():
    """
    Safety-only scenario:
    If the new owner crashes before sending TransferAck, reconfiguration
    must not complete and the system must avoid dual ownership.
    """

    h, coord, a, b = setup_basic_system()

    h.schedule(1, coord.reassign, "s1", "B")
    # With deterministic 1-step delivery:
    # t=2 freeze at A
    # t=3 freeze ack at coord
    # t=4 begin transfer at A
    # t=5 TransferShard would be delivered to B
    # So crashing B at t=5 should prevent receipt/ack.
    h.schedule(5, h.crash_node, "B")
    h.run()

    meta = coord.store.get("s1")

    assert meta["owner"] == "A"
    assert meta["epoch"] == 1
    assert meta["state"].value == "TRANSFER"

    assert_at_most_one_stable_holder("s1", a, b)

    events = merged_events(coord, a, b)
    names = event_names(events)

    assert "reassign_start" in names
    assert "freeze_enter" in names
    assert "freeze_ack_accepted" in names
    assert "transfer_out_start" in names

    assert "transfer_in_received" not in names
    assert "transfer_ack_accepted" not in names
    assert "activate_complete" not in names
    assert "cleanup_complete" not in names
    assert "reassign_complete" not in names


def test_false_suspicion_triggers_safe_but_unnecessary_reconfig():
    """
    A healthy old owner is unnecessarily suspected and reconfiguration is
    triggered anyway. The protocol should still complete safely.
    """

    h, coord, a, b = setup_basic_system()

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")

    assert meta["owner"] == "B"
    assert meta["epoch"] == 2
    assert meta["state"].value == "STABLE"

    assert_at_most_one_stable_holder("s1", a, b)

    events = merged_events(coord, a, b)
    names = event_names(events)

    assert "reassign_start" in names
    assert "freeze_enter" in names
    assert "freeze_ack_accepted" in names
    assert "transfer_out_start" in names
    assert "transfer_in_received" in names
    assert "transfer_ack_accepted" in names
    assert "activate_complete" in names
    assert "cleanup_complete" in names
    assert "reassign_complete" in names

    assert has_event(coord, "reassign_complete")