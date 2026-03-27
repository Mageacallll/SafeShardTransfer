"""
Metadata coordinator for shard reconfiguration.

The coordinator owns the shard metadata state machine and drives
reassignment of shard ownership through the protocol:

STABLE -> FREEZE -> TRANSFER -> ACTIVATE -> CLEANUP -> STABLE
"""

from common.types import (
    ActivateShard,
    BeginTransfer,
    CleanupShard,
    FreezeAck,
    FreezeShard,
    ShardState,
    StartReconfiguration,
    TransferAck,
)
from metadata.store import MetadataStore
from sim.process import Process


class Coordinator(Process):
    def __init__(
        self,
        node_id: str,
        freeze_timeout: int | None = None,
        transfer_timeout: int | None = None,
        max_retries: int = 0,
        retry_backoff: int = 2,
    ):
        super().__init__(node_id)
        self.store = MetadataStore()
        self.event_log = []
        self._event_seq = 0

        self.freeze_timeout = freeze_timeout
        self.transfer_timeout = transfer_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

        # timeout tokens prevent stale callbacks from mutating state
        self._phase_tokens: dict[tuple[str, str], int] = {}
        self._phase_retry_counts: dict[tuple[str, str], int] = {}

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def init_shard(self, shard_id: str, owner: str, epoch: int = 1):
        """
        Initialize a shard in STABLE state.
        """
        self.store.init_shard(shard_id=shard_id, owner=owner, epoch=epoch)

    def reassign(self, shard_id: str, new_owner: str):
        """
        Begin reassignment of a shard to a new owner.
        """
        shard = self.store.get(shard_id)

        if shard["state"] != ShardState.STABLE:
            raise ValueError(
                f"Cannot reassign shard {shard_id}: state is {shard['state'].value}, not STABLE."
            )

        old_owner = shard["owner"]
        current_epoch = shard["epoch"]

        if old_owner == new_owner:
            raise ValueError(f"Shard {shard_id} is already owned by {new_owner}.")

        self.store.update(
            shard_id,
            state=ShardState.FREEZE,
            target=new_owner,
        )

        self.log_event(
            event="reassign_start",
            shard_id=shard_id,
            old_owner=old_owner,
            new_owner=new_owner,
            epoch=current_epoch,
            state=ShardState.FREEZE.value,
        )

        self.send(old_owner, FreezeShard(shard_id=shard_id, epoch=current_epoch))

        self._start_phase_timer(shard_id, ShardState.FREEZE)

    # --------------------------------------------------
    # Message handling
    # --------------------------------------------------

    def on_message(self, src: str, message):
        if isinstance(message, FreezeAck):
            self._handle_freeze_ack(src, message)

        elif isinstance(message, TransferAck):
            self._handle_transfer_ack(src, message)

        elif isinstance(message, StartReconfiguration):
            self.reassign(message.shard_id, message.new_owner)

        else:
            self.log_event(
                event="unknown_message",
                src=src,
                message_type=message.__class__.__name__,
            )

    # --------------------------------------------------
    # Protocol handlers
    # --------------------------------------------------

    def _handle_freeze_ack(self, src: str, message: FreezeAck):
        shard_id = message.shard_id
        shard = self.store.get(shard_id)

        if shard["state"] != ShardState.FREEZE:
            self.log_event(
                event="unexpected_freeze_ack",
                shard_id=shard_id,
                src=src,
                state=shard["state"].value,
            )
            return

        if src != shard["owner"]:
            self.log_event(
                event="freeze_ack_wrong_owner",
                shard_id=shard_id,
                src=src,
                expected_owner=shard["owner"],
            )
            return

        if message.epoch != shard["epoch"]:
            self.log_event(
                event="freeze_ack_stale_epoch",
                shard_id=shard_id,
                src=src,
                msg_epoch=message.epoch,
                current_epoch=shard["epoch"],
            )
            return

        self._cancel_phase_timer(shard_id, ShardState.FREEZE)

        self.store.update(shard_id, state=ShardState.TRANSFER)

        self.log_event(
            event="freeze_ack_accepted",
            shard_id=shard_id,
            old_owner=shard["owner"],
            new_owner=shard["target"],
            epoch=shard["epoch"],
            state=ShardState.TRANSFER.value,
        )

        self.send(
            shard["owner"],
            BeginTransfer(
                shard_id=shard_id,
                epoch=shard["epoch"],
                target=shard["target"],
            ),
        )

        self._start_phase_timer(shard_id, ShardState.TRANSFER)

    def _handle_transfer_ack(self, src: str, message: TransferAck):
        shard_id = message.shard_id
        shard = self.store.get(shard_id)

        if shard["state"] != ShardState.TRANSFER:
            self.log_event(
                event="unexpected_transfer_ack",
                shard_id=shard_id,
                src=src,
                state=shard["state"].value,
            )
            return

        if src != shard["target"]:
            self.log_event(
                event="transfer_ack_wrong_target",
                shard_id=shard_id,
                src=src,
                expected_target=shard["target"],
            )
            return

        if message.epoch != shard["epoch"]:
            self.log_event(
                event="transfer_ack_stale_epoch",
                shard_id=shard_id,
                src=src,
                msg_epoch=message.epoch,
                current_epoch=shard["epoch"],
            )
            return

        self._cancel_phase_timer(shard_id, ShardState.TRANSFER)

        old_owner = shard["owner"]
        new_owner = shard["target"]
        old_epoch = shard["epoch"]
        new_epoch = old_epoch + 1

        self.store.update(
            shard_id,
            owner=new_owner,
            epoch=new_epoch,
            state=ShardState.ACTIVATE,
        )

        self.log_event(
            event="transfer_ack_accepted",
            shard_id=shard_id,
            old_owner=old_owner,
            new_owner=new_owner,
            old_epoch=old_epoch,
            new_epoch=new_epoch,
            state=ShardState.ACTIVATE.value,
        )
        
        self.log_event(
            event="activate_start",
            shard_id=shard_id,
            new_owner=new_owner,
            epoch=new_epoch,
            state=ShardState.ACTIVATE.value,
        )

        self.send(new_owner, ActivateShard(shard_id=shard_id, epoch=new_epoch))

        self.store.update(shard_id, state=ShardState.CLEANUP)

        self.log_event(
            event="cleanup_start",
            shard_id=shard_id,
            old_owner=old_owner,
            epoch=new_epoch,
            state=ShardState.CLEANUP.value,
        )

        self.send(old_owner, CleanupShard(shard_id=shard_id, epoch=new_epoch))

        self.store.update(shard_id, state=ShardState.STABLE, target=None)

        self.log_event(
            event="reassign_complete",
            shard_id=shard_id,
            owner=new_owner,
            epoch=new_epoch,
            state=ShardState.STABLE.value,
        )

    # --------------------------------------------------
    # Timeout / retry helpers
    # --------------------------------------------------

    def _phase_timeout_value(self, phase: ShardState) -> int | None:
        if phase == ShardState.FREEZE:
            return self.freeze_timeout
        if phase == ShardState.TRANSFER:
            return self.transfer_timeout
        return None

    def _phase_key(self, shard_id: str, phase: ShardState) -> tuple[str, str]:
        return (shard_id, phase.value)

    def _start_phase_timer(self, shard_id: str, phase: ShardState):
        timeout = self._phase_timeout_value(phase)
        if timeout is None:
            return

        key = self._phase_key(shard_id, phase)
        token = self._phase_tokens.get(key, 0) + 1
        self._phase_tokens[key] = token

        self.log_event(
            event="phase_timer_started",
            shard_id=shard_id,
            phase=phase.value,
            timeout=timeout,
            token=token,
        )

        def on_timeout():
            self._on_phase_timeout(shard_id, phase, token)

        self.network.loop.schedule(timeout, on_timeout)

    def _cancel_phase_timer(self, shard_id: str, phase: ShardState):
        key = self._phase_key(shard_id, phase)
        if key not in self._phase_tokens:
            return

        # bump token so scheduled callbacks for previous token become stale
        self._phase_tokens[key] += 1
        self._phase_retry_counts.pop(key, None)

        self.log_event(
            event="phase_timer_canceled",
            shard_id=shard_id,
            phase=phase.value,
        )

    def _on_phase_timeout(self, shard_id: str, phase: ShardState, token: int):
        key = self._phase_key(shard_id, phase)
        current_token = self._phase_tokens.get(key)
        if current_token != token:
            return

        shard = self.store.get(shard_id)
        if shard["state"] != phase:
            return

        retries = self._phase_retry_counts.get(key, 0)
        self.log_event(
            event="phase_timeout",
            shard_id=shard_id,
            phase=phase.value,
            retries=retries,
        )

        if retries >= self.max_retries:
            self.log_event(
                event="phase_retry_exhausted",
                shard_id=shard_id,
                phase=phase.value,
                retries=retries,
            )
            return

        self._phase_retry_counts[key] = retries + 1
        self._retry_phase_action(shard_id, phase, retries + 1)

    def _retry_phase_action(self, shard_id: str, phase: ShardState, retry_num: int):
        shard = self.store.get(shard_id)

        if phase == ShardState.FREEZE:
            self.log_event(
                event="phase_retry_send",
                shard_id=shard_id,
                phase=phase.value,
                retry=retry_num,
                target=shard["owner"],
            )
            self.send(
                shard["owner"],
                FreezeShard(shard_id=shard_id, epoch=shard["epoch"]),
            )
        elif phase == ShardState.TRANSFER:
            self.log_event(
                event="phase_retry_send",
                shard_id=shard_id,
                phase=phase.value,
                retry=retry_num,
                target=shard["owner"],
            )
            self.send(
                shard["owner"],
                BeginTransfer(
                    shard_id=shard_id,
                    epoch=shard["epoch"],
                    target=shard["target"],
                ),
            )
        else:
            return

        base = self._phase_timeout_value(phase)
        if base is None:
            return

        # exponential backoff by retry number: base * (retry_backoff ** (retry_num - 1))
        next_timeout = base * (self.retry_backoff ** (retry_num - 1))
        key = self._phase_key(shard_id, phase)
        next_token = self._phase_tokens.get(key, 0) + 1
        self._phase_tokens[key] = next_token

        self.log_event(
            event="phase_timer_restarted",
            shard_id=shard_id,
            phase=phase.value,
            timeout=next_timeout,
            retry=retry_num,
            token=next_token,
        )

        def on_timeout():
            self._on_phase_timeout(shard_id, phase, next_token)

        self.network.loop.schedule(next_timeout, on_timeout)

    # --------------------------------------------------
    # Logging helper
    # --------------------------------------------------

    def log_event(self, **fields):
        timestamp = self.network.loop.time if self.network and self.network.loop else "?"
        record = {
            "time": timestamp,
            "node": self.node_id,
            "seq": self._event_seq,
            **fields,
        }
        self._event_seq += 1
        self.event_log.append(record)
        print(f"[t={timestamp}] server={self.node_id} {fields}")