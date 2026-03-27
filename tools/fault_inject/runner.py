"""
Fault injection scenario runner.

Reads scenarios from scenarios.yaml, applies configured failures/noise,
runs the simulation, and prints a summary for each scenario.
"""

from pathlib import Path
import sys

# Allow direct script execution from repo root: `python tools/fault_inject/runner.py`
SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import yaml

from common.types import TransferShard
from metadata.coordinator import Coordinator
from metrics.collector import summarize_run
from shardserver.server import ShardServer
from sim.harness import Harness
from sim.network import LinkConfig


def setup_basic_system(
    *,
    freeze_timeout=None,
    transfer_timeout=None,
    max_retries=0,
    seed=0,
):
    h = Harness(drop_prob=0.0, min_delay=1, max_delay=1, seed=seed)

    coord = Coordinator(
        "coord",
        freeze_timeout=freeze_timeout,
        transfer_timeout=transfer_timeout,
        max_retries=max_retries,
    )
    a = ShardServer("A", coordinator_id="coord")
    b = ShardServer("B", coordinator_id="coord")

    h.add_node(coord)
    h.add_node(a)
    h.add_node(b)

    coord.init_shard("s1", owner="A", epoch=1)
    a.init_shard("s1", epoch=1, data={"k": "v"})

    return h, coord, a, b


def apply_setup(coord, a, setup_cfg):
    shard_id = setup_cfg["shard_id"]
    initial_owner = setup_cfg["initial_owner"]
    initial_epoch = setup_cfg["initial_epoch"]
    initial_data = setup_cfg.get("initial_data", {})

    coord.init_shard(shard_id, owner=initial_owner, epoch=initial_epoch)

    if initial_owner == "A":
        a.init_shard(shard_id, epoch=initial_epoch, data=initial_data)


def apply_injection(h, coord, inject_cfg):
    inject_type = inject_cfg["type"]

    if inject_type == "drop_message":
        message_type = inject_cfg["message_type"]

        def drop_rule(src, dst, msg):
            return msg.__class__.__name__ == message_type

        h.add_drop_rule(drop_rule)

    elif inject_type == "crash_node":
        h.schedule_at(inject_cfg["at_time"], h.crash_node, inject_cfg["node_id"])

    elif inject_type == "false_suspicion":
        # No network fault needed; runner will still trigger reassign below.
        pass

    elif inject_type == "cascading":
        for event in inject_cfg["events"]:
            event_type = event["type"]

            if event_type == "drop_message":
                message_type = event["message_type"]

                def drop_rule(src, dst, msg, expected=message_type):
                    return msg.__class__.__name__ == expected

                h.add_drop_rule(drop_rule)

            elif event_type == "crash_node":
                h.schedule_at(event["at_time"], h.crash_node, event["node_id"])

            else:
                raise ValueError(f"Unsupported cascading event type: {event_type}")

    elif inject_type == "partition":
        for link in inject_cfg["links"]:
            h.set_link_config(
                LinkConfig(
                    source=link["source"],
                    dest=link["dest"],
                    partition_enabled=True,
                    partition_start_time=link["start_time"],
                    partition_end_time=link["end_time"],
                )
            )

    elif inject_type == "link_noise":
        for link in inject_cfg["links"]:
            h.set_link_config(
                LinkConfig(
                    source=link["source"],
                    dest=link["dest"],
                    reorder_enabled=link.get("reorder_enabled", False),
                    duplicate_rate=link.get("duplicate_rate", 0.0),
                    delay_min_ms=link.get("delay_min_ms", 1),
                    delay_max_ms=link.get("delay_max_ms", 1),
                )
            )

    else:
        raise ValueError(f"Unsupported inject type: {inject_type}")


def run_scenario(scenario):
    name = scenario["name"]
    description = scenario.get("description", "")
    setup_cfg = scenario["setup"]
    inject_cfg = scenario["inject"]
    liveness_cfg = scenario.get("liveness", {})

    h, coord, a, b = setup_basic_system(
        freeze_timeout=liveness_cfg.get("freeze_timeout"),
        transfer_timeout=liveness_cfg.get("transfer_timeout"),
        max_retries=liveness_cfg.get("max_retries", 0),
        seed=liveness_cfg.get("seed", 0),
    )

    apply_setup(coord, a, setup_cfg)
    apply_injection(h, coord, inject_cfg)

    shard_id = setup_cfg["shard_id"]
    target_owner = setup_cfg["target_owner"]

    print("=" * 80)
    print(f"SCENARIO: {name}")
    if description:
        print(f"DESCRIPTION: {description}")
    print(
        "LIVENESS: "
        f"freeze_timeout={liveness_cfg.get('freeze_timeout')}, "
        f"transfer_timeout={liveness_cfg.get('transfer_timeout')}, "
        f"max_retries={liveness_cfg.get('max_retries', 0)}, "
        f"seed={liveness_cfg.get('seed', 0)}"
    )

    h.schedule(1, coord.reassign, shard_id, target_owner)
    h.run()

    metrics = summarize_run(coord, [a, b], shard_id, name)

    print(f"Outcome: {metrics['outcome']}")
    print(f"Completed: {metrics['completed']}")
    print(f"Aborted: {metrics['aborted']}")
    print(f"Converged: {metrics['converged']}")
    print(f"Stuck: {metrics['stuck']}")
    print(f"Stall State: {metrics['stall_state']}")
    print(f"Final Owner: {metrics['final_owner']}")
    print(f"Final Epoch: {metrics['final_epoch']}")
    print(f"Final State: {metrics['final_state']}")
    print(f"Total Reconfig Duration: {metrics['total_reconfig_duration']}")
    print(f"Freeze Duration: {metrics['freeze_duration']}")
    print(f"Transfer Duration: {metrics['transfer_duration']}")
    print(f"Cleanup Duration: {metrics['cleanup_duration']}")
    print(f"FreezeAck Count: {metrics['freeze_ack_count']}")
    print(f"TransferAck Count: {metrics['transfer_ack_count']}")
    print(f"TransferShard Sent Count: {metrics['transfer_shard_sent_count']}")
    print(f"Phase Timeout Count: {metrics['phase_timeout_count']}")
    print(f"Phase Retry Send Count: {metrics['phase_retry_send_count']}")
    print(f"Phase Retry Exhausted Count: {metrics['phase_retry_exhausted_count']}")
    print(f"Reassign Abort Count: {metrics['reassign_abort_count']}")
    print(f"Client Reject Reconfiguring: {metrics['client_reject_reconfiguring']}")
    print(f"Client Reject Epoch Mismatch: {metrics['client_reject_epoch_mismatch']}")
    print(f"Client Reject Missing Shard: {metrics['client_reject_missing_shard']}")

    return metrics


def main():
    scenario_file = Path(__file__).with_name("scenarios.yaml")
    with scenario_file.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    scenarios = config.get("scenarios", [])
    all_metrics = []

    for scenario in scenarios:
        metrics = run_scenario(scenario)
        all_metrics.append(metrics)

    print("=" * 80)
    print("SUMMARY")
    for m in all_metrics:
        print(
            f"{m['scenario_name']}: "
            f"outcome={m['outcome']}, "
            f"final_owner={m['final_owner']}, "
            f"final_state={m['final_state']}, "
            f"epoch={m['final_epoch']}"
        )


if __name__ == "__main__":
    main()