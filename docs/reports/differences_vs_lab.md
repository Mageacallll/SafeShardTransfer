# Differences vs DS Lab 5

This project overlaps conceptually with Lab 5 (Sharded Key/Value Service), but extends beyond the lab starting point in both **system model** and **evaluation focus**.

The goal of this section is to clarify what is **new in this project**, beyond reproducing the lab design.

---

## 1. Reconfiguration as an Explicit Protocol

In Lab 5, shard reassignment is implemented implicitly by inserting configuration changes into the Paxos log of each replica group. Client operations and configuration updates are totally ordered, ensuring consistency.

In contrast, this project models shard reassignment explicitly as a **configuration commit protocol** with well-defined phases:

STABLE → FREEZE → TRANSFER → ACTIVATE → CLEANUP

Key differences:

- reconfiguration is modeled as a multi-stage protocol rather than a log entry
- shard operations are explicitly **blocked during FREEZE and TRANSFER**
- correctness is enforced through **state transitions and acknowledgments**

This makes the protocol easier to reason about in isolation and enables targeted evaluation of each stage.

---

## 2. Different Failure Model

Lab 5 assumes that shard transfer occurs between **available and cooperating replica groups**.

This project instead focuses on **unreliable failure detection**, where:

- nodes may crash
- messages may be dropped or delayed
- nodes may be falsely suspected

The protocol must maintain safety and convergence even when:

- the old owner cannot respond
- the new owner crashes mid-transfer
- communication is unreliable

To address this, the system introduces:

- timeout-driven retries
- bounded retry with safe abort
- attempt-scoped reconfiguration (`attempt_id`)

This shifts the focus from correctness under normal operation to **robustness and convergence under partial failures**.

---

## 3. Removal of Replication (Scope Isolation)

Lab 5 uses Paxos to replicate operations within each replica group.

In this project, we intentionally remove replication and assume:

> a single active owner per shard

This is a deliberate simplification to isolate the core problem:

- correctness of shard reassignment
- prevention of split-brain ownership

By removing consensus, we can:
- focus on reconfiguration correctness
- reason about ownership transitions directly
- evaluate safety/liveness tradeoffs more clearly

---

## 4. Deterministic Simulation Instead of Distributed Execution

Lab 5 is implemented as a distributed system with real RPC communication.

This project instead uses a **deterministic discrete-event simulator**, which provides:

- logical time control
- deterministic message delivery
- reproducible fault injection

This enables:

- precise reasoning about protocol behavior
- controlled adversarial testing
- reproducible experiments

---

## 5. Adversarial Evaluation and Metrics

Lab 5 primarily evaluates correctness through functional testing.

This project extends evaluation significantly by introducing:

### Failure Injection Scenarios

- dropped transfer messages
- old owner crash during FREEZE
- new owner crash before acknowledgment
- false suspicion of healthy nodes

### Metrics

- reconfiguration completion time
- freeze duration
- transfer acknowledgment counts
- client-visible request rejection counts

### Observations

We explicitly analyze:

- safety vs liveness tradeoffs
- protocol convergence behavior (completion vs safe abort)
- impact of reconfiguration on client-perceived availability

---

## 6. Key Contribution Beyond the Lab

The main contribution of this project is not just implementing shard reassignment, but:

> systematically analyzing its behavior under failures.

In particular, we show that:

- the protocol consistently preserves **single-owner safety**
- the system guarantees **bounded convergence** under failures:
  - either successful completion, or
  - safe abort back to a consistent `STABLE` state
- retry and timeout mechanisms enable recovery from transient failures
- server-side idempotence and attempt-scoped validation ensure correctness under duplicated, delayed, and reordered messages

These insights go beyond the lab’s functional requirements and provide a deeper understanding of how shard reassignment behaves under realistic unreliable conditions.
This effectively transforms the protocol from a safety-only design into a **fault-aware convergent system**, which is more aligned with real-world distributed system requirements.

---

## 7. Summary

While inspired by Lab 5, this project differs in:

- modeling reconfiguration as an explicit protocol
- operating under a more adversarial failure model
- removing replication to isolate the problem
- using deterministic simulation for evaluation
- emphasizing **analysis, convergence behavior, and failure handling** over implementation alone

This ensures that the project goes beyond reproducing the lab and instead contributes **meaningful system-level insights**.