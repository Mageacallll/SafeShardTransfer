def merged_events(*nodes):
    """
    Merge and sort event logs from multiple nodes.

    Sorting key:
    1. logical time
    2. node id
    3. event name

    This makes event ordering deterministic for assertions.
    """
    events = []
    for node in nodes:
        events.extend(getattr(node, "event_log", []))

    return sorted(
        events,
        key=lambda e: (e["time"], e["node"], e.get("event", "")),
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