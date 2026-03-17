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

Planned metrics include:

- freeze duration
- reassignment completion time
- rejected request counts

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