# 3. Protocol

## 3.1 Protocol Overview

Shard reassignment is implemented as a **configuration commit protocol** coordinated by the metadata service. The protocol ensures that ownership of a shard transitions safely from one process to another while preserving the safety invariants defined earlier.

The protocol is modeled as a state machine applied to each shard. A reassignment transitions through the following states:

STABLE → FREEZE → TRANSFER → ACTIVATE → CLEANUP → STABLE

Each state enforces restrictions on shard operations to guarantee that no two processes can serve the same shard concurrently.

During reassignment, client operations targeting the migrating shard are temporarily rejected to ensure a clean state transition.

The metadata coordinator orchestrates the reassignment process by updating shard metadata and issuing control messages to the involved shard servers.

---

## 3.2 Reconfiguration State Machine

Each shard is associated with a protocol state stored in metadata.

### STABLE

The shard operates normally.

Properties:

- `state(s) = STABLE`
- `owner(s)` serves requests
- `epoch(s)` represents the active configuration

Client requests are accepted and processed by the shard owner.

---

### FREEZE

The coordinator begins the reassignment process.

Actions:

- Metadata state transitions to `FREEZE`
- The current shard owner is instructed to freeze operations

Effects:

- The shard owner stops accepting read and write operations
- Client requests for the shard are rejected

Purpose:

The FREEZE phase guarantees that no new operations modify the shard state while reassignment is in progress.

---

### TRANSFER

The shard state is transferred from the old owner to the new owner.

Actions:

- The old owner sends the shard’s key-value state to the destination process
- The coordinator waits for confirmation that the new owner has received the state

The shard remains unavailable to clients during this phase.

---

### ACTIVATE

The coordinator commits the new configuration.

Actions:

- Metadata is updated:
  - `owner(s) ← new_owner`
  - `epoch(s) ← epoch(s) + 1`
- The new owner is instructed to activate the shard

The new owner can now begin serving requests for the shard.

---

### CLEANUP

The old owner discards its local shard state.

Actions:

- Coordinator instructs the previous owner to delete the shard data
- Metadata transitions back to `STABLE`

The reassignment process is now complete.

---

## 3.3 Protocol Messages

The protocol uses explicit control messages exchanged between the coordinator and shard servers.

| Message | Sender | Receiver | Purpose |
|-------|-------|-------|-------|
FreezeShard | Coordinator | Old Owner | request freeze of shard operations |
FreezeAck | Old Owner | Coordinator | confirm shard is frozen |
TransferShard | Old Owner | New Owner | transfer shard state |
TransferAck | New Owner | Coordinator | confirm state received |
ActivateShard | Coordinator | New Owner | activate shard with new epoch |
CleanupShard | Coordinator | Old Owner | delete old shard state |

These messages allow the coordinator to track progress and ensure that each stage completes before proceeding.

---

## 3.4 Client Request Handling

Clients route requests based on shard range and include the following metadata with each request:

- `shard_id`
- `epoch`

Shard servers enforce **epoch fencing**.

A request is processed only if:

- the server is the current owner of the shard
- the request epoch matches the shard’s current epoch
- the shard state is `STABLE`

Otherwise, the request is rejected.

This mechanism prevents stale or misrouted requests from being applied after a configuration change.

---

## 3.5 Safety Intuition

The protocol maintains the safety invariants described earlier.

Unique active ownership is guaranteed because:

- shard ownership changes only through coordinator-controlled metadata updates
- epochs increase monotonically
- servers reject requests with stale epochs

Additionally, operations are blocked during the FREEZE and TRANSFER phases, ensuring that shard state remains consistent while being migrated.