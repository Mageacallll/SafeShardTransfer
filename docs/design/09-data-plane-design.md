# Data Plane Implementation and Design Decisions

## 1. Overview

This document describes the data-plane implementation of the freeze-based shard reassignment protocol.

The data plane is responsible for:
- shard server behavior and local state management
- execution of state transfer between servers
- client request handling and retry behavior

This is complementary to the control plane, which:
- maintains global metadata
- coordinates shard reassignment
- drives protocol state transitions

---

## 2. Shard Server Design

Each shard server maintains local shard state in the form:

- `epoch`: version number of the shard
- `state`: one of `{STABLE, FREEZE, TRANSFER, ACTIVATE, CLEANUP}`
- `data`: key-value storage for the shard

In addition, the server maintains:
- `pending_incoming`: temporary storage for shards received during transfer but not yet activated

### Request Handling

A client request (`GET` or `PUT`) is accepted only if:
- the shard exists locally
- the request epoch matches the shard epoch
- the shard is in `STABLE` state

Otherwise, the server rejects the request with one of:
- `wrong_owner_or_missing_shard`
- `stale_or_wrong_epoch`
- `reconfiguring`

This ensures that:
> Only the current, active owner of a shard can serve requests.

---

### State Transitions

The shard server reacts to coordinator messages:

- `FREEZE`  
  → stops serving client requests

- `TRANSFER`  
  → sends shard state to the target server using a snapshot

- `ACTIVATE`  
  → installs transferred state and becomes the new owner

- `CLEANUP`  
  → deletes stale shard state from the old owner

During transfer:
- data is first stored in `pending_incoming`
- only becomes active upon `ACTIVATE`

This guarantees that:
> Ownership is only assumed after a full transfer is acknowledged.

---

## 3. Client Design

The client is responsible for:
- issuing `GET` / `PUT` requests
- selecting a target server
- retrying requests under reconfiguration-related failures

### Routing Model

The client maintains a simple routing hint:
shard_id → server_id


If no route is known, it falls back to a default server.

This routing is:
- local
- heuristic-based
- not coordinator-driven

---

### Retry Behavior

The client retries requests when receiving:

- `reconfiguring`
- `wrong_owner_or_missing_shard`
- `stale_or_wrong_epoch`

On retry:
- the route is invalidated
- the request is resent after a fixed simulator delay

Retries are limited by a maximum retry count.

---

### Single In-Flight Request Constraint

The client supports only **one in-flight request at a time**.

This is a deliberate design decision.

Reason:
- protocol messages do not include request IDs
- replies cannot be safely matched to multiple outstanding requests
- allowing concurrency would introduce ambiguity and unsafe behavior

Thus:
> The client enforces sequential request execution to guarantee correctness.

---

## 4. Data Plane Testing

### Server Behavior Tests

The server is tested for:

- rejection of invalid client requests:
  - missing shard
  - epoch mismatch
  - non-`STABLE` state

- correct protocol transitions:
  - `FREEZE`
  - `TRANSFER`
  - `ACTIVATE`
  - `CLEANUP`

- correct handling of:
  - transfer-in state
  - activation preconditions
  - cleanup correctness

---

### Client Behavior Tests

The client is tested for:

- successful request execution
- retry behavior under failure
- route invalidation
- enforcement of single in-flight request
- handling of:
  - orphan replies
  - replies from incorrect sources

---

## 5. Design Tradeoffs and Compromises

### 5.1 No Request IDs

The protocol does not include request identifiers.

Implication:
- client cannot safely support multiple concurrent requests

Decision:
- restrict client to one in-flight request

---

### 5.2 Simplified Routing

The client does not query the coordinator for routing.

Instead:
- it uses a local routing hint
- falls back to a default server

Reason:
- sufficient for simulation and evaluation
- avoids introducing additional control-plane complexity

---

### 5.3 Fixed Retry Policy

Retry uses:
- fixed delay (simulator ticks)
- bounded retry count

Not implemented:
- exponential backoff
- jitter
- adaptive retry

Reason:
- not required for correctness evaluation
- keeps simulator deterministic

---

### 5.4 Minimal Storage Abstraction

Shard data is currently stored as in-memory key-value dictionaries.

A separate `ShardStorage` abstraction exists but is not fully integrated.

Reason:
- current structure is sufficient for protocol evaluation
- full abstraction can be introduced as future refactor

---

## 6. Future Work

Potential improvements include:

- adding request IDs for safe concurrent client requests
- integrating coordinator-driven routing
- implementing richer retry/backoff strategies
- fully adopting `ShardStorage` abstraction
- injecting client workloads during reconfiguration to evaluate availability

---

### Note:
It is also worth mentioning that client workload injection in the simulator is serialized because the current protocol does not attach request IDs to replies, so the client deliberately avoids concurrent outstanding requests.

## 7. Summary

The current data-plane implementation prioritizes:

- correctness
- simplicity
- deterministic behavior in simulation

While it omits more advanced features, it provides a clean and safe foundation for evaluating the shard reassignment protocol.

The design explicitly favors:

> safety and clarity over completeness and performance.

### Client-side Availability Note

We also injected a small client workload during reconfiguration to observe user-visible effects.

These exploratory runs showed that even when the protocol successfully completed, client-observed availability could remain poor if the client continued using stale routing information. In particular, post-reconfiguration requests could still be sent to the old owner and be rejected as missing-shard requests.

This does not indicate a protocol safety failure. Instead, it reflects a limitation of the current client model, which uses only local routing hints and does not query coordinator metadata for route refresh.

For this project, client routing recovery is treated as secondary to the core shard reassignment mechanism and is left as future work.