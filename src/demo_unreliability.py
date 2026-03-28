"""
Unreliability demo: run a matrix of unstable reassignment scenarios.

This script complements demo_reassign.py by showcasing behavior under
network and crash faults with recovery logic enabled.
"""

from metadata.coordinator import Coordinator
from shardserver.server import ShardServer
from sim.harness import Harness
from sim.network import LinkConfig


def setup_system(seed: int = 0):
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=seed)

    coord = Coordinator(
        "coord",
        freeze_timeout=2,
        transfer_timeout=2,
        max_retries=3,
        retry_backoff=2,
    )
    a = ShardServer("A", coordinator_id="coord")
    b = ShardServer("B", coordinator_id="coord")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)
    a.init_shard("s1", epoch=1, data={"k": "v", "x": 1})

    return h, coord, a, b


def summarize(name: str, h: Harness, coord: Coordinator, a: ShardServer, b: ShardServer):
    meta = coord.store.get("s1")
    events = [e.get("event") for e in coord.event_log]

    return {
        "scenario": name,
        "time": h.loop.time,
        "final_owner": meta["owner"],
        "final_epoch": meta["epoch"],
        "final_state": meta["state"].value,
        "completed": "reassign_complete" in events,
        "aborted": "reassign_abort" in events,
        "timeouts": events.count("phase_timeout"),
        "retries": events.count("phase_retry_send"),
        "a_has_shard": "s1" in a.shards,
        "b_has_shard": "s1" in b.shards,
    }


def run_noise_then_complete():
    h, coord, a, b = setup_system(seed=11)

    h.set_link_config(
        LinkConfig(
            source="A",
            dest="B",
            reorder_enabled=True,
            duplicate_rate=0.5,
            delay_min_ms=1,
            delay_max_ms=5,
        )
    )
    h.set_link_config(
        LinkConfig(
            source="B",
            dest="coord",
            reorder_enabled=True,
            duplicate_rate=0.5,
            delay_min_ms=1,
            delay_max_ms=5,
        )
    )

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    return summarize("noise_then_complete", h, coord, a, b)


def run_partition_then_complete():
    h, coord, a, b = setup_system(seed=22)

    h.set_link_config(
        LinkConfig(
            source="coord",
            dest="A",
            partition_enabled=True,
            partition_start_time=1,
            partition_end_time=6,
        )
    )
    h.set_link_config(
        LinkConfig(
            source="A",
            dest="coord",
            partition_enabled=True,
            partition_start_time=1,
            partition_end_time=6,
        )
    )

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    return summarize("partition_then_complete", h, coord, a, b)


def run_drop_transfer_then_abort():
    h, coord, a, b = setup_system(seed=33)

    def drop_transfer(_src, _dst, msg):
        return msg.__class__.__name__ == "TransferShard"

    h.add_drop_rule(drop_transfer)

    h.schedule(1, coord.reassign, "s1", "B")
    h.run()

    return summarize("drop_transfer_then_abort", h, coord, a, b)


def run_crash_old_owner_then_abort_recover():
    h, coord, a, b = setup_system(seed=44)

    h.schedule(1, coord.reassign, "s1", "B")
    h.schedule(2, h.crash_node, "A")
    h.schedule(5, h.recover_node, "A")
    h.run()

    return summarize("crash_old_owner_abort_recover", h, coord, a, b)


def print_table(results):
    headers = [
        "scenario",
        "completed",
        "aborted",
        "final_owner",
        "final_epoch",
        "final_state",
        "timeouts",
        "retries",
        "sim_time",
    ]

    print("\n=== Unreliabile Network Demo Results ===")
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")

    for row in results:
        values = [
            row["scenario"],
            str(row["completed"]),
            str(row["aborted"]),
            row["final_owner"],
            str(row["final_epoch"]),
            row["final_state"],
            str(row["timeouts"]),
            str(row["retries"]),
            str(row["time"]),
        ]
        print("| " + " | ".join(values) + " |")


def main():
    print("Running unreliability demo matrix...")

    results = [
        run_noise_then_complete(),
        run_partition_then_complete(),
        run_drop_transfer_then_abort(),
        run_crash_old_owner_then_abort_recover(),
    ]

    print_table(results)


if __name__ == "__main__":
    main()
