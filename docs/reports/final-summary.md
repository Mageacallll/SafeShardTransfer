# Final Summary — What We Built and What We Learned

## 1. What We Built

We implemented a **deterministic simulation of a shard reassignment protocol** for a distributed key-value system.

The system includes:
- a **coordinator** that manages shard ownership and drives reconfiguration
- **shard servers** that enforce correctness via epoch and state checks
- a **client** that issues requests under dynamic shard ownership
- a **deterministic discrete-event simulator** with fault injection and per-link unreliable network controls

Shard reassignment is modeled as a state machine:
STABLE → FREEZE → TRANSFER → ACTIVATE → CLEANUP → STABLE

The protocol guarantees **single-owner safety** through freezing, acknowledgment gating, and epoch-based validation.

---

## 2. Initial Design Commitments

We made several early decisions to make safety explicit and testable:

- **Epoch-based ownership** to reject stale requests  
- **Per-shard state machines** to isolate reconfiguration  
- **Coordinator-driven control plane** for deterministic transitions  
- **Strict phase ordering with acknowledgments**  
- **Server-side enforcement of correctness**  

These choices were motivated by a desire to build a system where **safety invariants are simple to state and verify**.

---

## 3. Where the System Pushed Back

While the protocol preserved safety, experiments revealed significant limitations.

### Liveness under failures

Progress depends on acknowledgments:

- missing `FreezeAck` → stuck in FREEZE  
- missing `TransferAck` → stuck in TRANSFER  

Under message loss or crashes:

- the original design stalled indefinitely in intermediate states  
- no server could serve the shard  
- the coordinator had no mechanism to recover  

This revealed a critical issue:

> **A protocol that is correct under ideal conditions can become unusable under realistic failures.**

We introduced timeout, retry, and abort mechanisms to address this, but this fundamentally changed the complexity of the system.

---

### Sensitivity to failure detection

False suspicion triggers unnecessary reassignment:

- shard is frozen  
- operations are rejected  
- availability drops  

Even when the original owner is healthy.

---

### Client-visible inconsistency

Even after successful reassignment:

- clients may send requests to the old owner  
- requests are rejected due to epoch mismatch  

> **Correct protocol execution does not guarantee immediate client correctness.**

---

## 4. Core Tradeoff

We made the following explicit design decision:

> **We deliberately sacrificed availability during reconfiguration to preserve single-owner safety.**

### Benefit
- strong, simple safety guarantees  
- no split-brain writes  
- clear correctness argument  

### Cost
- operations blocked during FREEZE  
- failed attempts may abort instead of completing reassignment  
- degraded client experience  
- delayed recovery  

This tradeoff is a direct consequence of requiring strict coordination before ownership changes.

---

## 5. Change in Understanding

Initially, we assumed:

> “Correct shard reassignment implies system correctness.”

However, our experiments showed:

- correct ownership transfer ≠ client-visible success  
- availability depends on routing and timing  
- progress depends on coordination reliability  

This led to a revised understanding:

> **Correctness is not only about protocol state, but also about how clients interact with the system.**

---

## 6. Depth vs Breadth

We chose to focus deeply on shard reassignment rather than building a full system.

We intentionally excluded:
- replication  
- coordinator replication/failover  
- routing services  
- persistent storage  

This allowed us to isolate the reconfiguration protocol and expose its **true tradeoffs**.

---

## 7. Recovery Complexity

We implemented bounded retry/timeout recovery to avoid indefinite coordinator-side stalls.

This improved convergence, but introduced new challenges:
- duplicate transfers  
- idempotency requirements (attempt IDs and duplicate handling)  
- abort-and-resync edge cases after crashes  

This suggests that:

> **Improving liveness shifts complexity into recovery and consistency logic, rather than eliminating it.**

---

## 8. What This Project Demonstrates

This project shows that:

- safety can be made simple with strict coordination  
- progress can be bounded with timeout/retry/abort, at the cost of more control-plane complexity  
- availability is a system-level property, not just a protocol property  
- distributed system design is fundamentally about tradeoffs  

---

## 9. Coordinator Failure Assumptions and Recovery Plan

We made an intentional architectural choice to keep a single coordinator in this project, which makes it a **single source of control-plane failure**.

Why we accepted this in scope:

- it keeps protocol reasoning and invariant validation tractable
- it isolates shard reassignment behavior without introducing consensus/election complexity
- it aligns with environments where the coordinator is treated as a mission-critical, human-supervised service

Operational assumption:

- the coordinator may fail, but has a **bounded recovery time** (restart/recover within an operator-defined window)
- under this assumption, in-flight attempts should converge to completion or safe abort once the coordinator is back

When this assumption is realistic:

- small clusters with explicit operational ownership
- controlled environments with active monitoring and on-call response
- deployments where brief control-plane outages are acceptable compared to protocol complexity overhead

To extend this project to enforce coordinator recovery:

1. Persist coordinator control state
- store shard metadata (`owner`, `epoch`, `state`, `target`, `attempt_id`)
- store in-flight phase state (`retry_count`, phase deadlines, timers)

2. Use atomic write to persistent storage
- write state snapshots before operations
- include monotonically increasing version numbers/checksums to detect torn/partial state

3. Recover deterministically on restart
- reload last committed snapshot
- replay/reschedule pending phase timers from absolute deadlines
- if deadlines are already exceeded, trigger safe abort and participant resync

4. Add testing
- measure crash-to-recovery convergence time in tests
- assert bounded recovery targets in failure-injection scenarios

This keeps the current design philosophy (safety-first, explicit coordination) while providing a concrete path from single-node coordinator reliability assumptions to stronger operational recovery guarantees.

---

## 10. Final Takeaway

This project is not about building a perfect system.

It is about demonstrating that:

> **When we design for safety under uncertainty, bounded convergence is possible, but availability and recovery simplicity still trade off against each other — and understanding that tension is the core learning outcome.**