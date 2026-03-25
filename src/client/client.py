from common.types import ClientReply, ClientRequest
from sim.process import Process


class Client(Process):
    """
    Minimal safe client for the freeze-based shard reassignment simulator.

    Design constraints:
    - supports only one in-flight request at a time
    - uses simulator time / scheduling only
    - retries on reconfiguration-related errors
    - keeps a simple local routing hint: shard_id -> server_id
    """

    RETRYABLE_ERRORS = {
        "reconfiguring",
        "wrong_owner_or_missing_shard",
        "stale_or_wrong_epoch",
    }

    def __init__(
        self,
        node_id: str,
        default_server_id: str | None = None,
        max_retries: int = 3,
        retry_delay: int = 1,
    ):
        super().__init__(node_id)

        self.default_server_id = default_server_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Simple local routing hint: shard_id -> server_id
        self.routing_table = {}

        # Only one outstanding request is supported safely.
        self.pending_request = None

        # Collected replies for inspection/tests
        self.replies = []

        # Event log for observability
        self.event_log = []
        self._event_seq = 0

    # --------------------------------------------------
    # Routing helpers
    # --------------------------------------------------

    def set_shard_owner(self, shard_id: str, server_id: str):
        self.routing_table[shard_id] = server_id
        self.log_event(
            event="route_set",
            shard_id=shard_id,
            server=server_id,
        )

    def get_route(self, shard_id: str) -> str | None:
        return self.routing_table.get(shard_id, self.default_server_id)

    def invalidate_route(self, shard_id: str):
        if shard_id in self.routing_table:
            old = self.routing_table[shard_id]
            del self.routing_table[shard_id]
            self.log_event(
                event="route_invalidated",
                shard_id=shard_id,
                old_server=old,
            )

    # --------------------------------------------------
    # Public request API
    # --------------------------------------------------

    def get(self, shard_id: str, epoch: int, key: str):
        return self._start_request(
            shard_id=shard_id,
            epoch=epoch,
            key=key,
            value=None,
            op="GET",
        )

    def put(self, shard_id: str, epoch: int, key: str, value):
        return self._start_request(
            shard_id=shard_id,
            epoch=epoch,
            key=key,
            value=value,
            op="PUT",
        )

    def _start_request(self, shard_id: str, epoch: int, key: str, value, op: str):
        if self.pending_request is not None:
            raise RuntimeError(
                "Client supports only one in-flight request at a time."
            )

        target = self.get_route(shard_id)
        if target is None:
            self.log_event(
                event="request_failed_no_route",
                shard_id=shard_id,
                op=op,
            )
            return False

        self.pending_request = {
            "shard_id": shard_id,
            "epoch": epoch,
            "key": key,
            "value": value,
            "op": op,
            "target": target,
            "retries": 0,
        }

        self.log_event(
            event="request_start",
            shard_id=shard_id,
            op=op,
            epoch=epoch,
            target=target,
        )

        self._send_pending_request()
        return True

    def _send_pending_request(self):
        req = self.pending_request
        if req is None:
            return

        self.log_event(
            event="request_sent",
            shard_id=req["shard_id"],
            op=req["op"],
            epoch=req["epoch"],
            target=req["target"],
            retry=req["retries"],
        )

        self.send(
            req["target"],
            ClientRequest(
                shard_id=req["shard_id"],
                epoch=req["epoch"],
                key=req["key"],
                value=req["value"],
                op=req["op"],
            ),
        )

    # --------------------------------------------------
    # Reply handling
    # --------------------------------------------------

    def on_message(self, src: str, message):
        if not isinstance(message, ClientReply):
            self.log_event(
                event="unknown_message",
                src=src,
                message_type=message.__class__.__name__,
            )
            return

        self.replies.append((src, message))

        if self.pending_request is None:
            self.log_event(
                event="orphan_reply",
                src=src,
                success=message.success,
                error=message.error,
            )
            return

        req = self.pending_request

        # Reply from unexpected server
        if src != req["target"]:
            self.log_event(
                event="reply_wrong_source",
                expected=req["target"],
                actual=src,
                shard_id=req["shard_id"],
            )
            return

        if message.success:
            self.log_event(
                event="request_success",
                shard_id=req["shard_id"],
                op=req["op"],
                target=src,
                value=message.value,
            )
            self.pending_request = None
            return

        # Failure path
        error = message.error
        self.log_event(
            event="request_error",
            shard_id=req["shard_id"],
            op=req["op"],
            target=src,
            error=error,
            retry=req["retries"],
        )

        if error in self.RETRYABLE_ERRORS and req["retries"] < self.max_retries:
            req["retries"] += 1

            # Invalidate routing hint on ownership/reconfiguration related failures
            self.invalidate_route(req["shard_id"])

            # Fall back to default server if no specific route is known
            new_target = self.get_route(req["shard_id"])
            if new_target is not None:
                req["target"] = new_target

            self.log_event(
                event="request_retry_scheduled",
                shard_id=req["shard_id"],
                op=req["op"],
                target=req["target"],
                retry=req["retries"],
                delay=self.retry_delay,
            )

            # Use simulator scheduling only
            self.network.loop.schedule(self.retry_delay, self._send_pending_request)
            return

        self.log_event(
            event="request_failed",
            shard_id=req["shard_id"],
            op=req["op"],
            target=src,
            error=error,
        )
        self.pending_request = None

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
        print(f"[t={timestamp}] client={self.node_id} {fields}")