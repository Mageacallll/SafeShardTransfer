from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness
from tests.helpers import merged_events, event_names


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


def test_reassign_happy_path():
    h, coord, a, b = setup_basic_system()

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    meta = coord.store.get("s1")
    assert meta["owner"] == "B"
    assert meta["epoch"] == 2
    assert meta["state"].value == "STABLE"

    assert "s1" not in a.shards
    assert "s1" in b.shards
    assert b.shards["s1"]["epoch"] == 2
    assert b.shards["s1"]["data"] == {"k": "v"}


def test_reassign_to_same_owner_raises():
    h, coord, a, b = setup_basic_system()

    try:
        coord.reassign("s1", "A")
        assert False, "Expected ValueError when reassigning to same owner"
    except ValueError:
        pass


def test_reassign_when_not_stable_raises():
    h, coord, a, b = setup_basic_system()

    coord.store.update("s1", state=coord.store.get("s1")["state"].FREEZE)

    try:
        coord.reassign("s1", "B")
        assert False, "Expected ValueError when shard is not STABLE"
    except ValueError:
        pass


def test_reassign_event_order():
    h, coord, a, b = setup_basic_system()

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

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

    assert names.index("reassign_start") < names.index("freeze_enter")
    assert names.index("freeze_enter") < names.index("freeze_ack_accepted")
    assert names.index("freeze_ack_accepted") < names.index("transfer_out_start")
    assert names.index("transfer_out_start") < names.index("transfer_in_received")
    assert names.index("transfer_in_received") < names.index("transfer_ack_accepted")
    assert names.index("transfer_ack_accepted") < names.index("reassign_complete")