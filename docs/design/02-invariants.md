## Correctness Invariants
# Safety Invariants
S1. Unique Active Ownership
 For any shard s and epoch e, at most one process is authorized to serve operations for (s, e).
S2. Non-overlapping Ranges
 For any distinct shards s != t, [L_s, R_s) ∩ [L_t, R_t) = ∅.
S3. Ownership-Gated Execution (Epoch Fencing)
 A process may apply or serve operations for shard s only if:
it is owner(s) in metadata, and


request epoch matches epoch(s).


Stale epochs are rejected.
S4. Freeze Cutover Safety
 If state(s) ∈ {FREEZE, TRANSFER}, then no operations for shard s are applied by any process. (MVP blocks reads/writes during move.)
S5. Monotonic Epoch
 epoch(s) never decreases; each successful reconfiguration increments epoch.
# Liveness (Under Stabilizing Conditions)
L1. Reconfiguration Termination
 If failures stop and the metadata service and at least one eligible process remain reachable, any initiated reassignment eventually reaches STABLE with a valid owner.
L2. Shard Isolation
 Reconfiguring shard s does not prevent unrelated shards t != s from serving requests.

