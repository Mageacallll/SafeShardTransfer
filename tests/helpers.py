def merged_events(*nodes):
    """
    Merge and sort event logs from multiple nodes.

    Sorting key:
    1. logical time
    2. node id
    3. per-node emission sequence

    This preserves same-time event order within a node.
    """
    events = []
    for node in nodes:
        events.extend(getattr(node, "event_log", []))

    return sorted(
        events,
        key=lambda e: (e["time"], e["node"], e.get("seq", 0)),
    )


def event_names(events):
    """
    Extract just the event names from a merged event list.
    """
    return [e["event"] for e in events]


def find_event(events, event_name):
    """
    Return the first event with the given name, or None if not found.
    """
    for event in events:
        if event.get("event") == event_name:
            return event
    return None


def find_all_events(events, event_name):
    """
    Return all events with the given name.
    """
    return [event for event in events if event.get("event") == event_name]

def stable_holders(shard_id, *servers):
    holders = []
    for server in servers:
        shard = getattr(server, "shards", {}).get(shard_id)
        if shard is not None and shard["state"].value == "STABLE":
            holders.append(server.node_id)
    return holders


def assert_at_most_one_stable_holder(shard_id, *servers):
    holders = stable_holders(shard_id, *servers)
    assert len(holders) <= 1, f"Expected at most one stable holder, got {holders}"


def has_event(node, event_name):
    return any(e.get("event") == event_name for e in getattr(node, "event_log", []))