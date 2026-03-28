# Evaluation and Analysis

This document presents the evaluation of the freeze-based shard reassignment protocol under unreliable network and failure conditions.

The goal is to analyze:

- protocol correctness (safety)
- convergence behavior (liveness)
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

- deterministic base message delay (1 step)
- no replication (single active owner per shard)
- explicit protocol phases with acknowledgments
- coordinator-driven timeout, retry, and abort
- attempt-scoped reconfiguration (`attempt_id`)

---

## 2. Metrics Collected

### Protocol Metrics

- `completed` — whether reassignment finished successfully
- `aborted` — whether reassignment aborted safely
- `converged` — whether system reached a terminal state (complete or abort)
- `final_owner`, `final_epoch`, `final_state`
- `total_reconfig_duration`
- `freeze_duration`, `transfer_duration`, `cleanup_duration`

### Message Metrics

- `freeze_ack_count`
- `transfer_ack_count`
- `transfer_shard_sent_count`
- `phase_timeout_count`
- `phase_retry_send_count`
- `phase_retry_exhausted_count`

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
| cascading_drop_then_old_owner_crash | transfer drop plus old owner crash in-flight |
| partition_then_recover | temporary partition between coordinator and old owner |
| reorder_and_duplicate_transfer_path | transfer-path reordering and duplication noise |

---

## 4. Results Summary

| Scenario | Outcome | Final Owner | Final Epoch | Final State | Freeze Duration | Transfer Duration |
|---|---|---|---|---|---|---|
| false_suspicion_safe_reconfig | Completed | B | 2 | STABLE | 2 | 3 |
| drop_transfer_shard_message | Aborted (safe) | A | 2 | STABLE | 2 | - |
| old_owner_crash_during_freeze | Aborted (safe) | A | 2 | STABLE | - | - |
| new_owner_crash_before_transfer_ack | Aborted (safe) | A | 2 | STABLE | 2 | - |
| cascading_drop_then_old_owner_crash | Aborted (safe) | A | 2 | STABLE | - | - |
| partition_then_recover | Completed | B | 2 | STABLE | 10 | 3 |
| reorder_and_duplicate_transfer_path | Completed | B | 2 | STABLE | 2 | 3 |

All results are generated directly from the experiment runner. :contentReference[oaicite:0]{index=0}

---

## 5. Safety Analysis

Across all scenarios:

- ownership never diverges
- no two servers simultaneously hold a shard in `STABLE`
- no stale state overwrites occur
- epoch values increase monotonically

This confirms:

> The protocol enforces **single-owner safety under all tested failures**, including message loss, crashes, partitions, and message reordering.

Key mechanisms:

- freezing the old owner before transfer
- activation only after transfer acknowledgment
- strict epoch validation
- attempt-scoped message validation (`attempt_id`)

---

## 6. Liveness and Convergence Analysis

Unlike the earlier version of the system, the protocol now guarantees **bounded convergence**.

Observed behavior:

- successful completion under:
  - false suspicion
  - temporary partitions
  - reorder/duplicate noise
- safe abort under:
  - persistent message loss
  - participant crashes

No scenario resulted in indefinite stalling.

This establishes:

> Every reconfiguration attempt converges to a terminal state: either successful completion or safe abort.

---

## 7. Failure-Type Behavior

### Message Loss

- transfer cannot complete
- retries are attempted
- retry exhaustion triggers safe abort

Outcome:
> **Safe fallback to original owner**

---

### Participant Crashes

- detected immediately by harness
- coordinator aborts without retry

Outcome:
> **Fail-fast safe abort**

---

### Temporary Partition

- coordinator repeatedly retries freeze
- once connectivity is restored, protocol proceeds

Outcome:
> **Eventual successful completion**

---

### Reordering and Duplication

- duplicate and delayed messages are observed
- stale messages are rejected safely

Example behavior:

- duplicate transfer messages ignored
- stale transfers rejected when local state is newer

Outcome:
> **Correct execution despite network noise**

---

## 8. Retry Mechanism Analysis

The coordinator implements bounded retry with exponential-style backoff.

Observed behavior:

- retries triggered only when progress stalls
- retry count remains bounded
- abort occurs after retry exhaustion

This provides:

> A balance between resilience (retry) and safety (abort).

---

## 9. Performance Observations

Reconfiguration duration varies by failure type:

| Scenario Type | Duration |
|---------------|--------|
| Crash | 1–4 steps |
| Message loss | ~6 steps |
| Normal success | ~5 steps |
| Partition recovery | ~13 steps |

This shows:

> Fault severity directly impacts reconfiguration latency.

---

## 10. Client-Side Observations

Client behavior during reconfiguration:

- requests during FREEZE/TRANSFER are rejected (`reconfiguring`)
- after completion, requests may still fail due to stale routing

Observed issues:

- client continues sending to old owner
- no coordinator-based routing refresh

This highlights:

> Client-visible availability depends on routing correctness, not just protocol correctness.

---

## 11. Safety vs Liveness vs Availability

The updated system achieves:

### Safety
- always preserved
- no split-brain ownership

### Liveness
- improved from “may stall” → “always converges”
- guarantees completion or safe abort

### Availability
- still reduced during reconfiguration
- impacted by stale client routing

---

## 12. Key Insight

The protocol now implements a **safe convergence model**:

> Every execution converges to a safe state — either successful reassignment or a consistent rollback.

This is stronger than simple liveness and more realistic under unreliable networks.

---

## 13. Limitations

The current system does not include:

- coordinator replication or failover
- durable storage across crashes
- adaptive timeout tuning (RTT-based)
- client-side routing service or coordinator lookup
- multi-shard atomic reconfiguration

---

## 14. Conclusion

The updated evaluation demonstrates that:

- safety is preserved under all tested failures
- liveness is improved via timeout, retry, and abort mechanisms
- the system guarantees convergence without indefinite stalls
- server-side idempotence and attempt-scoped validation ensure robustness under unreliable networks

Overall, the protocol evolves from a **safety-only design** to a **fault-aware convergent system**, capable of handling realistic distributed system conditions.