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
from sim.network import Network, LinkConfig


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

    def schedule_at(self, at_time: int, fn, *args):
        delay = at_time - self.loop.time
        if delay < 0:
            raise ValueError(f"Cannot schedule in the past: at_time={at_time}, now={self.loop.time}")
        self.loop.schedule(delay, fn, *args)

    def crash_node(self, node_id: str):
        node = self.get_node(node_id)
        node.crash()

        for observer in self.nodes.values():
            if hasattr(observer, "on_node_crash") and callable(observer.on_node_crash):
                observer.on_node_crash(node_id)

        print(f"[t={self.loop.time}] HARNESS crash node={node_id}")

    def recover_node(self, node_id: str):
        node = self.get_node(node_id)
        node.recover()

        for observer in self.nodes.values():
            if hasattr(observer, "on_node_recover") and callable(observer.on_node_recover):
                observer.on_node_recover(node_id)

        print(f"[t={self.loop.time}] HARNESS recover node={node_id}")

    def add_drop_rule(self, rule):
        self.network.add_drop_rule(rule)

    def clear_drop_rules(self):
        self.network.clear_drop_rules()

    def set_link_config(self, config: LinkConfig):
        self.network.set_link_config(config)

    def clear_link_configs(self):
        self.network.clear_link_configs()

    def schedule_failures(self, failure_schedule: list[dict]):
        """
        Schedule failure events from declarative entries.

        Supported entries:
        - {"time": int, "type": "crash", "node_id": str}
        - {"time": int, "type": "recover", "node_id": str}
        - {
            "time": int,
            "type": "link_config",
            "source": str,
            "dest": str,
            "config": {...LinkConfig kwargs except source/dest...}
          }
        """
        for item in failure_schedule:
            event_type = item.get("type")
            at_time = item.get("time")

            if event_type == "crash":
                self.schedule_at(at_time, self.crash_node, item["node_id"])
            elif event_type == "recover":
                self.schedule_at(at_time, self.recover_node, item["node_id"])
            elif event_type == "link_config":
                source = item["source"]
                dest = item["dest"]
                config_kwargs = dict(item.get("config", {}))

                def apply_link(src=source, dst=dest, kwargs=config_kwargs):
                    self.set_link_config(
                        LinkConfig(
                            source=src,
                            dest=dst,
                            **kwargs,
                        )
                    )

                self.schedule_at(at_time, apply_link)
            else:
                raise ValueError(f"Unknown failure type in schedule: {event_type}")

    def run(self, max_steps: int = 100_000):
        self.loop.run(max_steps=max_steps)