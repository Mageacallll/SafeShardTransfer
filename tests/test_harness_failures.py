from sim.harness import Harness
from sim.process import Process


class ProbeNode(Process):
    def __init__(self, node_id: str):
        super().__init__(node_id)
        self.crash_events = []
        self.recover_events = []

    def on_message(self, src, message):
        pass

    def on_node_crash(self, node_id: str):
        self.crash_events.append((self.network.loop.time, node_id))

    def on_node_recover(self, node_id: str):
        self.recover_events.append((self.network.loop.time, node_id))


def test_schedule_at_runs_at_absolute_time():
    h = Harness(seed=0)
    probe = ProbeNode("probe")
    h.add_node(probe)

    fired = []

    def mark(x):
        fired.append((h.loop.time, x))

    h.schedule_at(5, mark, "ok")
    h.run()

    assert fired == [(5, "ok")]


def test_schedule_failures_crash_and_recover_notify_observers():
    h = Harness(seed=0)
    a = ProbeNode("A")
    b = ProbeNode("B")
    h.add_node(a)
    h.add_node(b)

    h.schedule_failures(
        [
            {"time": 2, "type": "crash", "node_id": "A"},
            {"time": 4, "type": "recover", "node_id": "A"},
        ]
    )
    h.run()

    assert (2, "A") in b.crash_events
    assert (4, "A") in b.recover_events


def test_schedule_failures_applies_link_config():
    h = Harness(seed=0)
    a = ProbeNode("A")
    b = ProbeNode("B")
    h.add_node(a)
    h.add_node(b)

    h.schedule_failures(
        [
            {
                "time": 1,
                "type": "link_config",
                "source": "A",
                "dest": "B",
                "config": {
                    "drop_rate": 0.25,
                    "delay_min_ms": 2,
                    "delay_max_ms": 4,
                    "reorder_enabled": True,
                },
            }
        ]
    )
    h.run()

    cfg = h.network.get_link_config("A", "B")
    assert cfg is not None
    assert cfg.drop_rate == 0.25
    assert cfg.delay_min_ms == 2
    assert cfg.delay_max_ms == 4
    assert cfg.reorder_enabled is True
