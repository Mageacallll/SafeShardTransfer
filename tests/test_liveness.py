from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness
from sim.network import LinkConfig
from tests.helpers import assert_at_most_one_stable_holder


def setup_system(*, freeze_timeout=None, transfer_timeout=None, max_retries=0, seed=0):
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


def test_liveness_happy_path_completes_within_bound():
    h, coord, a, b = setup_system()

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "B"
    assert meta["epoch"] == 2
    assert meta["attempt_id"] is None
    assert h.loop.time <= 15
    assert_at_most_one_stable_holder("s1", a, b)


def test_liveness_drop_transfer_eventually_aborts_stable():
    h, coord, a, b = setup_system(transfer_timeout=2, max_retries=1)

    def drop_transfer(src, dst, msg):
        return msg.__class__.__name__ == "TransferShard"

    h.add_drop_rule(drop_transfer)
    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "A"
    assert meta["attempt_id"] is None
    assert h.loop.time <= 25
    assert_at_most_one_stable_holder("s1", a, b)


def test_liveness_old_owner_crash_eventually_stable():
    h, coord, a, b = setup_system(freeze_timeout=2, max_retries=1)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(2, h.crash_node, "A")
    h.schedule(5, h.recover_node, "A")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "A"
    assert meta["epoch"] == 2
    assert meta["attempt_id"] is None
    assert h.loop.time <= 25
    assert_at_most_one_stable_holder("s1", a, b)


def test_liveness_partition_heals_and_reassign_completes():
    h, coord, a, b = setup_system(freeze_timeout=2, max_retries=3)

    h.set_link_config(
        LinkConfig(
            source="coord",
            dest="A",
            partition_enabled=True,
            partition_start_time=1,
            partition_end_time=6,
        )
    )
    h.set_link_config(
        LinkConfig(
            source="A",
            dest="coord",
            partition_enabled=True,
            partition_start_time=1,
            partition_end_time=6,
        )
    )

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["state"].value == "STABLE"
    assert meta["owner"] == "B"
    assert meta["epoch"] == 2
    assert meta["attempt_id"] is None
    assert h.loop.time <= 35
    assert_at_most_one_stable_holder("s1", a, b)