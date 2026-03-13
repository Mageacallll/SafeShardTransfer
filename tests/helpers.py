def merged_events(*nodes):
    events = []
    for node in nodes:
        events.extend(getattr(node, "event_log", []))
    return sorted(events, key=lambda e: (e["time"], e["node"], e["event"]))


def event_names(events):
    return [e["event"] for e in events]


def find_event(events, event_name):
    for e in events:
        if e["event"] == event_name:
            return e
    return None