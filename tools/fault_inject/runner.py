import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness


def setup_basic_system():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord")
    a = ShardServer("A", coordinator_id="coord")
    b = ShardServer("B", coordinator_id="coord")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)
    a.init_shard("s1", epoch=1, data={"k": "v"})

    return h, coord, a, b


def run_scenario(name: str):
    h, coord, a, b = setup_basic_system()

    if name == "drop_transfer_shard_message":
        def drop_transfer(src, dst, msg):
            return msg.__class__.__name__ == "TransferShard"

        h.add_drop_rule(drop_transfer)
        h.schedule(1, coord.reassign, "s1", "B")

    elif name == "old_owner_crash_during_freeze":
        h.schedule(1, coord.reassign, "s1", "B")
        h.schedule(2, h.crash_node, "A")

    elif name == "new_owner_crash_before_transfer_ack":
        h.schedule(1, coord.reassign, "s1", "B")
        h.schedule(5, h.crash_node, "B")

    elif name == "false_suspicion_safe_reconfig":
        h.schedule(1, coord.reassign, "s1", "B")

    else:
        raise ValueError(f"Unknown scenario: {name}")

    h.run()

    print("\n=== Final Metadata ===")
    print(coord.store.get("s1"))

    print("\n=== Server State ===")
    print("A shards:", a.shards)
    print("B shards:", b.shards)

    print("\n=== Event Counts ===")
    print("coord:", len(coord.event_log))
    print("A:", len(a.event_log))
    print("B:", len(b.event_log))


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python tools/fault_inject/runner.py <scenario_name>")
        raise SystemExit(1)

    run_scenario(sys.argv[1])