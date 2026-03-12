# 5. Evaluation Plan

The goal of the evaluation is to validate the safety and behavior of the shard reassignment protocol under both normal and failure conditions.

The evaluation focuses on verifying invariants and measuring the operational impact of shard migration.

---

## 5.1 Evaluation Goals

The evaluation addresses two primary questions:

1. Does the protocol preserve safety invariants under failures?
2. What is the operational cost of shard reassignment?

Safety validation is performed through invariant checking during simulation runs. Performance is evaluated through latency and availability metrics.

---

## 5.2 Experimental Environment

The system is implemented as a **deterministic discrete-event simulator in Python**.

Components include:

- metadata coordinator
- shard servers
- simulated message-passing network
- deterministic event scheduler

The simulator allows controlled injection of network delays, message loss, and process crashes.

Because the simulator is deterministic, experiments can be replayed and analyzed consistently.

---

## 5.3 Metrics

The following metrics are collected during experiments.

### Reconfiguration Latency

Time from the initiation of shard reassignment to completion of the protocol.

Measured as:

initiate_reassign → STABLE

---

### Freeze Duration

The duration during which the shard is unavailable for client requests.

Measured as:

FREEZE → ACTIVATE

---

### Request Rejection Count

Number of client requests rejected during reassignment due to freeze or epoch mismatch.

---

### Recovery Time

Time required to complete reassignment after a failure is injected during the protocol.

---

## 5.4 Experimental Scenarios

Experiments evaluate the protocol under several conditions.

### Baseline Reassignment

Shard reassignment with no injected failures.

Purpose:

- measure normal protocol latency
- confirm correct protocol execution

---

### Network Delay

Artificial delays are introduced into message delivery.

Purpose:

- observe impact on reassignment completion time
- verify protocol correctness under asynchronous conditions

---

### Message Loss

Selected protocol messages are dropped.

Purpose:

- verify safety invariants remain intact
- observe whether reassignment eventually completes

---

### Node Crash

The old owner or new owner crashes during reassignment.

Purpose:

- evaluate protocol behavior when transfers are interrupted
- confirm that dual ownership never occurs

---

## 5.5 Invariant Verification

During simulation runs, the system continuously checks the safety invariants defined earlier.

Key invariants include:

- no two processes serve the same shard simultaneously
- shard operations are not applied during FREEZE or TRANSFER
- shard epochs increase monotonically

If any invariant violation occurs, the simulator records the failure and terminates the experiment.

This automated verification provides strong evidence that the protocol preserves correctness under the tested failure scenarios.