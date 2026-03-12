# 4. Failure Model

This section describes the failures considered in the system and how the protocol behaves under these conditions.

The goal is to ensure that safety invariants hold even when failures occur during shard reassignment.

---

## 4.1 Process Failures

Processes may experience **crash-stop failures**.

A crashed process:

- stops executing
- sends no further messages
- does not recover during the experiment (MVP assumption)

Implications:

- shard state hosted by a crashed owner may become temporarily unavailable
- ongoing shard transfers may be interrupted

The protocol must ensure that no other process begins serving the shard unless the configuration has been safely updated.

---

## 4.2 Network Failures

The system operates in an **asynchronous message-passing network**.

Messages may:

- be delayed
- be dropped
- be duplicated
- be reordered

Messages are not corrupted and there is no Byzantine behavior.

Safety must not depend on bounded network delays. The protocol must remain correct even if messages are delayed indefinitely.

---

## 4.3 Failure Detection

Failure detection is **advisory and imperfect**.

The failure detector may produce:

- false positives (suspecting a healthy node)
- false negatives (failing to detect a crashed node)

Failure detection is used only to trigger shard reassignment. Correctness of the protocol must not depend on accurate failure detection.

---

## 4.4 Failures During Reconfiguration

Several failure scenarios may occur during shard reassignment.

### Freeze Failure

The shard owner may crash before acknowledging the freeze request.

Result:

- the coordinator may timeout and continue the protocol
- the shard remains frozen because the crashed process cannot serve requests

---

### Transfer Failure

The old owner may crash during state transfer.

Result:

- the destination process may receive incomplete state
- the coordinator may abort or retry the reassignment

The system must ensure that the shard is not activated until a complete transfer has been confirmed.

---

### Activation Failure

The destination owner may crash after activation but before serving requests.

Result:

- the shard becomes temporarily unavailable
- the coordinator may initiate another reassignment

---

## 4.5 Safety vs Liveness

The protocol prioritizes **safety** over liveness.

Safety guarantees must hold even under arbitrary failures.

Liveness is guaranteed only under **stabilizing conditions**, meaning:

- failures eventually stop occurring
- the metadata coordinator remains reachable
- at least one process capable of hosting the shard is available
- the network eventually delivers messages

Under these conditions, any initiated shard reassignment will eventually complete and the shard will return to the `STABLE` state.