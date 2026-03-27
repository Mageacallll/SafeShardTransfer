# Evaluation and Analysis

This document presents the evaluation of the freeze-based shard reassignment protocol under controlled failure scenarios.

The goal is to analyze:

- protocol correctness (safety)
- progress behavior (liveness)
- client-visible effects during reconfiguration

---

## 1. Evaluation Setup

All experiments are executed using a deterministic discrete-event simulator.

Each run includes:

- a coordinator
- two shard servers (A → B)
- a client workload (bounded and serialized)
- controlled fault injection

Assumptions:

- deterministic message delay (1 step)
- no replication (single active owner per shard)
- explicit protocol phases with acknowledgments

---

## 2. Metrics Collected

### Protocol Metrics

- `completed` — whether reassignment finished
- `stall_state` — phase where protocol stopped
- `final_owner`, `final_epoch`, `final_state`
- `freeze_duration`, `transfer_duration`

### Message Metrics

- `freeze_ack_count`
- `transfer_ack_count`
- `transfer_shard_sent_count`

### Client Metrics

- `client_reject_reconfiguring`
- `client_reject_missing_shard`
- `client_reject_epoch_mismatch`

---

## 3. Scenarios Evaluated

| Scenario | Description |
|---|---|
| false_suspicion_safe_reconfig | unnecessary but successful reassignment |
| drop_transfer_shard_message | transfer message is dropped |
| old_owner_crash_during_freeze | old owner crashes before freeze completes |
| new_owner_crash_before_transfer_ack | new owner crashes during transfer |

---

## 4. Results Summary

| Scenario | Completed | Stall State | Final Owner | Final Epoch | Final State | Freeze Duration | Transfer Duration | Transfer Ack |
|---|---|---|---|---|---|---|---|---|
| false_suspicion_safe_reconfig | Yes | - | B | 2 | STABLE | 2 | 3 | 1 |
| drop_transfer_shard_message | No | TRANSFER | A | 1 | TRANSFER | 2 | - | 0 |
| old_owner_crash_during_freeze | No | FREEZE | A | 1 | FREEZE | - | - | 0 |
| new_owner_crash_before_transfer_ack | No | TRANSFER | A | 1 | TRANSFER | 2 | - | 0 |

Results are generated directly from the experiment runner :contentReference[oaicite:1]{index=1}.

---

## 5. Safety Analysis

Across all scenarios:

- ownership never diverges
- no two servers simultaneously serve the same shard
- no incorrect activation occurs
- epoch values remain consistent

This confirms:

> The protocol enforces **single-owner safety under all tested failures**.

Key mechanisms:

- freezing the old owner before transfer
- activation only after transfer acknowledgment
- strict epoch validation

---

## 6. Liveness Analysis

The protocol does not guarantee progress under failures.

Observed behavior:

- FREEZE stall → old owner crash prevents acknowledgment
- TRANSFER stall → message loss or new owner crash prevents commit

This shows:

> Protocol progress depends on successful completion of each phase.

Without retries or timeouts:

- the system may remain indefinitely in `FREEZE` or `TRANSFER`

---

## 7. Phase-Level Insights

Failure scenarios reveal where the protocol is sensitive:

- **FREEZE phase**  
  → vulnerable to old owner failure  

- **TRANSFER phase**  
  → vulnerable to message loss and new owner failure  

This confirms:

> Each phase introduces a dependency that can block progress.

---

## 8. Client-Side Observations

Client workload was injected during all scenarios.

### Successful Reconfiguration

Even when the protocol completes:

- pre-reconfiguration request succeeds
- requests during FREEZE/TRANSFER are rejected
- many post-reconfiguration requests still fail

Observed metrics:
- `client_reject_reconfiguring = 2`
- `client_reject_missing_shard = 7` :contentReference[oaicite:2]{index=2}

Root cause:

- client continues sending requests to old owner (A)
- routing is not refreshed from the coordinator

---

### Failure Scenarios

In stalled scenarios:

- requests repeatedly receive `reconfiguring`
- retry attempts are exhausted
- operations ultimately fail

Example:

- `client_reject_reconfiguring = 9` in TRANSFER stall cases :contentReference[oaicite:3]{index=3}

---

## 9. Availability Interpretation

These results highlight:

> Client-perceived availability is not determined solely by protocol correctness.

Even when:

- the system is safe
- the protocol completes successfully

the client may still experience failures due to:

- stale routing information
- lack of coordinator-based route refresh

---

## 10. Safety vs Liveness vs Availability

The experiments reveal a three-way tradeoff:

### Safety
- always preserved
- no split-brain ownership

### Liveness
- not guaranteed
- stalls under partial failures

### Availability
- reduced during reconfiguration
- further impacted by stale client routing

---

## 11. Key Insight

Across all experiments:

> Strong safety guarantees are achieved through strict phase ordering and acknowledgment requirements, but this introduces sensitivity to failures and reduces both liveness and availability.

---

## 12. Limitations

Current evaluation does not include:

- retry/timeout mechanisms in the protocol
- coordinator-driven client routing
- request identifiers for concurrent clients
- large-scale or concurrent workloads

---

## 13. Conclusion

The evaluation demonstrates that:

- the protocol is robust in maintaining correctness
- but fragile in terms of progress under failures
- and limited in client-visible availability

This highlights the fundamental tradeoffs in shard reassignment under unreliable conditions.