import itertools
import queue
from dataclasses import dataclass, field


_counter = itertools.count()


@dataclass(order=True)
class PrioritizedJob:
    sort_index: tuple = field(init=False)
    priority: int
    payload: dict = field(compare=False)

    def __post_init__(self):
        self.sort_index = (-self.priority, next(_counter))


class JobQueue:
    def __init__(self, maxsize: int = 1000):
        self._q = queue.PriorityQueue(maxsize=maxsize)

    def put(self, payload: dict):
        priority = int(payload.get("priority", 0))
        self._q.put(PrioritizedJob(priority=priority, payload=payload))

    def get(self, timeout: float = 1.0) -> dict:
        item = self._q.get(timeout=timeout)
        return item.payload

    def task_done(self) -> None:
        self._q.task_done()

    def qsize(self) -> int:
        return self._q.qsize()
