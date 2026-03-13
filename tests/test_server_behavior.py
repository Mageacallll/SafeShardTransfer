from common.types import BeginTransfer, ClientRequest, FreezeShard, TransferShard
from shardserver.server import ShardServer
from sim.harness import Harness
from sim.process import Process


class DummyClient(Process):
    def __init__(self, node_id: str):
        super().__init__(node_id)
        self.replies = []

    def on_message(self, src, message):
        self.replies.append((src, message))


def setup_server_only():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)
    server = ShardServer("A", coordinator_id="coord")
    coord = DummyClient("coord")
    client = DummyClient("client")
    peer = ShardServer("B", coordinator_id="coord")

    h.add_node(server)
    h.add_node(coord)
    h.add_node(client)
    h.add_node(peer)

    server.init_shard("s1", epoch=1, data={"x": 10})
    return h, server, coord, client, peer


def test_server_accepts_get_when_stable():
    h, server, coord, client, peer = setup_server_only()

    req = ClientRequest(shard_id="s1", epoch=1, key="x", value=None, op="GET")
    h.schedule(1, server.on_message, "client", req)
    h.run()

    assert len(client.replies) == 1
    _, reply = client.replies[0]
    assert reply.success is True
    assert reply.value == 10
    assert reply.error is None


def test_server_rejects_epoch_mismatch():
    h, server, coord, client, peer = setup_server_only()

    req = ClientRequest(shard_id="s1", epoch=999, key="x", value=None, op="GET")
    h.schedule(1, server.on_message, "client", req)
    h.run()

    _, reply = client.replies[0]
    assert reply.success is False
    assert reply.error == "stale_or_wrong_epoch"


def test_server_rejects_when_frozen():
    h, server, coord, client, peer = setup_server_only()

    h.schedule(1, server.on_message, "coord", FreezeShard(shard_id="s1", epoch=1))
    h.schedule(3, server.on_message, "client", ClientRequest(
        shard_id="s1", epoch=1, key="x", value=None, op="GET"
    ))
    h.run()

    _, reply = client.replies[-1]
    assert reply.success is False
    assert reply.error == "reconfiguring"


def test_server_sends_freeze_ack():
    h, server, coord, client, peer = setup_server_only()

    h.schedule(1, server.on_message, "coord", FreezeShard(shard_id="s1", epoch=1))
    h.run()

    assert len(coord.replies) == 1
    src, msg = coord.replies[0]
    assert src == "A"
    assert msg.__class__.__name__ == "FreezeAck"
    assert msg.shard_id == "s1"
    assert msg.epoch == 1


def test_begin_transfer_sends_transfer_shard():
    h, server, coord, client, peer = setup_server_only()

    h.schedule(1, server.on_message, "coord", FreezeShard(shard_id="s1", epoch=1))
    h.schedule(3, server.on_message, "coord", BeginTransfer(shard_id="s1", epoch=1, target="B"))
    h.run()

    assert "s1" in peer.pending_incoming
    assert peer.pending_incoming["s1"]["data"] == {"x": 10}


def test_activate_installs_pending_state():
    h, server, coord, client, peer = setup_server_only()

    h.schedule(1, peer.on_message, "A", TransferShard(shard_id="s1", epoch=1, data={"x": 10}))
    h.schedule(3, peer.on_message, "coord", __import__("common.types", fromlist=["ActivateShard"]).ActivateShard(
        shard_id="s1", epoch=2
    ))
    h.run()

    assert "s1" in peer.shards
    assert peer.shards["s1"]["epoch"] == 2
    assert peer.shards["s1"]["data"]["x"] == 10