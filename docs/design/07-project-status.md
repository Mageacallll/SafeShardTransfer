# Project Status — Freeze-Based Shard Reassignment Protocol

This document summarizes the current state of the capstone project implementation and evaluation.  
It serves as a checkpoint describing what has been implemented, what has been tested, and what remains to be explored.

The goal of this project is to design and experimentally evaluate a protocol for **safe shard reassignment in a sharded key-value system** under unreliable failure detection.

---

# 0. Update (March 26, 2026)

The implementation has moved beyond the initial safety-only checkpoint. The current code now includes:

- per-link unreliable network controls (drop, delay, reorder, duplicate, partition)
- coordinator timeout framework with exponential-backoff retries
- timeout/crash-triggered abort path returning metadata to `STABLE`
- crash notifications and recovery resynchronization (`on_node_crash` / `on_node_recover`)
- server-side client request deduplication via `request_id`
- harness failure scheduling and additional cascading failure scenarios

Current validation status:

- safety invariants remain intact under noisy network and crash scenarios
- liveness is improved: all reconfiguration attempts now converge by either completion or safe abort
- full automated test suite currently passes (`87 passed`)

This upgrade introduces a **safe convergence model**, where the system guarantees termination in a correct state even when progress is not possible.
Note: Sections below include historical observations from the earlier safety-only phase and should be interpreted as baseline results.

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
│ └── harness.py
│
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

- coordinator retries transfer up to retry budget
- transfer cannot complete
- coordinator aborts reconfiguration

Observation:

The protocol **preserves safety and converges via safe abort**, rather than stalling indefinitely.

---

## 6.2 Old Owner Crash During FREEZE

Fault:

old owner crashes before FreezeAck

Result:

- coordinator detects crash
- reconfiguration attempt is aborted
- metadata returns to `STABLE`

Observation:

The protocol avoids unsafe progress and **converges via fail-fast safe abort**.

---

## 6.3 New Owner Crash Before Transfer Acknowledgment

Fault:


new owner crashes before TransferAck


Result:

- coordinator detects failure and aborts the attempt
- metadata is restored to `STABLE`

Observation:

Safety preserved, and failed attempts converge by safe abort.

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

## 6.2 Old Owner Crash During FREEZE

Fault:

old owner crashes before FreezeAck

Result:

- coordinator detects crash
- reconfiguration attempt is aborted
- metadata returns to `STABLE`

Observation:

The protocol avoids unsafe progress and **converges via fail-fast safe abort**.

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

The following metrics have been implemented:

- freeze duration
- reassignment completion time
- transfer acknowledgment counts
- client rejection counts during reconfiguration

These metrics are collected through the experiment runner and summarized after each scenario execution.

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
- the core safety invariants hold under all tested failures
- bounded liveness has been achieved via timeout, retry, and abort mechanisms

The system has transitioned from:

- a safety-only design with possible stalls  
to:
- a **fault-aware convergent system**

The next stage focuses on:

- deeper evaluation and analysis
- understanding performance and availability tradeoffs

---

# 12. Repository State


All tests pass:

pytest → 87 passed in ~0.35s


The repository now contains:

- a working protocol implementation
- deterministic experiment infrastructure
- reproducible failure scenarios

This provides a stable foundation for deeper evaluation and further design exp

# 13. Experimental Results

We evaluated the protocol under seven representative scenarios using the deterministic simulator and fault injection framework.

## 13.1 Summary Table

| Scenario | Completed | Stall State | Final Owner | Final Epoch | Final State | Freeze Duration | Transfer Duration | Transfer Ack |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| false_suspicion_safe_reconfig | Yes | - | B | 2 | STABLE | 2 | 3 | 1 |
| drop_transfer_shard_message | No (aborted_safe) | - | A | 2 | STABLE | 2 | - | 0 |
| old_owner_crash_during_freeze | No (aborted_safe) | - | A | 2 | STABLE | - | - | 0 |
| new_owner_crash_before_transfer_ack | No (aborted_safe) | - | A | 2 | STABLE | 2 | - | 0 |
| cascading_drop_then_old_owner_crash | No (aborted_safe) | - | A | 2 | STABLE | 2 | - | 0 |
| partition_then_recover | Yes | - | B | 2 | STABLE | 10 | 3 | 1 |
| reorder_and_duplicate_transfer_path | Yes | - | B | 2 | STABLE | 2 | 3 | 1 |

Results are generated using the experiment runner and metrics collector.

---

## 13.2 Observations

### Successful Reconfiguration

In the absence of faults (false suspicion scenario):

- the protocol completes successfully
- ownership moves from A → B
- epoch increases from 1 → 2
- final state returns to `STABLE`

This demonstrates that correctness does not depend on accurate failure detection.

---

### Failure Scenarios

Across all failure scenarios:

- completion is possible under partition healing and link noise
- failed attempts are safely aborted when retries are exhausted or crashes are detected
- ownership remains with the original node (A) on abort paths
- epoch advances to abort epoch (2) while metadata returns to `STABLE`
- no incorrect activation occurs

This confirms that:

> The protocol consistently preserves single-owner safety even under failures.

---

### Phase Sensitivity

Failures affect different phases of the protocol:

- **FREEZE phase**
  - depends on old owner availability
  - crash leads to immediate abort

- **TRANSFER phase**
  - depends on reliable message delivery and new owner availability
  - message loss or crash leads to retry and eventual abort

This shows that:

> Each phase introduces a dependency that determines whether the protocol can complete or must abort.

---

### Message-Level Insights

From the metrics:

- `freeze_ack_count = 0` → no progress beyond FREEZE  
- `transfer_ack_count = 0` → no ownership commit  
- `transfer_ack_count = 1` → successful reconfiguration  

This indicates that:

> Acknowledgments are the key drivers of protocol progress.

---

## 13.3 Safety Analysis

The protocol enforces safety through:

- freezing the old owner before transfer
- delaying activation until transfer is acknowledged
- incrementing the epoch only upon ownership commit
- rejecting requests with mismatched epoch or non-`STABLE` state

As a result:

> There is no execution in which two servers simultaneously serve the same shard.

---

## 13.4 Liveness Analysis

The updated protocol guarantees bounded convergence under failures.

Observed behavior:

- retries and phase timeouts drive progress under transient failures
- partition scenarios recover and complete after connectivity is restored
- crash and persistent failure scenarios trigger safe abort

As a result:

- no scenario results in indefinite stalling
- every reconfiguration attempt converges to a terminal state

This establishes:

> The protocol guarantees convergence to either successful completion or safe abort.

---

## 13.5 Key Insight

Across all experiments:

> The protocol achieves strong safety guarantees while ensuring bounded convergence under unreliable conditions.

This is enabled by:

- strict phase ordering and acknowledgment requirements (safety)
- timeout and retry mechanisms (progress)
- safe abort as a fallback (convergence)

# 14. Client-Side Workload Observation

We extended the experiment runner to include a simple client workload during reconfiguration.

The client issues a small number of `GET` and `PUT` requests:
- before reconfiguration
- during `FREEZE` and `TRANSFER`
- after reconfiguration completes

---

## 14.1 Observed Behavior

In the successful reconfiguration scenario:

- pre-reconfiguration requests succeed on the old owner (A)
- requests during `FREEZE` and `TRANSFER` are rejected
- after reconfiguration completes, some client requests still fail

This occurs even though:
- the protocol has successfully transferred ownership to B
- the system is in a correct `STABLE` state

---

## 14.2 Root Cause

The client maintains only a local routing hint and does not query the coordinator for updated ownership.

As a result:

- after reassignment, the client may continue sending requests to the old owner (A)
- the old owner has already cleaned up the shard
- requests are rejected with `wrong_owner_or_missing_shard`

---

## 14.3 Interpretation

This highlights an important distinction:

> Protocol correctness does not guarantee immediate client-perceived availability.

---

## 14.4 Design Limitation

The current client:

- uses local routing hints only
- does not query the coordinator
- supports only one in-flight request

These constraints simplify the simulator but limit routing recovery.

---

## 14.5 Conclusion

Client-side routing recovery is an important but orthogonal concern to shard reassignment correctness, and is left as future work.