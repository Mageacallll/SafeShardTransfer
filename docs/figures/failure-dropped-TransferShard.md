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

    Note over C: stuck in TRANSFER
    Note over A: frozen, not serving
    Note over B: not activated

    Note over C: Safety preserved, liveness fails