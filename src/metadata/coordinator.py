"""
Metadata coordinator for shard reconfiguration.

The coordinator owns the shard metadata state machine and drives
reassignment of shard ownership through the protocol:

STABLE -> FREEZE -> TRANSFER -> ACTIVATE -> CLEANUP -> STABLE
"""

from common.types import (
    ActivateShard,
    AbortReconfiguration,
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
        self._phase_tokens: dict[tuple[str, str, int], int] = {}
        self._phase_retry_counts: dict[tuple[str, str, int], int] = {}

        self._next_attempt_id = 1

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def init_shard(self, shard_id: str, owner: str, epoch: int = 1):
        """
        Initialize a shard in STABLE state.
        """
        self.store.init_shard(shard_id=shard_id, owner=owner, epoch=epoch)
        self.store.update(
            shard_id,
            target=None,
            attempt_id=None,
        )

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

        attempt_id = self._next_attempt_id
        self._next_attempt_id += 1

        self.store.update(
            shard_id,
            state=ShardState.FREEZE,
            target=new_owner,
            attempt_id=attempt_id,
        )

        self.log_event(
            event="reassign_start",
            shard_id=shard_id,
            old_owner=old_owner,
            new_owner=new_owner,
            epoch=current_epoch,
            attempt_id=attempt_id,
            state=ShardState.FREEZE.value,
        )

        self.send(
            old_owner,
            FreezeShard(
                shard_id=shard_id,
                epoch=current_epoch,
                attempt_id=attempt_id,
            ),
        )

        self._start_phase_timer(shard_id, ShardState.FREEZE, attempt_id)

    def on_node_crash(self, node_id: str):
        for shard_id, shard in list(self.store.shards.items()):
            if shard["state"] not in (ShardState.FREEZE, ShardState.TRANSFER):
                continue

            if node_id == shard["owner"] or node_id == shard["target"]:
                self.log_event(
                    event="participant_crash_detected",
                    shard_id=shard_id,
                    crashed_node=node_id,
                    attempt_id=shard.get("attempt_id"),
                    state=shard["state"].value,
                )
                self._abort_reconfiguration(
                    shard_id,
                    reason=f"participant_crash_{node_id}",
                )

    def on_node_recover(self, node_id: str):
        self.log_event(
            event="participant_recovered",
            node_id=node_id,
        )

        # Resynchronize recovered participants with coordinator metadata.
        for shard_id, shard in self.store.shards.items():
            if node_id != shard["owner"] and node_id != shard.get("target"):
                continue

            self.send(
                node_id,
                AbortReconfiguration(
                    shard_id=shard_id,
                    epoch=shard["epoch"],
                    attempt_id=shard.get("attempt_id"),
                    reason="resync_on_recover",
                ),
            )

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
                attempt_id=message.attempt_id,
                state=shard["state"].value,
            )
            return

        if src != shard["owner"]:
            self.log_event(
                event="freeze_ack_wrong_owner",
                shard_id=shard_id,
                src=src,
                attempt_id=message.attempt_id,
                expected_owner=shard["owner"],
            )
            return

        if message.epoch != shard["epoch"]:
            self.log_event(
                event="freeze_ack_stale_epoch",
                shard_id=shard_id,
                src=src,
                attempt_id=message.attempt_id,
                msg_epoch=message.epoch,
                current_epoch=shard["epoch"],
            )
            return

        if message.attempt_id != shard.get("attempt_id"):
            self.log_event(
                event="freeze_ack_attempt_mismatch",
                shard_id=shard_id,
                src=src,
                msg_attempt_id=message.attempt_id,
                current_attempt_id=shard.get("attempt_id"),
            )
            return

        attempt_id = shard["attempt_id"]

        self._cancel_phase_timer(shard_id, ShardState.FREEZE, attempt_id)

        self.store.update(shard_id, state=ShardState.TRANSFER)

        self.log_event(
            event="freeze_ack_accepted",
            shard_id=shard_id,
            old_owner=shard["owner"],
            new_owner=shard["target"],
            epoch=shard["epoch"],
            attempt_id=attempt_id,
            state=ShardState.TRANSFER.value,
        )

        self.send(
            shard["owner"],
            BeginTransfer(
                shard_id=shard_id,
                epoch=shard["epoch"],
                target=shard["target"],
                attempt_id=attempt_id,
            ),
        )

        self._start_phase_timer(shard_id, ShardState.TRANSFER, attempt_id)

    def _handle_transfer_ack(self, src: str, message: TransferAck):
        shard_id = message.shard_id
        shard = self.store.get(shard_id)

        if shard["state"] != ShardState.TRANSFER:
            self.log_event(
                event="unexpected_transfer_ack",
                shard_id=shard_id,
                src=src,
                attempt_id=message.attempt_id,
                state=shard["state"].value,
            )
            return

        if src != shard["target"]:
            self.log_event(
                event="transfer_ack_wrong_target",
                shard_id=shard_id,
                src=src,
                attempt_id=message.attempt_id,
                expected_target=shard["target"],
            )
            return

        if message.epoch != shard["epoch"]:
            self.log_event(
                event="transfer_ack_stale_epoch",
                shard_id=shard_id,
                src=src,
                attempt_id=message.attempt_id,
                msg_epoch=message.epoch,
                current_epoch=shard["epoch"],
            )
            return

        if message.attempt_id != shard.get("attempt_id"):
            self.log_event(
                event="transfer_ack_attempt_mismatch",
                shard_id=shard_id,
                src=src,
                msg_attempt_id=message.attempt_id,
                current_attempt_id=shard.get("attempt_id"),
            )
            return

        old_owner = shard["owner"]
        new_owner = shard["target"]
        old_epoch = shard["epoch"]
        attempt_id = shard["attempt_id"]
        new_epoch = old_epoch + 1

        self._cancel_phase_timer(shard_id, ShardState.TRANSFER, attempt_id)

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
            attempt_id=attempt_id,
            state=ShardState.ACTIVATE.value,
        )

        self.send(
            new_owner,
            ActivateShard(
                shard_id=shard_id,
                epoch=new_epoch,
                attempt_id=attempt_id,
            ),
        )

        self.store.update(shard_id, state=ShardState.CLEANUP)

        self.log_event(
            event="cleanup_start",
            shard_id=shard_id,
            old_owner=old_owner,
            new_owner=new_owner,
            epoch=new_epoch,
            attempt_id=attempt_id,
            state=ShardState.CLEANUP.value,
        )

        self.send(
            old_owner,
            CleanupShard(
                shard_id=shard_id,
                epoch=new_epoch,
                attempt_id=attempt_id,
            ),
        )

        self.store.update(
            shard_id,
            state=ShardState.STABLE,
            target=None,
            attempt_id=None,
        )

        self.log_event(
            event="reassign_complete",
            shard_id=shard_id,
            owner=new_owner,
            epoch=new_epoch,
            completed_attempt_id=attempt_id,
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

    def _phase_key(self, shard_id: str, phase: ShardState, attempt_id: int) -> tuple[str, str, int]:
        return (shard_id, phase.value, attempt_id)

    def _start_phase_timer(self, shard_id: str, phase: ShardState, attempt_id: int):
        timeout = self._phase_timeout_value(phase)
        if timeout is None:
            return

        key = self._phase_key(shard_id, phase, attempt_id)
        token = self._phase_tokens.get(key, 0) + 1
        self._phase_tokens[key] = token

        self.log_event(
            event="phase_timer_started",
            shard_id=shard_id,
            phase=phase.value,
            attempt_id=attempt_id,
            timeout=timeout,
            token=token,
        )

        def on_timeout():
            self._on_phase_timeout(shard_id, phase, attempt_id, token)

        self.network.loop.schedule(timeout, on_timeout)

    def _cancel_phase_timer(self, shard_id: str, phase: ShardState, attempt_id: int):
        key = self._phase_key(shard_id, phase, attempt_id)
        if key not in self._phase_tokens:
            return

        # bump token so scheduled callbacks for previous token become stale
        self._phase_tokens[key] += 1
        self._phase_retry_counts.pop(key, None)

        self.log_event(
            event="phase_timer_canceled",
            shard_id=shard_id,
            phase=phase.value,
            attempt_id=attempt_id,
        )

    def _on_phase_timeout(self, shard_id: str, phase: ShardState, attempt_id: int, token: int):
        key = self._phase_key(shard_id, phase, attempt_id)
        current_token = self._phase_tokens.get(key)
        if current_token != token:
            return

        shard = self.store.get(shard_id)
        if shard["state"] != phase:
            return
        if shard.get("attempt_id") != attempt_id:
            return

        retries = self._phase_retry_counts.get(key, 0)
        self.log_event(
            event="phase_timeout",
            shard_id=shard_id,
            phase=phase.value,
            attempt_id=attempt_id,
            retries=retries,
        )

        if retries >= self.max_retries:
            self.log_event(
                event="phase_retry_exhausted",
                shard_id=shard_id,
                phase=phase.value,
                attempt_id=attempt_id,
                retries=retries,
            )
            self._abort_reconfiguration(
                shard_id,
                reason=f"timeout_exhausted_{phase.value.lower()}",
            )
            return

        self._phase_retry_counts[key] = retries + 1
        self._retry_phase_action(shard_id, phase, attempt_id, retries + 1)

    def _retry_phase_action(self, shard_id: str, phase: ShardState, attempt_id: int, retry_num: int):
        shard = self.store.get(shard_id)

        if shard.get("attempt_id") != attempt_id:
            return

        if phase == ShardState.FREEZE:
            self.log_event(
                event="phase_retry_send",
                shard_id=shard_id,
                phase=phase.value,
                attempt_id=attempt_id,
                retry=retry_num,
                target=shard["owner"],
            )
            self.send(
                shard["owner"],
                FreezeShard(
                    shard_id=shard_id,
                    epoch=shard["epoch"],
                    attempt_id=attempt_id,
                ),
            )
        elif phase == ShardState.TRANSFER:
            self.log_event(
                event="phase_retry_send",
                shard_id=shard_id,
                phase=phase.value,
                attempt_id=attempt_id,
                retry=retry_num,
                target=shard["owner"],
            )
            self.send(
                shard["owner"],
                BeginTransfer(
                    shard_id=shard_id,
                    epoch=shard["epoch"],
                    target=shard["target"],
                    attempt_id=attempt_id,
                ),
            )
        else:
            return

        base = self._phase_timeout_value(phase)
        if base is None:
            return

        next_timeout = base * (self.retry_backoff ** (retry_num - 1))
        key = self._phase_key(shard_id, phase, attempt_id)
        next_token = self._phase_tokens.get(key, 0) + 1
        self._phase_tokens[key] = next_token

        self.log_event(
            event="phase_timer_restarted",
            shard_id=shard_id,
            phase=phase.value,
            attempt_id=attempt_id,
            timeout=next_timeout,
            retry=retry_num,
            token=next_token,
        )

        def on_timeout():
            self._on_phase_timeout(shard_id, phase, attempt_id, next_token)

        self.network.loop.schedule(next_timeout, on_timeout)

    def _abort_reconfiguration(self, shard_id: str, reason: str):
        shard = self.store.get(shard_id)
        prev_state = shard["state"]

        if prev_state == ShardState.STABLE:
            return

        old_owner = shard["owner"]
        target = shard["target"]
        old_epoch = shard["epoch"]
        attempt_id = shard.get("attempt_id")
        abort_epoch = old_epoch + 1

        if attempt_id is not None:
            self._cancel_phase_timer(shard_id, ShardState.FREEZE, attempt_id)
            self._cancel_phase_timer(shard_id, ShardState.TRANSFER, attempt_id)

        self.store.update(
            shard_id,
            owner=old_owner,
            epoch=abort_epoch,
            state=ShardState.STABLE,
            target=None,
            attempt_id=None,
        )

        self.log_event(
            event="reassign_abort",
            shard_id=shard_id,
            reason=reason,
            old_owner=old_owner,
            target=target,
            prev_state=prev_state.value,
            old_epoch=old_epoch,
            abort_epoch=abort_epoch,
            aborted_attempt_id=attempt_id,
        )

        self.send(
            old_owner,
            AbortReconfiguration(
                shard_id=shard_id,
                epoch=abort_epoch,
                attempt_id=attempt_id,
                reason=reason,
            ),
        )

        if target is not None and target != old_owner:
            self.send(
                target,
                AbortReconfiguration(
                    shard_id=shard_id,
                    epoch=abort_epoch,
                    attempt_id=attempt_id,
                    reason=reason,
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
            "seq": self._event_seq,
            **fields,
        }
        self._event_seq += 1
        self.event_log.append(record)
        print(f"[t={timestamp}] server={self.node_id} {fields}")