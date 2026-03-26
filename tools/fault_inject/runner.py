import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness
from metrics.collector import summarize_run
from client.client import Client


def setup_basic_system():
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=0)

    coord = Coordinator("coord")
    a = ShardServer("A", coordinator_id="coord")
    b = ShardServer("B", coordinator_id="coord")
    client = Client("client1", default_server_id="A", max_retries=2, retry_delay=1)

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)
    h.add_node(client)

    coord.init_shard("s1", owner="A", epoch=1)
    a.init_shard("s1", epoch=1, data={"k": "v"})

    client.set_shard_owner("s1", "A")

    return h, coord, a, b, client

# Helper to schedule client operations when it is idle (no pending request)
def schedule_when_idle(h, client, delay, fn, *args):
    def try_start():
        if client.pending_request is None:
            fn(*args)
        else:
            h.schedule(1, try_start)

    h.schedule(delay, try_start)

# workload helper
def schedule_client_workload(h, client, expect_post_reconfig_owner=False):
    schedule_when_idle(h, client, 0, client.get, "s1", 1, "k")
    schedule_when_idle(h, client, 3, client.get, "s1", 1, "k")
    schedule_when_idle(h, client, 6, client.put, "s1", 1, "x", "during_reconfig")

    if expect_post_reconfig_owner:
        h.schedule(8, client.set_shard_owner, "s1", "B")
        schedule_when_idle(h, client, 9, client.get, "s1", 2, "k")
    else:
        schedule_when_idle(h, client, 9, client.get, "s1", 1, "k")

def run_scenario(name: str):
    h, coord, a, b, client = setup_basic_system()

    if name == "drop_transfer_shard_message":
        def drop_transfer(src, dst, msg):
            return msg.__class__.__name__ == "TransferShard"

        h.add_drop_rule(drop_transfer)
        h.schedule(1, coord.reassign, "s1", "B")
        schedule_client_workload(h, client, expect_post_reconfig_owner=False)

    elif name == "old_owner_crash_during_freeze":
        h.schedule(1, coord.reassign, "s1", "B")
        h.schedule(2, h.crash_node, "A")
        schedule_client_workload(h, client, expect_post_reconfig_owner=False)

    elif name == "new_owner_crash_before_transfer_ack":
        h.schedule(1, coord.reassign, "s1", "B")
        h.schedule(5, h.crash_node, "B")
        schedule_client_workload(h, client, expect_post_reconfig_owner=False)

    elif name == "false_suspicion_safe_reconfig":
        h.schedule(1, coord.reassign, "s1", "B")
        schedule_client_workload(h, client, expect_post_reconfig_owner=True)

    else:
        raise ValueError(f"Unknown scenario: {name}")

    h.run()

    metrics = summarize_run(
        coordinator=coord,
        servers=[a, b],
        shard_id="s1",
        scenario_name=name,
    )

    print("\n=== Final Metadata ===")
    print(coord.store.get("s1"))

    print("\n=== Server State ===")
    print("A shards:", a.shards)
    print("B shards:", b.shards)

    print("\n=== Client Replies ===")
    for src, reply in client.replies:
        print(src, reply)

    print("\n=== Event Counts ===")
    print("coord:", len(coord.event_log))
    print("A:", len(a.event_log))
    print("B:", len(b.event_log))
    print("client:", len(client.event_log))

    print("\n=== Metrics Summary ===")
    for k, v in metrics.items():
        print(f"{k}: {v}")

    return metrics

def generate_markdown_table(results):
    headers = [
        "Scenario",
        "Completed",
        "Stall State",
        "Final Owner",
        "Final Epoch",
        "Final State",
        "Freeze Duration",
        "Transfer Duration",
        "Transfer Ack",
    ]

    lines = []

    # header
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")

    for r in results:
        row = [
            r["scenario_name"],
            "Yes" if r["completed"] else "No",
            r["stall_state"] or "-",
            r["final_owner"],
            str(r["final_epoch"]),
            r["final_state"],
            str(r["freeze_duration"]) if r["freeze_duration"] is not None else "-",
            str(r["transfer_duration"]) if r["transfer_duration"] is not None else "-",
            str(r["transfer_ack_count"]),
        ]

        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

def run_all_scenarios():
    scenarios = [
        "false_suspicion_safe_reconfig",
        "drop_transfer_shard_message",
        "old_owner_crash_during_freeze",
        "new_owner_crash_before_transfer_ack",
    ]

    results = []

    for name in scenarios:
        print(f"\n===== Running: {name} =====")
        metrics = run_scenario(name)
        results.append(metrics)

    print("\n\n=== Markdown Table ===\n")
    print(generate_markdown_table(results))

if __name__ == "__main__":
    if len(sys.argv) == 2:
        run_scenario(sys.argv[1])
    else:
        run_all_scenarios()