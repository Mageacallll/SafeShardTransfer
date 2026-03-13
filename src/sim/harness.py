"""
Experiment harness.

Responsibilities:
- create and connect nodes
- initialize state
- schedule actions
- inject crashes or faults
- run the simulation
"""

from sim.event_loop import EventLoop
from sim.network import Network


class Harness:
    def __init__(
        self,
        drop_prob: float = 0.0,
        min_delay: int = 1,
        max_delay: int = 1,
        seed: int = 0,
    ):
        self.loop = EventLoop()
        self.network = Network(
            self.loop,
            drop_prob=drop_prob,
            min_delay=min_delay,
            max_delay=max_delay,
            seed=seed,
        )
        self.nodes = {}

    def add_node(self, node):
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node
        self.network.register(node)

    def get_node(self, node_id: str):
        return self.nodes[node_id]

    def schedule(self, delay: int, fn, *args):
        self.loop.schedule(delay, fn, *args)

    def crash_node(self, node_id: str):
        node = self.get_node(node_id)
        node.crash()
        print(f"[t={self.loop.time}] HARNESS crash node={node_id}")

    def recover_node(self, node_id: str):
        node = self.get_node(node_id)
        node.recover()
        print(f"[t={self.loop.time}] HARNESS recover node={node_id}")

    def add_drop_rule(self, rule):
        self.network.add_drop_rule(rule)

    def clear_drop_rules(self):
        self.network.clear_drop_rules()

    def run(self, max_steps: int = 100_000):
        self.loop.run(max_steps=max_steps)