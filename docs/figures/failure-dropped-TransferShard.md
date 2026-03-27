sequenceDiagram
    participant C as Coordinator
    participant A as Old Owner (A)
    participant B as New Owner (B)

    C->>A: FreezeShard
    A->>C: FreezeAck

    C->>A: BeginTransfer(target=B)
    A->>B: TransferShard (DROPPED)

    Note over B: never receives data

    B-->>C: (no TransferAck)

    Note over C: retries TRANSFER until timeout budget is exhausted
    Note over A: frozen, not serving
    Note over B: not activated

    C->>A: AbortReconfiguration(reason=timeout_exhausted_transfer)
    C->>B: AbortReconfiguration(reason=timeout_exhausted_transfer)
    Note over C: metadata returns to STABLE (owner remains A, epoch increments)
    Note over C: Safety preserved, outcome is safe abort (not indefinite stall)