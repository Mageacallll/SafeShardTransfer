# Failure Injection Experiments — Shard Reassignment Protocol

This document summarizes early adversarial experiments conducted on the freeze-based shard reassignment protocol. The goal of these experiments is to observe how the system behaves under message loss, node crashes, and false failure suspicions.

All experiments were executed using the deterministic simulator and the manual scenario runner:

python tools/fault_inject/runner.py <scenario_name>


The initial system configuration for all scenarios was:

- shard: `s1`
- initial owner: `A`
- target owner: `B`
- epoch: `1`
- shard data: `{k: v}`

---

# Scenario 1 — Dropped Transfer Message

Command:
python tools/fault_inject/runner.py drop_transfer_shard_message
Observed timeline (truncated):


reassign_start
freeze_enter
freeze_ack_accepted
transfer_out_start


Final metadata:


owner: A
epoch: 1
state: TRANSFER
target: B


Final server state:


A shards: {s1}
B shards: {}


### Interpretation

The `TransferShard` message from `A` to `B` was dropped. As a result:

- the new owner never received the shard
- no `TransferAck` was generated
- the coordinator remained in the `TRANSFER` state

Importantly, **the protocol did not activate the new owner**. This prevented two nodes from serving the same shard simultaneously.

### Insight

The protocol successfully preserved **single-owner safety**, but **liveness failed**. Without retry or timeout logic, the system becomes stuck in `TRANSFER` when the transfer message is lost.

This demonstrates a deliberate tradeoff: the design prioritizes safety over availability under unreliable communication.

---

# Scenario 2 — Old Owner Crash During FREEZE

Command:


python tools/fault_inject/runner.py old_owner_crash_during_freeze


Observed timeline:


reassign_start
HARNESS crash node=A


Final metadata:


owner: A
epoch: 1
state: FREEZE
target: B


Final server state:


A shards: {s1}
B shards: {}


### Interpretation

The old owner crashed before processing the freeze request. Because no `FreezeAck` was received:

- the coordinator remained in `FREEZE`
- transfer never started

The shard still exists on the crashed node, but the system cannot proceed with reassignment.

### Insight

Again, safety is preserved: the new owner is never activated and no dual ownership occurs. However, the protocol is unable to make progress if the old owner fails before acknowledging the freeze.

This experiment highlights a limitation of the current MVP design: **reconfiguration depends on participation from the previous owner**.

---

# Scenario 3 — New Owner Crash Before Transfer Acknowledgment

Command:


python tools/fault_inject/runner.py new_owner_crash_before_transfer_ack


Observed timeline:


reassign_start
freeze_enter
freeze_ack_accepted
transfer_out_start
HARNESS crash node=B


Final metadata:


owner: A
epoch: 1
state: TRANSFER
target: B


Final server state:


A shards: {s1}
B shards: {}


### Interpretation

The shard transfer began, but the new owner crashed before receiving the transfer and sending `TransferAck`.

As in the dropped-message scenario:

- the coordinator remained in `TRANSFER`
- activation never occurred
- the old owner retained the shard

### Insight

The protocol again preserved safety: the new owner was never activated incorrectly. However, the reassignment process stalled because the transfer acknowledgment never arrived.

This demonstrates another liveness limitation of the current protocol.

---

# Scenario 4 — False Suspicion Reconfiguration

Command:


python tools/fault_inject/runner.py false_suspicion_safe_reconfig


Observed timeline (truncated):


reassign_start
freeze_enter
freeze_ack_accepted
transfer_out_start
transfer_in_received
transfer_ack_accepted
activate_complete
cleanup_complete
reassign_complete


Final metadata:


owner: B
epoch: 2
state: STABLE


Final server state:


A shards: {}
B shards: {s1}


### Interpretation

The system triggered a reassignment even though the original owner was healthy. The protocol completed successfully and transferred ownership from `A` to `B`.

### Insight

This scenario demonstrates that the protocol's **correctness does not depend on accurate failure detection**. Even if a node is falsely suspected, the reassignment proceeds safely.

However, the protocol temporarily blocks operations during the `FREEZE` phase, meaning an unnecessary reconfiguration can reduce availability.

---

# Key Observations

Across all scenarios, a consistent pattern emerged:

| Scenario | Safety | Liveness |
|--------|--------|--------|
Dropped transfer message | preserved | stalled |
Old owner crash | preserved | stalled |
New owner crash | preserved | stalled |
False suspicion | preserved | completes |

The protocol reliably prevents dual ownership of shards. However, it lacks mechanisms for recovering from partial failures during reassignment.

---

# Design Tradeoff

A core design decision in this project was:

> We sacrificed availability during shard reassignment to preserve single-owner safety.

The `FREEZE` stage blocks operations to ensure that no concurrent writes occur during shard transfer. As shown in the experiments above, this approach guarantees correctness but can cause the system to stall if failures occur during reconfiguration.

Future work could explore mechanisms such as:

- transfer retries
- timeout-based abort
- coordinator-driven recovery

to improve liveness while preserving safety.