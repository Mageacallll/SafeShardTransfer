## System Model
# Processes
The system consists of a finite set of processes P.


Each process can host shard state and serve requests if it is authorized as the shard owner.


Failure model for processes:


Crash-stop failures: a process may halt permanently.


(Optional later) Crash-recovery: process may restart with empty volatile state but persistent local storage can remain. MVP can assume no recovery.


# Network
Asynchronous message-passing network:


Messages may be delayed, dropped, duplicated, and reordered.


Messages are not corrupted (no Byzantine behavior).


The protocol must not assume bounded delays for safety, only for liveness under stabilizing conditions.


# Failure Detection
Failure detection is advisory:


It may produce false suspicions (false positives).


It may miss failures temporarily (false negatives).


Correctness must not depend on failure detection accuracy. Failure detection only influences when reconfiguration is initiated.


# Metadata Service
MVP assumes a logically centralized metadata service storing shard configurations.


The metadata service is treated as the source of truth for:


ownership


epoch/version fencing


reconfiguration state machine


Coordinator crash recovery is out of scope for MVP unless explicitly implemented later.

## Data and Sharding Model
# Keys and Shards
The keyspace is ordered and partitioned into non-overlapping key ranges.


A shard s is defined by a half-open interval [L_s, R_s).


Shard boundaries are fixed in MVP.


# Ownership Metadata
For each shard s, metadata stores:
range(s) = [L_s, R_s)


epoch(s) — monotonically increasing integer


owner(s) — process currently authorized to serve s


state(s) — one of:


STABLE


FREEZE


TRANSFER


ACTIVATE


CLEANUP


target(s) — destination owner during reassignment (only in move states)


Clients route by shard range and include (shard_id, epoch) in requests.
