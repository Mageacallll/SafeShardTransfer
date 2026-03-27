1. What is an epoch?

Answer

An epoch is a monotonically increasing version number associated with a shard’s ownership.

It is used to:

distinguish old vs new configurations
reject stale messages and requests
enforce that only the latest owner can serve the shard

When ownership changes, the coordinator increments the epoch. Servers and clients must use the latest epoch to perform operations.

Key property

A server only accepts requests whose epoch matches its current shard epoch.

2. Are states assigned per shard or per server?

Answer

States are assigned per shard, not per server.

Each shard independently progresses through the protocol states:

STABLE → FREEZE → TRANSFER → ACTIVATE → CLEANUP

A single server may host multiple shards, each in a different state at the same time.

Why this matters

enables fine-grained reconfiguration
avoids blocking unrelated shards
reflects how real distributed storage systems operate
3. What does the client do?

Answer

The client sends key-value requests (GET, PUT) to a shard server.

Each request includes:

shard ID
epoch
key/value
operation type

The server validates:

shard ownership
epoch correctness
shard state (STABLE required)

If any condition fails, the request is rejected.

Key idea

The client is not authoritative; the server enforces correctness.

4. What does the coordinator do?

Answer

The coordinator is the control-plane component that manages shard ownership and drives the reassignment protocol.

It is responsible for:

maintaining shard metadata (owner, epoch, state, target)
initiating reconfiguration
validating acknowledgments
advancing the state machine
committing ownership changes

Key idea

The coordinator decides what should happen; servers execute those decisions.

5. What does MetadataStore do?

Answer

MetadataStore stores the global metadata for each shard, including:

current owner
current epoch
protocol state
target node during reassignment

It acts as the coordinator’s source of truth.

Key idea

MetadataStore represents the global configuration state of the system.

6. Why do we need exactly these five states?

Answer

Each state represents a distinct correctness-critical phase:

STABLE: normal operation
FREEZE: stop new operations on the old owner
TRANSFER: move shard data to new owner
ACTIVATE: commit new ownership and increment epoch
CLEANUP: remove stale copy from old owner

Removing any state would merge phases that must remain separate for safety.

Adding more states would primarily support recovery or retry logic, which is not part of the current MVP.

7. Where does safety come from?

Answer

Safety (single-owner guarantee) is enforced by:

freezing the old owner before transfer
not activating the new owner until transfer is acknowledged
incrementing the epoch only at ownership commit
rejecting requests with mismatched epochs
rejecting requests during non-STABLE states

Key idea

There is no point in time where two servers are allowed to serve the same shard.

8. Why does liveness fail?

Answer

Liveness is limited because the protocol still requires explicit acknowledgments at each stage:

FreezeAck must be received to proceed
TransferAck must be received to commit ownership

If messages are dropped or nodes crash:

the coordinator retries while timeout budget remains
the attempt may abort safely if retries are exhausted or a participant crash is detected

Key idea

The protocol prioritizes safety, and now converges by either completion or safe abort rather than indefinite stall.