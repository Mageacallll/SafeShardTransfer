## Protocol State Machine

```mermaid
stateDiagram-v2
    [*] --> STABLE

    STABLE --> FREEZE : initiate_reassign(shard)

    FREEZE --> TRANSFER : freeze_ack / timeout

    TRANSFER --> ACTIVATE : state_transfer_complete

    ACTIVATE --> CLEANUP : metadata_commit

    CLEANUP --> STABLE : old_owner_cleanup

    note right of FREEZE
        Client operations rejected
    end note

    note right of TRANSFER
        Shard state moved to new owner
    end note

    note right of ACTIVATE
        Epoch increment
        New owner begins serving
    end note