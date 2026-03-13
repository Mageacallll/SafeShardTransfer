"""
Shard server for the freeze-based shard reassignment MVP.

Responsibilities:
- serve client requests only when authorized
- reject requests with stale epochs
- reject requests while shard is frozen / transferring
- transfer shard state to the target server
- activate received shard state on new ownership
- cleanup old shard state after cutover
"""

from common.types import (
    ActivateShard,
    BeginTransfer,
    CleanupShard,
    ClientReply,
    ClientRequest,
    FreezeAck,
    FreezeShard,
    ShardState,
    TransferAck,
    TransferShard,
)
from sim.process import Process


class ShardServer(Process):
    def __init__(self, node_id: str, coordinator_id: str = "coord"):
        super().__init__(node_id)

        self.coordinator_id = coordinator_id

        # shard_id -> local active shard record
        self.shards = {}

        # shard_id -> temporarily received state waiting for activation
        self.pending_incoming = {}
        
        self.event_log = []

    # --------------------------------------------------
    # Local shard management
    # --------------------------------------------------

    def init_shard(self, shard_id: str, epoch: int = 1, data=None):
        """
        Initialize a shard locally on this server as active and stable.
        Only used by harness/bootstrap code.
        """
        self.shards[shard_id] = {
            "epoch": epoch,
            "state": ShardState.STABLE,
            "data": dict(data or {}),
        }

    def has_shard(self, shard_id: str) -> bool:
        return shard_id in self.shards

    def get_shard(self, shard_id: str):
        return self.shards.get(shard_id)

    # --------------------------------------------------
    # Message handling
    # --------------------------------------------------

    def on_message(self, src: str, message):
        if isinstance(message, ClientRequest):
            self._handle_client_request(src, message)

        elif isinstance(message, FreezeShard):
            self._handle_freeze_shard(src, message)

        elif isinstance(message, BeginTransfer):
            self._handle_begin_transfer(src, message)

        elif isinstance(message, TransferShard):
            self._handle_transfer_shard(src, message)

        elif isinstance(message, ActivateShard):
            self._handle_activate_shard(src, message)

        elif isinstance(message, CleanupShard):
            self._handle_cleanup_shard(src, message)

        else:
            self.log_event(
                event="unknown_message",
                src=src,
                message_type=message.__class__.__name__,
            )

    # --------------------------------------------------
    # Client request handling
    # --------------------------------------------------

    def _handle_client_request(self, src: str, message: ClientRequest):
        shard = self.shards.get(message.shard_id)

        if shard is None:
            self._reply_client(
                src,
                success=False,
                value=None,
                error="wrong_owner_or_missing_shard",
            )
            self.log_event(
                event="client_reject_missing_shard",
                client=src,
                shard_id=message.shard_id,
            )
            return

        local_epoch = shard["epoch"]
        local_state = shard["state"]

        if message.epoch != local_epoch:
            self._reply_client(
                src,
                success=False,
                value=None,
                error="stale_or_wrong_epoch",
            )
            self.log_event(
                event="client_reject_epoch_mismatch",
                client=src,
                shard_id=message.shard_id,
                request_epoch=message.epoch,
                local_epoch=local_epoch,
            )
            return

        if local_state != ShardState.STABLE:
            self._reply_client(
                src,
                success=False,
                value=None,
                error="reconfiguring",
            )
            self.log_event(
                event="client_reject_reconfiguring",
                client=src,
                shard_id=message.shard_id,
                state=local_state.value,
            )
            return

        if message.op == "GET":
            value = shard["data"].get(message.key)
            self._reply_client(src, success=True, value=value, error=None)
            self.log_event(
                event="client_get_ok",
                client=src,
                shard_id=message.shard_id,
                key=message.key,
                value=value,
            )

        elif message.op == "PUT":
            shard["data"][message.key] = message.value
            self._reply_client(src, success=True, value=None, error=None)
            self.log_event(
                event="client_put_ok",
                client=src,
                shard_id=message.shard_id,
                key=message.key,
            )

        else:
            self._reply_client(
                src,
                success=False,
                value=None,
                error="unknown_operation",
            )
            self.log_event(
                event="client_reject_unknown_op",
                client=src,
                shard_id=message.shard_id,
                op=message.op,
            )

    # --------------------------------------------------
    # Reconfiguration handlers
    # --------------------------------------------------

    def _handle_freeze_shard(self, src: str, message: FreezeShard):
        shard = self.shards.get(message.shard_id)

        if shard is None:
            self.log_event(
                event="freeze_missing_shard",
                coordinator=src,
                shard_id=message.shard_id,
            )
            return

        if shard["epoch"] != message.epoch:
            self.log_event(
                event="freeze_epoch_mismatch",
                coordinator=src,
                shard_id=message.shard_id,
                msg_epoch=message.epoch,
                local_epoch=shard["epoch"],
            )
            return

        shard["state"] = ShardState.FREEZE

        self.log_event(
            event="freeze_enter",
            coordinator=src,
            shard_id=message.shard_id,
            epoch=message.epoch,
            state=ShardState.FREEZE.value,
        )

        self.send(src, FreezeAck(shard_id=message.shard_id, epoch=message.epoch))

    def _handle_begin_transfer(self, src: str, message: BeginTransfer):
        shard = self.shards.get(message.shard_id)

        if shard is None:
            self.log_event(
                event="begin_transfer_missing_shard",
                coordinator=src,
                shard_id=message.shard_id,
            )
            return

        if shard["epoch"] != message.epoch:
            self.log_event(
                event="begin_transfer_epoch_mismatch",
                coordinator=src,
                shard_id=message.shard_id,
                msg_epoch=message.epoch,
                local_epoch=shard["epoch"],
            )
            return

        if shard["state"] != ShardState.FREEZE:
            self.log_event(
                event="begin_transfer_wrong_state",
                coordinator=src,
                shard_id=message.shard_id,
                state=shard["state"].value,
            )
            return

        self.transfer_out(message.shard_id, message.target)

    def transfer_out(self, shard_id: str, target: str):
        shard = self.shards.get(shard_id)

        if shard is None:
            self.log_event(
                event="transfer_out_missing_shard",
                shard_id=shard_id,
                target=target,
            )
            return

        if shard["state"] != ShardState.FREEZE:
            self.log_event(
                event="transfer_out_wrong_state",
                shard_id=shard_id,
                target=target,
                state=shard["state"].value,
            )
            return

        shard["state"] = ShardState.TRANSFER

        self.log_event(
            event="transfer_out_start",
            shard_id=shard_id,
            target=target,
            epoch=shard["epoch"],
            state=ShardState.TRANSFER.value,
        )

        self.send(
            target,
            TransferShard(
                shard_id=shard_id,
                epoch=shard["epoch"],
                data=dict(shard["data"]),
            ),
        )

    def _handle_transfer_shard(self, src: str, message: TransferShard):
        self.pending_incoming[message.shard_id] = {
            "epoch": message.epoch,
            "data": dict(message.data),
            "source": src,
        }

        self.log_event(
            event="transfer_in_received",
            source=src,
            shard_id=message.shard_id,
            epoch=message.epoch,
        )

        self.send(
            self.coordinator_id,
            TransferAck(shard_id=message.shard_id, epoch=message.epoch),
        )

    def _handle_activate_shard(self, src: str, message: ActivateShard):
        pending = self.pending_incoming.get(message.shard_id)

        if pending is None:
            self.log_event(
                event="activate_missing_pending_state",
                coordinator=src,
                shard_id=message.shard_id,
                new_epoch=message.epoch,
            )
            return

        old_epoch = pending["epoch"]
        new_epoch = message.epoch

        if new_epoch <= old_epoch:
            self.log_event(
                event="activate_bad_epoch",
                coordinator=src,
                shard_id=message.shard_id,
                old_epoch=old_epoch,
                new_epoch=new_epoch,
            )
            return

        self.shards[message.shard_id] = {
            "epoch": new_epoch,
            "state": ShardState.STABLE,
            "data": dict(pending["data"]),
        }

        del self.pending_incoming[message.shard_id]

        self.log_event(
            event="activate_complete",
            coordinator=src,
            shard_id=message.shard_id,
            old_epoch=old_epoch,
            new_epoch=new_epoch,
            state=ShardState.STABLE.value,
        )

    def _handle_cleanup_shard(self, src: str, message: CleanupShard):
        shard = self.shards.get(message.shard_id)

        if shard is None:
            self.log_event(
                event="cleanup_missing_shard",
                coordinator=src,
                shard_id=message.shard_id,
            )
            return

        del self.shards[message.shard_id]

        self.log_event(
            event="cleanup_complete",
            coordinator=src,
            shard_id=message.shard_id,
            cleanup_epoch=message.epoch,
        )

    # --------------------------------------------------
    # Client reply helper
    # --------------------------------------------------

    def _reply_client(self, client_id: str, success: bool, value, error):
        self.send(
            client_id,
            ClientReply(
                success=success,
                value=value,
                error=error,
            ),
        )

    # --------------------------------------------------
    # Logging helper
    # --------------------------------------------------

    def log_event(self, **fields):
        timestamp = self.network.loop.time if self.network and self.network.loop else "?"
        record = {
            "time": timestamp,
            "node": self.node_id,
            **fields,
        }
        self.event_log.append(record)
        print(f"[t={timestamp}] server={self.node_id} {fields}")