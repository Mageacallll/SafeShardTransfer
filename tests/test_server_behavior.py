from common.types import (
    ActivateShard,
    AbortReconfiguration,
    BeginTransfer,
    CleanupShard,
    ClientRequest,
    FreezeShard,
    ShardState,
    TransferShard,
)
from shardserver.server import ShardServer
from sim.harness import Harness


def setup_server_system():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    server = ShardServer("A", coordinator_id="coord")
    peer = ShardServer("B", coordinator_id="coord")

    h.add_node(server)
    h.add_node(peer)

    return h, server, peer


# --------------------------------------------------
# Client request behavior
# --------------------------------------------------

def test_get_request_success():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 42})

    server.on_message(
        "client1",
        ClientRequest(shard_id="s1", epoch=1, key="x", value=None, op="GET"),
    )

    assert server.event_log[-1]["event"] == "client_get_ok"


def test_put_request_success():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={})

    server.on_message(
        "client1",
        ClientRequest(shard_id="s1", epoch=1, key="x", value=99, op="PUT"),
    )

    assert server.shards["s1"]["data"]["x"] == 99
    assert server.event_log[-1]["event"] == "client_put_ok"


def test_reject_missing_shard():
    h, server, _ = setup_server_system()

    server.on_message(
        "client1",
        ClientRequest(shard_id="missing", epoch=1, key="x", value=None, op="GET"),
    )

    assert server.event_log[-1]["event"] == "client_reject_missing_shard"


def test_reject_epoch_mismatch():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=2, data={"x": 42})

    server.on_message(
        "client1",
        ClientRequest(shard_id="s1", epoch=1, key="x", value=None, op="GET"),
    )

    assert server.event_log[-1]["event"] == "client_reject_epoch_mismatch"


def test_reject_when_not_stable():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 42})
    server.shards["s1"]["state"] = ShardState.FREEZE

    server.on_message(
        "client1",
        ClientRequest(shard_id="s1", epoch=1, key="x", value=None, op="GET"),
    )

    assert server.event_log[-1]["event"] == "client_reject_reconfiguring"


def test_reject_unknown_operation():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={})

    server.on_message(
        "client1",
        ClientRequest(shard_id="s1", epoch=1, key="x", value=None, op="DELETE"),
    )

    assert server.event_log[-1]["event"] == "client_reject_unknown_op"


def test_duplicate_request_id_deduplicates_put():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 1})

    server.on_message(
        "client1",
        ClientRequest(
            shard_id="s1",
            epoch=1,
            key="x",
            value=99,
            op="PUT",
            request_id="req-1",
        ),
    )

    server.on_message(
        "client1",
        ClientRequest(
            shard_id="s1",
            epoch=1,
            key="x",
            value=123,
            op="PUT",
            request_id="req-1",
        ),
    )

    assert server.shards["s1"]["data"]["x"] == 99
    assert server.event_log[-1]["event"] == "client_request_dedup_hit"


def test_duplicate_request_id_deduplicates_errors():
    h, server, _ = setup_server_system()

    server.on_message(
        "client1",
        ClientRequest(
            shard_id="missing",
            epoch=1,
            key="x",
            value=None,
            op="GET",
            request_id="req-miss",
        ),
    )

    server.on_message(
        "client1",
        ClientRequest(
            shard_id="missing",
            epoch=1,
            key="x",
            value=None,
            op="GET",
            request_id="req-miss",
        ),
    )

    assert server.event_log[-1]["event"] == "client_request_dedup_hit"


# --------------------------------------------------
# Freeze behavior
# --------------------------------------------------

def test_freeze_shard_success():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 1})

    server.on_message("coord", FreezeShard(shard_id="s1", epoch=1))

    assert server.shards["s1"]["state"] == ShardState.FREEZE
    assert server.event_log[-1]["event"] == "freeze_enter"


def test_freeze_missing_shard():
    h, server, _ = setup_server_system()

    server.on_message("coord", FreezeShard(shard_id="s1", epoch=1))

    assert server.event_log[-1]["event"] == "freeze_missing_shard"


def test_freeze_epoch_mismatch():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=2, data={})

    server.on_message("coord", FreezeShard(shard_id="s1", epoch=1))

    assert server.shards["s1"]["state"] == ShardState.STABLE
    assert server.event_log[-1]["event"] == "freeze_epoch_mismatch"


def test_freeze_duplicate_resends_ack_without_state_regression():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 1})
    server.shards["s1"]["state"] = ShardState.FREEZE

    server.on_message("coord", FreezeShard(shard_id="s1", epoch=1))

    assert server.shards["s1"]["state"] == ShardState.FREEZE
    assert server.event_log[-1]["event"] == "freeze_duplicate"


def test_freeze_ignored_after_transfer():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 1})
    server.shards["s1"]["state"] = ShardState.TRANSFER

    server.on_message("coord", FreezeShard(shard_id="s1", epoch=1))

    assert server.shards["s1"]["state"] == ShardState.TRANSFER
    assert server.event_log[-1]["event"] == "freeze_ignored_after_transfer"


# --------------------------------------------------
# Transfer out behavior
# --------------------------------------------------

def test_begin_transfer_success():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 10})
    server.shards["s1"]["state"] = ShardState.FREEZE

    server.on_message("coord", BeginTransfer(shard_id="s1", epoch=1, target="B"))

    assert server.shards["s1"]["state"] == ShardState.TRANSFER
    assert server.event_log[-1]["event"] == "transfer_out_start"


def test_begin_transfer_missing_shard():
    h, server, _ = setup_server_system()

    server.on_message("coord", BeginTransfer(shard_id="s1", epoch=1, target="B"))

    assert server.event_log[-1]["event"] == "begin_transfer_missing_shard"


def test_begin_transfer_epoch_mismatch():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=2, data={"x": 10})
    server.shards["s1"]["state"] = ShardState.FREEZE

    server.on_message("coord", BeginTransfer(shard_id="s1", epoch=1, target="B"))

    assert server.event_log[-1]["event"] == "begin_transfer_epoch_mismatch"


def test_begin_transfer_wrong_state():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 10})
    server.shards["s1"]["state"] = ShardState.STABLE

    server.on_message("coord", BeginTransfer(shard_id="s1", epoch=1, target="B"))

    assert server.event_log[-1]["event"] == "begin_transfer_wrong_state"


def test_begin_transfer_duplicate_is_ignored():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 10})
    server.shards["s1"]["state"] = ShardState.TRANSFER

    server.on_message("coord", BeginTransfer(shard_id="s1", epoch=1, target="B"))

    assert server.shards["s1"]["state"] == ShardState.TRANSFER
    assert server.event_log[-1]["event"] == "begin_transfer_duplicate"


# --------------------------------------------------
# Transfer in behavior
# --------------------------------------------------

def test_receive_transfer_shard_creates_pending_state():
    h, _, peer = setup_server_system()

    peer.on_message("A", TransferShard(shard_id="s1", epoch=1, data={"x": 10}))

    assert "s1" in peer.pending_incoming
    assert peer.pending_incoming["s1"]["epoch"] == 1
    assert peer.pending_incoming["s1"]["data"] == {"x": 10}
    assert peer.pending_incoming["s1"]["source"] == "A"
    assert peer.event_log[-1]["event"] == "transfer_in_received"


def test_receive_transfer_shard_duplicate_is_idempotent():
    h, _, peer = setup_server_system()

    peer.on_message("A", TransferShard(shard_id="s1", epoch=1, data={"x": 10}))
    peer.on_message("A", TransferShard(shard_id="s1", epoch=1, data={"x": 10}))

    assert peer.pending_incoming["s1"]["epoch"] == 1
    assert peer.pending_incoming["s1"]["data"] == {"x": 10}
    assert peer.event_log[-1]["event"] == "transfer_in_duplicate"


def test_receive_transfer_shard_rejects_when_local_epoch_is_newer_or_equal():
    h, _, peer = setup_server_system()
    peer.init_shard("s1", epoch=2, data={"x": 99})

    peer.on_message("A", TransferShard(shard_id="s1", epoch=1, data={"x": 10}))

    assert "s1" not in peer.pending_incoming
    assert peer.shards["s1"]["data"] == {"x": 99}
    assert peer.event_log[-1]["event"] == "transfer_in_reject_local_newer_or_equal"


def test_receive_transfer_shard_rejects_when_pending_newer_exists():
    h, _, peer = setup_server_system()
    peer.pending_incoming["s1"] = {
        "epoch": 2,
        "data": {"x": 99},
        "source": "A",
    }

    peer.on_message("A", TransferShard(shard_id="s1", epoch=1, data={"x": 10}))

    assert peer.pending_incoming["s1"]["epoch"] == 2
    assert peer.event_log[-1]["event"] == "transfer_in_reject_pending_newer"


def test_receive_transfer_shard_rejects_same_epoch_conflict():
    h, _, peer = setup_server_system()
    peer.pending_incoming["s1"] = {
        "epoch": 1,
        "data": {"x": 99},
        "source": "A",
    }

    peer.on_message("C", TransferShard(shard_id="s1", epoch=1, data={"x": 10}))

    assert peer.pending_incoming["s1"]["data"] == {"x": 99}
    assert peer.event_log[-1]["event"] == "transfer_in_conflict_same_epoch"


# --------------------------------------------------
# Activate behavior
# --------------------------------------------------

def test_activate_success():
    h, _, peer = setup_server_system()
    peer.pending_incoming["s1"] = {
        "epoch": 1,
        "data": {"x": 10},
        "source": "A",
    }

    peer.on_message("coord", ActivateShard(shard_id="s1", epoch=2))

    assert "s1" in peer.shards
    assert peer.shards["s1"]["epoch"] == 2
    assert peer.shards["s1"]["state"] == ShardState.STABLE
    assert peer.shards["s1"]["data"] == {"x": 10}
    assert "s1" not in peer.pending_incoming
    assert peer.event_log[-1]["event"] == "activate_complete"


def test_activate_missing_pending_state():
    h, _, peer = setup_server_system()

    peer.on_message("coord", ActivateShard(shard_id="s1", epoch=2))

    assert peer.event_log[-1]["event"] == "activate_missing_pending_state"


def test_activate_bad_epoch():
    h, _, peer = setup_server_system()
    peer.pending_incoming["s1"] = {
        "epoch": 2,
        "data": {"x": 10},
        "source": "A",
    }

    peer.on_message("coord", ActivateShard(shard_id="s1", epoch=2))

    assert "s1" not in peer.shards
    assert "s1" in peer.pending_incoming
    assert peer.event_log[-1]["event"] == "activate_bad_epoch"


# --------------------------------------------------
# Cleanup behavior
# --------------------------------------------------

def test_cleanup_success():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 10})

    server.on_message("coord", CleanupShard(shard_id="s1", epoch=2))

    assert "s1" not in server.shards
    assert server.event_log[-1]["event"] == "cleanup_complete"


def test_cleanup_missing_shard():
    h, server, _ = setup_server_system()

    server.on_message("coord", CleanupShard(shard_id="s1", epoch=2))

    assert server.event_log[-1]["event"] == "cleanup_missing_shard"


def test_cleanup_stale_epoch_is_ignored():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=2, data={"x": 10})

    server.on_message("coord", CleanupShard(shard_id="s1", epoch=2))

    assert "s1" in server.shards
    assert server.event_log[-1]["event"] == "cleanup_stale_epoch"


# --------------------------------------------------
# Abort behavior
# --------------------------------------------------

def test_abort_rolls_back_local_shard_to_stable():
    h, server, _ = setup_server_system()
    server.init_shard("s1", epoch=1, data={"x": 10})
    server.shards["s1"]["state"] = ShardState.TRANSFER

    server.on_message(
        "coord",
        AbortReconfiguration(shard_id="s1", epoch=2, reason="timeout_exhausted_transfer"),
    )

    assert server.shards["s1"]["state"] == ShardState.STABLE
    assert server.shards["s1"]["epoch"] == 2
    assert server.event_log[-1]["event"] == "abort_local_rollback"


def test_abort_clears_pending_incoming_state():
    h, _, peer = setup_server_system()
    peer.pending_incoming["s1"] = {
        "epoch": 1,
        "data": {"x": 10},
        "source": "A",
    }

    peer.on_message(
        "coord",
        AbortReconfiguration(shard_id="s1", epoch=2, reason="timeout_exhausted_transfer"),
    )

    assert "s1" not in peer.pending_incoming
    assert peer.event_log[-1]["event"] == "abort_pending_cleared"


# --------------------------------------------------
# End-to-end local flow
# --------------------------------------------------

def test_end_to_end_server_side_flow():
    h, server, peer = setup_server_system()
    server.init_shard("s1", epoch=1, data={"k": "v"})

    server.on_message("coord", FreezeShard(shard_id="s1", epoch=1))
    assert server.shards["s1"]["state"] == ShardState.FREEZE

    server.on_message("coord", BeginTransfer(shard_id="s1", epoch=1, target="B"))
    assert server.shards["s1"]["state"] == ShardState.TRANSFER

    peer.on_message("A", TransferShard(shard_id="s1", epoch=1, data={"k": "v"}))
    assert peer.pending_incoming["s1"]["data"] == {"k": "v"}

    peer.on_message("coord", ActivateShard(shard_id="s1", epoch=2))
    assert peer.shards["s1"]["epoch"] == 2
    assert peer.shards["s1"]["state"] == ShardState.STABLE
    assert peer.shards["s1"]["data"] == {"k": "v"}

    server.on_message("coord", CleanupShard(shard_id="s1", epoch=2))
    assert "s1" not in server.shards