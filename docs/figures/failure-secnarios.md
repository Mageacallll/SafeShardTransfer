# Failure Injection Scenarios

```mermaid
flowchart TD
    A[Baseline Reconfiguration] --> B[Freeze old owner]
    B --> C[Transfer shard state]
    C --> D[Activate new owner]
    D --> E[Cleanup old owner]

    B --> F[Scenario 1: old owner crashes during FREEZE]
    C --> G[Scenario 2: TransferShard message is dropped]
    C --> H[Scenario 3: new owner crashes before TransferAck]
    A --> I[Scenario 4: false suspicion triggers unnecessary reconfiguration]

    F --> J[Expected result: safety preserved, liveness stalls]
    G --> J
    H --> J
    I --> K[Expected result: safe completion with unnecessary availability cost]