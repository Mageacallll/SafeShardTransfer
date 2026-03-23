# Q&A — Understanding the Freeze-Based Shard Reassignment Project

This document answers common questions about the current capstone project design and implementation.

The goal is to explain not only **what the code does**, but also **why the system is structured this way**.

---

# 1. What is the purpose of our project, and why did we choose Python?

## Short answer

The purpose of this project is to study **how to safely move shard ownership** in a sharded key-value system when failures and unreliable failure detection are possible.

More concretely, we are building and evaluating a **freeze-based shard reassignment protocol** for a distributed key-value service.

The project is not mainly about building a high-performance database.  
It is about understanding a distributed systems question:

> How can we prevent two nodes from serving the same shard at the same time when ownership changes?

That is the core safety problem.

---

## Why shard reassignment matters

In a sharded system, different key ranges are assigned to different servers.  
Sometimes a shard needs to move because of:

- load balancing
- machine failure
- machine replacement
- reconfiguration

The dangerous part is that failure detectors are not perfect.  
A healthy node might be falsely suspected, or a failed node might not be detected immediately.

If reassignment is done carelessly, two servers might both believe they own the same shard.  
That can lead to:

- split-brain writes
- inconsistent data
- state divergence

Our project studies how to avoid that.

---

## Why we chose a freeze-based design

We chose a **freeze-based protocol** because it makes the safety story much clearer.

The main idea is:

- before moving a shard, stop serving operations on it
- transfer the shard state
- activate the new owner only after the transfer is acknowledged

So we deliberately **sacrifice availability during reassignment** in order to preserve **single-owner safety**.

This is the main tradeoff in the current design.

---

## Why we chose Python

We chose Python because this project is implemented as a **deterministic simulator**, not a production distributed system.

Python is a good choice here because:

- it is fast to prototype
- it makes simulator logic easy to write and inspect
- it supports clean testing with `pytest`
- it is good for structured logs and experiment tooling

Most importantly, Python lets us focus on:

- protocol reasoning
- fault injection
- invariants
- experiment reproducibility

instead of spending time on:

- sockets
- RPC frameworks
- concurrency bugs from real networking
- deployment complexity

So the short answer is:

> We chose Python because the project is about understanding and evaluating protocol behavior under failure, not about building a production-scale network service.

---

# 2. How does the state change along the workflow? Walk me through a successful reassignment example and a failure one.

## Successful reassignment example

Assume:

- shard `s1`
- old owner = `A`
- new owner = `B`
- current epoch = `1`

Initial metadata:

- `owner = A`
- `epoch = 1`
- `state = STABLE`

### Step 1 — STABLE

Shard `s1` is normally served by `A`.

Clients send requests to `A`, and `A` accepts them because:

- it has the shard
- the epoch matches
- the state is `STABLE`

---

### Step 2 — Coordinator starts reassignment

The coordinator decides to move the shard from `A` to `B`.

It updates metadata to:

- `state = FREEZE`
- `target = B`

and sends:

- `FreezeShard(s1, epoch=1)` to `A`

---

### Step 3 — FREEZE

Server `A` receives `FreezeShard`.

It changes its local shard state to `FREEZE` and stops serving client requests for this shard.

Then it sends:

- `FreezeAck(s1, epoch=1)` to the coordinator

At this point, the shard is temporarily unavailable.

---

### Step 4 — TRANSFER begins

The coordinator receives `FreezeAck`.

It updates metadata to:

- `state = TRANSFER`

and sends:

- `BeginTransfer(s1, epoch=1, target=B)` to `A`

Then `A` sends:

- `TransferShard(s1, epoch=1, data=...)` to `B`

---

### Step 5 — New owner receives shard

Server `B` receives `TransferShard`.

It stores the shard data in a **pending area**, not yet as an active shard.

Then it sends:

- `TransferAck(s1, epoch=1)` to the coordinator

At this moment, `B` still does **not** serve the shard yet.

---

### Step 6 — ACTIVATE

The coordinator receives `TransferAck`.

Now it knows that the shard data has arrived safely.

It commits the new configuration:

- `owner = B`
- `epoch = 2`
- `state = ACTIVATE`

and sends:

- `ActivateShard(s1, epoch=2)` to `B`

Server `B` now installs the shard as active with epoch `2`.

---

### Step 7 — CLEANUP

The coordinator sends:

- `CleanupShard(s1, epoch=2)` to `A`

Server `A` deletes its old local copy of the shard.

Coordinator then sets metadata to:

- `state = STABLE`
- `target = None`

Final result:

- `owner = B`
- `epoch = 2`
- `state = STABLE`

Now `B` is the only active owner.

---

## Failure example — dropped `TransferShard`

Again assume:

- old owner = `A`
- new owner = `B`
- shard `s1`
- epoch = `1`

### Steps 1–4 are the same

- coordinator starts reassignment
- `A` freezes
- `FreezeAck` arrives
- coordinator enters `TRANSFER`
- `A` sends `TransferShard` to `B`

But now suppose the network drops `TransferShard`.

---

### What happens next?

`B` never receives the shard.

So:

- `B` does not send `TransferAck`
- coordinator never activates `B`
- coordinator never bumps epoch
- coordinator never completes reassignment

Final metadata stays something like:

- `owner = A`
- `epoch = 1`
- `state = TRANSFER`
- `target = B`

Final server state:

- `A` still has the shard locally, but it is not fully back to normal
- `B` has nothing

---

## Why this failure is important

This shows:

- **safety is preserved** — `B` never becomes active incorrectly
- **liveness fails** — the system gets stuck in `TRANSFER`

That is a key lesson of the current protocol.

---

# 3. What is the specific meaning of each state? Why do we have exactly these states — not more, not fewer?

The current protocol uses five states:

- `STABLE`
- `FREEZE`
- `TRANSFER`
- `ACTIVATE`
- `CLEANUP`

These states correspond to five distinct phases of ownership change.

---

## STABLE

Meaning:

- the shard has one active owner
- clients may access the shard normally
- there is no reassignment currently happening

Why needed:

This is the normal resting state of the system.

Without `STABLE`, there would be no “normal operation” phase.

---

## FREEZE

Meaning:

- the old owner must stop serving requests
- no more reads/writes should be applied to the shard

Why needed:

This creates a clean cutover point.

Without `FREEZE`, the old owner might still process writes while transfer is happening, which could cause inconsistency.

So `FREEZE` exists to guarantee:

> no new updates are applied while ownership is changing

---

## TRANSFER

Meaning:

- the shard data is being moved from old owner to new owner
- new owner has not yet been authorized to serve it

Why needed:

Receiving data is different from being allowed to serve data.

Without `TRANSFER`, the protocol would blur together:

- data movement
- ownership commit

That would make correctness harder to reason about.

---

## ACTIVATE

Meaning:

- the new configuration has been committed
- the new owner is now allowed to install and serve the shard under the new epoch

Why needed:

This is the moment when ownership officially changes.

Without `ACTIVATE`, we would not have a clean point where:

- epoch increments
- new owner becomes authoritative

This is the key configuration-commit moment.

---

## CLEANUP

Meaning:

- the old owner deletes its old copy after cutover

Why needed:

This removes stale local state from the old owner.

Without `CLEANUP`, the old owner could keep an old shard copy forever.  
Even if it no longer serves it, that weakens the protocol story and complicates debugging and recovery.

---

## Why not fewer states?

If we used fewer states, we would mix together logically different phases.

Examples:

### If we removed `FREEZE`
Then the old owner might still process operations during transfer.

### If we removed `TRANSFER`
Then data movement and ownership commit would happen together, which is unsafe.

### If we removed `ACTIVATE`
Then there would be no explicit point where the new owner becomes authoritative.

### If we removed `CLEANUP`
Then stale copies remain on the old owner.

So each state exists because it marks a distinct safety-relevant step.

---

## Why not more states?

We could add more states in a more advanced protocol, such as:

- `ABORT`
- `RETRY`
- `RECOVERY`
- `WAIT_FOR_ACK`

But for the MVP, the current five states are enough to model the essential reassignment lifecycle.

So the answer is:

> We have exactly these five states because each one represents a distinct correctness-critical phase, and the MVP does not yet implement more advanced recovery logic.

---

# 4. It seems we have four players: coordinator, client, server, and store. What is the function of each? Does state change exist only in coordinator? Is the coordinator one of the servers?

Yes, you can think of the current system as having four main roles.

---

## Coordinator

The coordinator is the **control-plane decision maker**.

It is responsible for:

- deciding when reassignment starts
- maintaining shard metadata
- tracking protocol state
- bumping the epoch
- sending control messages

Examples of coordinator-controlled changes:

- `STABLE -> FREEZE`
- `FREEZE -> TRANSFER`
- `owner = A -> owner = B`
- `epoch = 1 -> epoch = 2`

So the coordinator controls the **global reconfiguration state**.

---

## Client

The client is the actor that sends requests like:

- GET
- PUT

Its role is not to manage ownership.  
Its role is to exercise the system from the outside.

The client includes:

- shard id
- epoch
- operation
- key/value

in its request.

This allows the server to reject stale or misrouted requests.

---

## Shard Server

A shard server is the **data-plane host**.

It stores actual shard data and handles:

- client operations
- freeze behavior
- sending transfer data
- receiving transfer data
- activation
- cleanup

The shard server has **local shard state**, which is not the same as coordinator metadata.

For example, a server may locally know:

- this shard is in `FREEZE`
- this shard is in `TRANSFER`
- this shard data is pending activation

So state does **not** exist only in the coordinator.

There are two kinds of state:

### Global metadata state
Owned by the coordinator.

### Local operational state
Owned by each shard server.

That distinction is important.

---

## Store

“Store” in this project means the metadata store used by the coordinator.

It is not a separate distributed machine right now.  
It is basically the coordinator’s persistent/control data structure.

It stores things like:

- shard owner
- epoch
- protocol state
- target

So in the MVP, the store is a **logical component**, not necessarily an independent running process.

---

## Is the coordinator one of the servers?

In the current simulator design, **no**.

We model the coordinator as a separate control-plane process from shard servers.

Why?

Because this separation makes the system easier to reason about:

- coordinator decides ownership and state transitions
- servers execute those decisions

In a real system, the coordinator could be implemented:

- as a dedicated service
- as part of a metadata subsystem
- or even colocated with one of the nodes

But in this project, separating them is a deliberate simplification for clarity.

So the answer is:

> The coordinator is not one of the shard servers in the current model. It is a separate control-plane authority.

---

# 5. In the type folder, what is the meaning and usage of Basic Types?

The “Basic Types” section in `types.py` defines shared aliases such as:

- `ShardId`
- `NodeId`
- `Epoch`
- `Key`
- `Value`

Example:

```python
ShardId = str
NodeId = str
Epoch = int
Key = str
Value = Any