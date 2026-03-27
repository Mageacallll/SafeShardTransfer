
### Mermaid Architecture Diagram

# System Architecture

```mermaid
flowchart LR

    Client1[Client]
    Client2[Client]

    Coordinator[Metadata Coordinator]

    ServerA[Shard Server A]
    ServerB[Shard Server B]
    ServerC[Shard Server C]

    Client1 -->|request(key, epoch)| ServerA
    Client2 -->|request(key, epoch)| ServerB

    Coordinator -->|FreezeShard| ServerA
    Coordinator -->|ActivateShard| ServerB
    Coordinator -->|CleanupShard| ServerA

    ServerA -->|TransferShard| ServerB

    ServerA --> KV1[(Shard KV Store)]
    ServerB --> KV2[(Shard KV Store)]
    ServerC --> KV3[(Shard KV Store)]
```