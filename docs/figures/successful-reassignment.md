sequenceDiagram
    participant C as Coordinator
    participant A as Old Owner (A)
    participant B as New Owner (B)

    Note over A: STABLE (serving)

    C->>A: FreezeShard(epoch=1)
    A->>A: state = FREEZE
    A->>C: FreezeAck

    C->>A: BeginTransfer(target=B)
    A->>A: state = TRANSFER
    A->>B: TransferShard(data)

    B->>B: store pending data
    B->>C: TransferAck

    C->>C: owner = B, epoch = 2

    C->>B: ActivateShard(epoch=2)
    B->>B: state = STABLE (active owner)

    C->>A: CleanupShard(epoch=2)
    A->>A: delete shard

    Note over B: STABLE (serving)