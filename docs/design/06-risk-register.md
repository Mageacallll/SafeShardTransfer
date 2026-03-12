# 6. Risk Register

This section identifies potential technical and project risks that may arise during development of the shard reassignment protocol, along with mitigation strategies.

| Risk | Description | Impact | Mitigation |
|-----|-------------|--------|------------|
Protocol deadlock | Reconfiguration may stall if expected acknowledgments are never received due to message loss or process crash. | Reassignment may never complete. | Use coordinator timeouts and retry mechanisms to ensure progress. |
Incorrect epoch handling | Bugs in epoch fencing logic may allow stale servers to accept client requests. | Violates unique ownership safety invariant. | Enforce strict epoch checks in shard servers and verify invariants during simulation. |
Incomplete state transfer | Shard state may be partially transferred if a node crashes during migration. | Potential data inconsistency or shard unavailability. | Require transfer acknowledgments before activation and verify state completeness. |
Simulation complexity | Distributed system simulations can become difficult to debug due to many interacting components. | Slower development and debugging time. | Use structured logging, deterministic event scheduling, and replayable experiments. |
Network nondeterminism | Message delays or drops may lead to unexpected protocol behaviors. | Harder to reproduce failures. | Use deterministic simulation and scripted fault injection scenarios. |
Partner integration issues | Parallel development may lead to interface mismatches between modules. | Integration delays. | Clearly define shared interfaces in `src/common` and perform frequent integration tests. |
Schedule risk | Distributed systems debugging may take longer than expected. | Project milestones may slip. | Implement core protocol early and add failure injection incrementally. |