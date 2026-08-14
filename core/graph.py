"""
graph.py  —  the task DAG (the dependency graph the assignment mandates).

A DAG = Directed Acyclic Graph: tasks with dependencies, no cycles.
This file does NOT run any tasks. It only holds the structure and answers
two questions the controller will ask:
    1. which tasks are READY to run right now? (all their deps are done)
    2. are we DONE? (every task finished)

Key point: this graph is DATA. The Planner will build one of these from a
requirement, and the Replanner can add tasks to it mid-run.
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


if __name__ == "__main__":
    g = TaskGraph()
    g.add(Task("requirement"))
    g.add(Task("plan", depends_on=["requirement"]))
    g.add(Task("architect", depends_on=["plan"]))
    g.add(Task("implement", depends_on=["architect"], parallel_group="build"))
    g.add(Task("test", depends_on=["architect"], parallel_group="build"))
    g.add(Task("verify", depends_on=["implement", "test"]))
    g.add(Task("document", depends_on=["verify"]))
    g.add(Task("release", depends_on=["document"]))

    print("Ready at the start (only 'requirement' has no deps):")
    print("  ", [t.name for t in g.ready_tasks()])

    for name in ["requirement", "plan", "architect"]:
        g.get(name).status = DONE

    print("Ready after architect is done (parallel pair should both appear):")
    print("  ", [t.name for t in g.ready_tasks()])

    print("Is the graph complete?", g.is_complete())
