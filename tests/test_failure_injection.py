from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness
from sim.network import LinkConfig
from tests.helpers import assert_at_most_one_stable_holder


def setup_basic_system(*, freeze_timeout=None, transfer_timeout=None, max_retries=0, seed=0):
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=seed)

    coord = Coordinator(
        "coord",
        freeze_timeout=freeze_timeout,
        transfer_timeout=transfer_timeout,
        max_retries=max_retries,
    )
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
    With transfer timeout/retry enabled:
    If TransferShard is dropped, reconfiguration should safely abort
    back to STABLE rather than remain stuck in TRANSFER.
    """
    h, coord, a, b = setup_basic_system(transfer_timeout=2, max_retries=1)

    def drop_transfer(src, dst, msg):
        return msg.__class__.__name__ == "TransferShard"

    h.add_drop_rule(drop_transfer)

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "A"
    assert meta["epoch"] == 2
    assert_at_most_one_stable_holder("s1", a, b)

    names = [e["event"] for e in coord.event_log] + [e["event"] for e in a.event_log] + [e["event"] for e in b.event_log]
    assert "transfer_in_received" not in names
    assert "transfer_ack_accepted" not in names
    assert "activate_complete" not in names
    assert "cleanup_complete" not in names
    assert "reassign_complete" not in names
    assert "phase_timeout" in names
    assert "reassign_abort" in names


def test_old_owner_crash_during_freeze():
    h, coord, a, b = setup_basic_system(freeze_timeout=2, transfer_timeout=2, max_retries=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(2, h.crash_node, "A")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "A"
    assert meta["epoch"] == 2
    assert_at_most_one_stable_holder("s1", a, b)

    names = [e["event"] for e in coord.event_log]
    assert "reassign_complete" not in names
    assert "reassign_abort" in names


def test_new_owner_crash_before_transfer_ack():
    h, coord, a, b = setup_basic_system(freeze_timeout=2, transfer_timeout=2, max_retries=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(5, h.crash_node, "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "A"
    assert meta["epoch"] == 2
    assert_at_most_one_stable_holder("s1", a, b)

    names = [e["event"] for e in coord.event_log]
    assert "reassign_complete" not in names
    assert "reassign_abort" in names


def test_false_suspicion_safe_reconfig():
    h, coord, a, b = setup_basic_system(freeze_timeout=2, transfer_timeout=2, max_retries=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "B"
    assert meta["epoch"] == 2
    assert_at_most_one_stable_holder("s1", a, b)

    names = [e["event"] for e in coord.event_log]
    assert "reassign_complete" in names


def test_cascading_drop_then_old_owner_crash():
    h, coord, a, b = setup_basic_system(transfer_timeout=2, max_retries=1)

    def drop_transfer(src, dst, msg):
        return msg.__class__.__name__ == "TransferShard"

    h.add_drop_rule(drop_transfer)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(4, h.crash_node, "A")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "A"
    assert meta["epoch"] == 2
    assert_at_most_one_stable_holder("s1", a, b)

    names = [e["event"] for e in coord.event_log]
    assert "reassign_complete" not in names
    assert "reassign_abort" in names


def test_partition_then_recover():
    h, coord, a, b = setup_basic_system(freeze_timeout=2, max_retries=3)

    h.set_link_config(
        LinkConfig(
            source="coord",
            dest="A",
            partition_enabled=True,
            partition_start_time=2,
            partition_end_time=8,
        )
    )
    h.set_link_config(
        LinkConfig(
            source="A",
            dest="coord",
            partition_enabled=True,
            partition_start_time=2,
            partition_end_time=8,
        )
    )

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "B"
    assert meta["epoch"] == 2
    assert_at_most_one_stable_holder("s1", a, b)

    names = [e["event"] for e in coord.event_log]
    assert "reassign_complete" in names


def test_reorder_and_duplicate_transfer_path():
    h, coord, a, b = setup_basic_system(freeze_timeout=2, transfer_timeout=2, max_retries=2)

    h.set_link_config(
        LinkConfig(
            source="A",
            dest="B",
            reorder_enabled=True,
            duplicate_rate=0.5,
        )
    )
    h.set_link_config(
        LinkConfig(
            source="B",
            dest="coord",
            reorder_enabled=True,
            duplicate_rate=0.5,
        )
    )

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "B"
    assert meta["epoch"] == 2
    assert_at_most_one_stable_holder("s1", a, b)