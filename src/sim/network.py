"""
Simulated message-passing network.

Supports:
- deterministic or configurable delay
- probabilistic drops
- targeted drop rules
- node crash awareness
"""

import random
from typing import Any, Callable


class Network:
    def __init__(
        self,
        loop,
        drop_prob: float = 0.0,
        min_delay: int = 1,
        max_delay: int = 1,
        seed: int = 0,
    ):
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError("Require 0 <= min_delay <= max_delay")

        self.loop = loop
        self.nodes = {}
        self.drop_prob = drop_prob
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.random = random.Random(seed)

        # Each rule: fn(src, dst, msg) -> bool, where True means drop
        self.drop_rules: list[Callable[[str, str, Any], bool]] = []

    def register(self, node):
        self.nodes[node.node_id] = node
        node.network = self

    def unregister(self, node_id: str):
        if node_id in self.nodes:
            self.nodes[node_id].network = None
            del self.nodes[node_id]

    def add_drop_rule(self, rule: Callable[[str, str, Any], bool]):
        self.drop_rules.append(rule)

    def clear_drop_rules(self):
        self.drop_rules.clear()

    def send(self, src: str, dst: str, message: Any):
        # sender missing or crashed
        if src not in self.nodes or not self.nodes[src].alive:
            return

        # destination missing: model as lost
        if dst not in self.nodes:
            return

        # targeted drop rules
        for rule in self.drop_rules:
            if rule(src, dst, message):
                return

        # probabilistic drop
        if self.random.random() < self.drop_prob:
            return

        delay = self.random.randint(self.min_delay, self.max_delay)

        def deliver():
            if dst not in self.nodes:
                return

            dst_node = self.nodes[dst]
            if not dst_node.alive:
                return

            dst_node.on_message(src, message)

        self.loop.schedule(delay, deliver)