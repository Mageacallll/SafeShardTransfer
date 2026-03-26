# Project Status — Freeze-Based Shard Reassignment Protocol

This document summarizes the current state of the capstone project implementation and evaluation.  
It serves as a checkpoint describing what has been implemented, what has been tested, and what remains to be explored.

The goal of this project is to design and experimentally evaluate a protocol for **safe shard reassignment in a sharded key-value system** under unreliable failure detection.

---

# 1. Project Goal

The project investigates the safety of shard reassignment in distributed systems where:

- failure detectors are unreliable
- nodes may crash or become unreachable
- messages may be dropped or delayed

The core challenge is **preventing split-brain ownership of shards**.

To address this, the system treats reassignment as a **configuration commit protocol** with explicit states:


STABLE → FREEZE → TRANSFER → ACTIVATE → CLEANUP


During reassignment:

- the old owner is frozen
- the shard state is transferred
- the new owner is activated
- the old owner cleans up

Operations for the shard are blocked during the transition to preserve safety.

---

# 2. Current Architecture

The system is implemented as a **deterministic discrete-event simulator** written in Python.

Instead of running a real distributed system, we simulate processes and network behavior. This enables controlled fault injection and deterministic replay.

The main components are:


src/
├── metadata/
│ ├── coordinator.py
│ └── store.py
│
├── shardserver/
│ ├── server.py
│ └── storage.py
│
├── client/
│ └── client.py
│
└── sim/
├── harness.py
└── demo_reassign.py


### Metadata / Control Plane

The **Coordinator** implements the shard reassignment state machine.

Responsibilities:

- initiate reconfiguration
- manage shard metadata
- enforce epoch fencing
- coordinate transfer and activation

Metadata includes:

- shard owner
- shard epoch
- protocol state
- transfer target

---

### Shard Servers (Data Plane)

Each server:

- stores shard data in a simple key-value dictionary
- enforces **epoch-gated execution**
- blocks operations during `FREEZE` and `TRANSFER`
- logs events for observability

The MVP assumes **one active owner per shard** (no replication).

---

### Deterministic Simulator

The simulator provides:

- logical time
- deterministic event scheduling
- message delivery simulation
- node crash injection

This allows controlled experiments without real networking.

---

# 3. Protocol Implementation Status

The following protocol stages are implemented:

| Stage | Implemented |
|------|-------------|
STABLE | ✓ |
FREEZE | ✓ |
TRANSFER | ✓ |
ACTIVATE | ✓ |
CLEANUP | ✓ |

Coordinator transitions have been implemented and verified through unit tests.

The coordinator enforces:

- epoch monotonicity
- unique active owner
- correct state transitions

---

# 4. Test Coverage

A set of automated tests verify core protocol properties.


tests/
├── test_coordinator_behavior.py
├── test_server_behavior.py
├── test_invariants.py
├── test_reconfig_paths.py
└── test_failure_injection.py


The test suite currently checks:

### Coordinator Behavior

- correct state transitions
- correct handling of acknowledgments
- epoch bump correctness

### Server Behavior

- epoch-gated request handling
- freezing behavior
- transfer message handling

### Protocol Invariants

The following safety properties are verified:

- unique active shard owner
- monotonic epoch progression
- correct ownership transitions

### Protocol Path Execution

Tests verify that the protocol follows the intended event order:


reassign_start
freeze_enter
freeze_ack_accepted
transfer_out_start
transfer_in_received
transfer_ack_accepted
activate_complete
cleanup_complete
reassign_complete


---

# 5. Failure Injection Framework

To evaluate the protocol under adverse conditions, we implemented a lightweight failure injection system.

Failure scenarios are defined in:


tools/fault_inject/scenarios.yaml


Experiments are executed using:


python tools/fault_inject/runner.py <scenario>


The runner initializes the simulator and applies fault injection rules.

---

# 6. Failure Scenarios Tested

Four initial adversarial scenarios were implemented.

---

## 6.1 Dropped Transfer Message

Fault:


TransferShard message dropped


Result:

- coordinator remains in `TRANSFER`
- new owner never activates
- old owner retains the shard

Observation:

The protocol **preserves safety** but **fails to make progress**.

---

## 6.2 Old Owner Crash During FREEZE

Fault:


old owner crashes before FreezeAck


Result:

- coordinator remains in `FREEZE`
- reassignment cannot proceed

Observation:

The protocol prevents unsafe activation but cannot recover without the old owner.

---

## 6.3 New Owner Crash Before Transfer Acknowledgment

Fault:


new owner crashes before TransferAck


Result:

- coordinator remains in `TRANSFER`
- reassignment stalls

Observation:

Safety preserved, but liveness fails.

---

## 6.4 False Suspicion Reconfiguration

Fault:


healthy node falsely suspected


Result:

- full reassignment completed
- ownership moved from A to B

Observation:

Protocol correctness does not depend on accurate failure detection.

However, unnecessary reconfiguration temporarily blocks operations.

---

# 7. Key Insight So Far

Across all experiments:

| Scenario | Safety | Liveness |
|--------|--------|--------|
Dropped transfer | preserved | stalled |
Old owner crash | preserved | stalled |
New owner crash | preserved | stalled |
False suspicion | preserved | completes |

The protocol **successfully enforces single-owner safety**, but **does not guarantee progress under partial failures**.

This is a direct consequence of the design decision to require explicit acknowledgments before activating the new owner.

---

# 8. Core Design Tradeoff

A deliberate tradeoff in this design is:

> We sacrificed availability during shard reassignment in order to preserve single-owner safety.

The **FREEZE phase blocks operations**, ensuring no concurrent writes occur during transfer.

This simplifies reasoning about correctness but introduces potential availability loss.

---

# 9. What Has Been Completed

At this stage, the following work has been completed:

- protocol design documentation
- coordinator implementation
- shard server implementation
- deterministic simulator harness
- automated protocol tests
- adversarial failure scenarios
- manual experiment runner
- initial experimental report

The protocol core is now functioning and testable.

---

# 10. Work Remaining

Several areas remain to be explored.

### Experiment Infrastructure

- richer failure injection controls
- more systematic scenario execution
- automated experiment runs

### Metrics and Observability

Implemented metrics include:

freeze duration
reassignment completion time
transfer acknowledgment counts
client rejection counts during reconfiguration

### Protocol Refinement

Experiments suggest potential improvements:

- transfer retries
- timeout-based abort
- recovery from stalled transfers

### Evaluation

Future work will analyze:

- safety vs availability tradeoffs
- protocol behavior under repeated faults
- cost of unnecessary reconfiguration

---

# 11. Current Development Status

As of this checkpoint:

- the protocol implementation is stable
- the core safety invariants hold
- several liveness limitations have been identified

The next stage of the project will focus on **systematic experimentation and analysis** rather than adding new protocol features.

---

# 12. Repository State

All current tests pass.


pytest
17 passed


The repository now contains:

- a working protocol implementation
- deterministic experiment infrastructure
- reproducible failure scenarios

This provides a stable foundation for deeper evaluation and further design exp

# 13. Experimental Results

We evaluated the protocol under four representative scenarios using the deterministic simulator and fault injection framework.

- 13.1 Summary Table
| Scenario | Completed | Stall State | Final Owner | Final Epoch | Final State | Freeze Duration | Transfer Duration | Transfer Ack |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| false_suspicion_safe_reconfig | Yes | - | B | 2 | STABLE | 2 | 3 | 1 |
| drop_transfer_shard_message | No | TRANSFER | A | 1 | TRANSFER | 2 | - | 0 |
| old_owner_crash_during_freeze | No | FREEZE | A | 1 | FREEZE | - | - | 0 |
| new_owner_crash_before_transfer_ack | No | TRANSFER | A | 1 | TRANSFER | 2 | - | 0 |


Results are generated using the experiment runner and metrics collector

- 13.2 Observations
Successful Reconfiguration

In the absence of faults (false suspicion scenario):

The protocol completes successfully
Ownership moves from A → B
Epoch increases from 1 → 2
Final state returns to STABLE

This demonstrates that correctness does not depend on accurate failure detection.

Failure Scenarios

Across all failure scenarios:

Reconfiguration does not complete
Ownership remains with the original node (A)
Epoch remains unchanged (1)
No incorrect activation occurs

This confirms that:

The protocol consistently preserves single-owner safety even under failures.

Stall Behavior by Phase

Failures cause the protocol to stall in different phases:

FREEZE stall
Occurs when the old owner crashes before acknowledging freeze
→ system cannot proceed to transfer
TRANSFER stall
Occurs when:
transfer message is dropped, or
new owner crashes before acknowledgment
→ system cannot commit ownership

This distinction highlights that:

Progress depends on successful completion of each phase and its acknowledgment.

Message-Level Insights

From the metrics:

freeze_ack_count = 0 → no progress beyond FREEZE
transfer_ack_count = 0 → no ownership commit
transfer_ack_count = 1 → successful reconfiguration

This shows that:

Acknowledgments are the key drivers of protocol progress.

- 13.3 Safety Analysis

The protocol enforces safety through:

freezing the old owner before transfer
delaying activation until transfer is acknowledged
incrementing the epoch only upon ownership commit
rejecting requests with mismatched epoch or non-STABLE state

As a result:

There is no execution in which two servers simultaneously serve the same shard.

- 13.4 Liveness Analysis

The protocol does not guarantee progress under failures.

Observed limitations:

no retry mechanism for lost messages
no timeout for stalled phases
no recovery path for crashed nodes

As a result:

the system may remain indefinitely in FREEZE or TRANSFER
availability is reduced during reconfiguration

This reflects a deliberate design choice:

The protocol prioritizes safety over availability.

- 13.5 Key Insight

Across all experiments:

The protocol achieves strong safety guarantees by enforcing strict phase ordering and acknowledgment requirements, but this comes at the cost of liveness under partial failures.

# 14. Client-Side Workload Observation

We extended the experiment runner to include a simple client workload during reconfiguration.

The client issues a small number of GET and PUT requests:

before reconfiguration
during FREEZE and TRANSFER
after reconfiguration completes

The client implements:

local shard routing hints
retry on:
reconfiguring
wrong_owner_or_missing_shard
stale_or_wrong_epoch
a single in-flight request constraint
- 14.1 Observed Behavior

In the successful reconfiguration scenario:

pre-reconfiguration requests succeed on the old owner (A)
requests during FREEZE and TRANSFER are rejected
after reconfiguration completes, some client requests still fail

This occurs even though:

the protocol has successfully transferred ownership to B
the system is in a correct STABLE state
- 14.2 Root Cause

The client maintains only a local routing hint and does not query the coordinator for updated ownership.

As a result:

after reassignment, the client may continue sending requests to the old owner (A)
the old owner has already cleaned up the shard
requests are rejected with wrong_owner_or_missing_shard

This leads to elevated counts of client-visible failures, even though the system is correct.

- 14.3 Interpretation

This observation highlights an important distinction:

Protocol correctness does not guarantee immediate client-perceived availability.

Specifically:

the protocol ensures safe ownership transfer
but client availability depends on timely routing updates
- 14.4 Design Limitation (Intentional)

The current client design intentionally:

does not query the coordinator
uses only local routing hints
supports only one in-flight request

These constraints were chosen to:

keep the simulation simple and deterministic
avoid extending the protocol with request identifiers or routing APIs
14.5 Conclusion

The client workload experiment confirms that:

the protocol behaves correctly under reconfiguration
temporary availability loss occurs during transition phases
stale client routing can prolong perceived unavailability

Client-side routing recovery is therefore:

an important but orthogonal concern to the shard reassignment protocol.

This is left as future work.