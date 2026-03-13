"""
Deterministic discrete-event loop.

Events are executed in increasing logical time order.
If multiple events have the same logical timestamp, insertion order breaks ties.
"""

import heapq
import itertools
from typing import Callable, Any


class EventLoop:
    def __init__(self):
        self.time = 0
        self._queue = []
        self._counter = itertools.count()

    def schedule(self, delay: int, callback: Callable[..., Any], *args):
        if delay < 0:
            raise ValueError("delay must be >= 0")

        event_time = self.time + delay
        event_id = next(self._counter)
        heapq.heappush(self._queue, (event_time, event_id, callback, args))

    def run(self, max_steps: int = 100_000):
        steps = 0

        while self._queue and steps < max_steps:
            event_time, _, callback, args = heapq.heappop(self._queue)
            self.time = event_time
            callback(*args)
            steps += 1

        if steps >= max_steps:
            raise RuntimeError("EventLoop exceeded max_steps; possible infinite event generation.")

    def is_empty(self) -> bool:
        return len(self._queue) == 0