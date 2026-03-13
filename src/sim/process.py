"""
Base process abstraction for all simulated nodes.

All coordinator, shard server, and client nodes inherit from Process.
"""

from typing import Any


class Process:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.network = None
        self.alive = True

    def send(self, dst: str, message: Any):
        if not self.alive:
            return
        if self.network is None:
            raise RuntimeError(f"Process {self.node_id} is not attached to a network.")
        self.network.send(self.node_id, dst, message)

    def crash(self):
        self.alive = False

    def recover(self):
        self.alive = True

    def on_message(self, src: str, message: Any):
        raise NotImplementedError("Subclasses must implement on_message().")