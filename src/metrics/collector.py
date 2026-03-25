def _first_event(events, event_name, shard_id):
    for e in events:
        if e.get("event") == event_name and e.get("shard_id") == shard_id:
            return e
    return None


def _count_events(events, event_name, shard_id=None):
    count = 0
    for e in events:
        if e.get("event") != event_name:
            continue
        if shard_id is not None and e.get("shard_id") != shard_id:
            continue
        count += 1
    return count


def summarize_run(coordinator, servers: list, shard_id: str, scenario_name: str) -> dict:
    coord_events = coordinator.event_log
    server_events = []
    for s in servers:
        server_events.extend(s.event_log)

    shard_meta = coordinator.store.get(shard_id)

    start = _first_event(coord_events, "reassign_start", shard_id)
    complete = _first_event(coord_events, "reassign_complete", shard_id)

    freeze_enter = _first_event(server_events, "freeze_enter", shard_id)
    transfer_out = _first_event(server_events, "transfer_out_start", shard_id)
    activate_complete = _first_event(server_events, "activate_complete", shard_id)
    cleanup_complete = _first_event(server_events, "cleanup_complete", shard_id)

    reconfig_start_time = start["time"] if start else None
    reconfig_end_time = complete["time"] if complete else None

    total_reconfig_duration = None
    if reconfig_start_time is not None and reconfig_end_time is not None:
        total_reconfig_duration = reconfig_end_time - reconfig_start_time

    freeze_duration = None
    if freeze_enter and transfer_out:
        freeze_duration = transfer_out["time"] - freeze_enter["time"]

    transfer_duration = None
    if transfer_out and activate_complete:
        transfer_duration = activate_complete["time"] - transfer_out["time"]

    cleanup_duration = None
    if activate_complete and cleanup_complete:
        cleanup_duration = cleanup_complete["time"] - activate_complete["time"]

    metrics = {
        "scenario_name": scenario_name,
        "shard_id": shard_id,
        "completed": complete is not None,
        "stalled": complete is None,
        "stall_state": None if complete else shard_meta["state"].value,
        "final_owner": shard_meta["owner"],
        "final_epoch": shard_meta["epoch"],
        "final_state": shard_meta["state"].value,
        "reconfig_start_time": reconfig_start_time,
        "reconfig_end_time": reconfig_end_time,
        "total_reconfig_duration": total_reconfig_duration,
        "freeze_duration": freeze_duration,
        "transfer_duration": transfer_duration,
        "cleanup_duration": cleanup_duration,
        "freeze_ack_count": _count_events(coord_events, "freeze_ack_accepted", shard_id),
        "transfer_ack_count": _count_events(coord_events, "transfer_ack_accepted", shard_id),
        "transfer_shard_sent_count": _count_events(server_events, "transfer_out_start", shard_id),
        "client_reject_reconfiguring": _count_events(server_events, "client_reject_reconfiguring", shard_id),
        "client_reject_epoch_mismatch": _count_events(server_events, "client_reject_epoch_mismatch", shard_id),
        "client_reject_missing_shard": _count_events(server_events, "client_reject_missing_shard", shard_id),
    }

    return metrics