"""
graph.py  —  the task DAG (the dependency graph the assignment mandates).

Tasks now carry an `acceptance` criterion: the Planner defines what "done"
means for each task, and the node's exit gate reads it from here. That is the
spec-as-code idea — the plan defines the contract, the gate enforces it.
"""

from dataclasses import dataclass, field

PENDING = "pending"
READY = "ready"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass
class Task:
    """One node in the DAG."""
    name: str
    depends_on: list[str] = field(default_factory=list)
    status: str = PENDING
    parallel_group: str | None = None
    acceptance: str = ""          # what "done" means for this task (spec-as-code)
    rationale: str = ""           # why the Planner included this task (lineage)


class TaskGraph:
    """Holds the tasks and answers 'what can run?' and 'are we done?'."""

    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        self._tasks[task.name] = task

    def get(self, name: str) -> Task:
        return self._tasks[name]

    def all(self) -> list[Task]:
        return list(self._tasks.values())

    def _deps_done(self, task: Task) -> bool:
        for dep_name in task.depends_on:
            if self._tasks[dep_name].status != DONE:
                return False
        return True

    def ready_tasks(self) -> list[Task]:
        ready = []
        for task in self._tasks.values():
            if task.status == PENDING and self._deps_done(task):
                ready.append(task)
        return ready

    def is_complete(self) -> bool:
        for task in self._tasks.values():
            if task.status in (PENDING, READY, RUNNING):
                return False
        return True

    def has_failure(self) -> bool:
        return any(t.status == FAILED for t in self._tasks.values())
