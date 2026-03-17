```mermaid
sequenceDiagram
    participant C as Coordinator
    participant A as Old Owner
    participant B as New Owner

    C->>A: FreezeShard
    Note over A: Scenario 1: crash here

    A-->>C: FreezeAck
    C->>A: BeginTransfer(target=B)

    A->>B: TransferShard
    Note over A,B: Scenario 2: drop TransferShard
    Note over B: Scenario 3: crash before TransferAck

    B-->>C: TransferAck
    C->>B: ActivateShard(epoch+1)
    C->>A: CleanupShard

    Note over C,A: Scenario 4: same sequence can be triggered by false suspicion