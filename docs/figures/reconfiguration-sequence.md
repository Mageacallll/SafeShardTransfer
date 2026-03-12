```markdown
## Reconfiguration Timeline

```mermaid
sequenceDiagram
    participant C as Coordinator
    participant A as Old Owner
    participant B as New Owner

    C->>A: FreezeShard
    A-->>C: FreezeAck

    A->>B: TransferShard(state)

    B-->>C: TransferAck

    C->>B: ActivateShard(epoch+1)

    C->>A: CleanupShard