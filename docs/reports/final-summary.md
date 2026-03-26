# Final Summary — What We Built and What We Learned

## 1. What We Built

We implemented a **deterministic simulation of a shard reassignment protocol** for a distributed key-value system.

The system includes:
- a **coordinator** that manages shard ownership and drives reconfiguration
- **shard servers** that enforce correctness via epoch and state checks
- a **client** that issues requests under dynamic shard ownership
- a **deterministic discrete-event simulator** with fault injection

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

### Liveness failures

Progress depends on acknowledgments:

- missing `FreezeAck` → stuck in FREEZE  
- missing `TransferAck` → stuck in TRANSFER  

Under message loss or crashes:

> **The system cannot make progress.**

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
- protocol stalls under failures  
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
- retry/recovery mechanisms  
- routing services  
- persistent storage  

This allowed us to isolate the reconfiguration protocol and expose its **true tradeoffs**.

---

## 7. Optimization vs Understanding

We considered improving liveness through retry mechanisms.

However, this introduces new challenges:
- duplicate transfers  
- idempotency requirements  
- ambiguous state transitions  

This suggests that:

> **Improving liveness shifts complexity into recovery and consistency logic, rather than eliminating it.**

---

## 8. What This Project Demonstrates

This project shows that:

- safety can be made simple with strict coordination  
- the same mechanisms make progress fragile  
- availability is a system-level property, not just a protocol property  
- distributed system design is fundamentally about tradeoffs  

---

## 9. Final Takeaway

This project is not about building a perfect system.

It is about demonstrating that:

> **When we design for safety under uncertainty, the system pushes back through reduced liveness and availability — and understanding that tension is the core learning outcome.**