from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness
from sim.network import LinkConfig
from common.types import ClientRequest


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


def test_unique_active_owner_after_reconfig():
    h, coord, a, b = setup_basic_system()

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    holders = []
    if "s1" in a.shards and a.shards["s1"]["state"].value == "STABLE":
        holders.append("A")
    if "s1" in b.shards and b.shards["s1"]["state"].value == "STABLE":
        holders.append("B")

    assert holders == ["B"]


def test_epoch_monotonic_after_reconfig():
    h, coord, a, b = setup_basic_system()

    before = coord.store.get("s1")["epoch"]
    h.schedule(1, coord.reassign, "s1", "B")
    h.run()
    after = coord.store.get("s1")["epoch"]

    assert after >= before
    assert after == before + 1


def test_old_owner_cleaned_up_after_reconfig():
    h, coord, a, b = setup_basic_system()

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    assert "s1" not in a.shards
    assert "s1" in b.shards
    

def test_no_client_success_during_freeze():
    h, coord, a, b = setup_basic_system()

    class DummyClient:
        def __init__(self):
            self.messages = []

        def on_message(self, src, message):
            self.messages.append((src, message))

    # Better to use a real Process subclass if needed in your setup

    from sim.process import Process

    class ClientInbox(Process):
        def __init__(self, node_id):
            super().__init__(node_id)
            self.messages = []

        def on_message(self, src, message):
            self.messages.append((src, message))

    client = ClientInbox("client")
    h.add_node(client)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(
        3,
        a.on_message,
        "client",
        ClientRequest(shard_id="s1", epoch=1, key="k", value=None, op="GET"),
    )
    h.run()

    assert len(client.messages) >= 1
    _, reply = client.messages[-1]
    assert reply.success is False
    assert reply.error == "reconfiguring"


def test_no_dual_owner_under_reorder_and_duplicates():
    h, coord, a, b = setup_basic_system()

    h.set_link_config(
        LinkConfig(
            source="A",
            dest="B",
            reorder_enabled=True,
            duplicate_rate=0.8,
            delay_min_ms=1,
            delay_max_ms=5,
        )
    )
    h.set_link_config(
        LinkConfig(
            source="B",
            dest="coord",
            reorder_enabled=True,
            duplicate_rate=0.8,
            delay_min_ms=1,
            delay_max_ms=5,
        )
    )

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    holders = []
    if "s1" in a.shards and a.shards["s1"]["state"].value == "STABLE":
        holders.append("A")
    if "s1" in b.shards and b.shards["s1"]["state"].value == "STABLE":
        holders.append("B")

    assert len(holders) <= 1


def test_abort_after_participant_crash_preserves_single_owner():
    h, coord, a, b = setup_basic_system()

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(2, h.crash_node, "A")
    h.schedule(4, h.recover_node, "A")
    h.run()

    holders = []
    if "s1" in a.shards and a.shards["s1"]["state"].value == "STABLE":
        holders.append("A")
    if "s1" in b.shards and b.shards["s1"]["state"].value == "STABLE":
        holders.append("B")

    assert len(holders) <= 1
    assert coord.store.get("s1")["state"].value == "STABLE"