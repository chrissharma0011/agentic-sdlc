"""
controller.py  —  the engine that walks the graph, with governed recovery.

On a gate failure it:
    1. ROLLS BACK by appending a 'rollback_occurred' event (NOT by deleting
       history). build_state() then ignores the failed attempt's artifact.
    2. RETRIES up to a bounded budget (3), feeding the last failure reason back
       in so the node can adapt instead of repeating the same failure.
    3. ESCALATES to a human when the budget is exhausted (human owns the call).
"""

from core.event_log import EventLog, build_state, Event
from core.graph import TaskGraph, DONE, RUNNING, FAILED
from core.node import Node, GateError
from core.replanner import build_escalation, present_and_await

RETRY_BUDGET = 3


class Controller:
    def __init__(self, graph: TaskGraph, nodes: dict[str, Node], run_id: str):
        self.graph = graph
        self.nodes = nodes
        self.run_id = run_id
        self.log = EventLog()

    def _run_one(self, task) -> bool:
        """
        Run one task with adaptive retries. Returns True if it passed,
        False if the budget was exhausted (caller escalates).
        """
        node = self.nodes[task.name]
        last_reason = None      # what went wrong last time (fed back on retry)

        for attempt in range(1, RETRY_BUDGET + 1):
            state = build_state(self.log)          # rolled-back artifacts already excluded
            state["attempt"] = attempt             # node can see which try this is
            state["last_failure"] = last_reason    # ...and why it failed last time (fix 2)

            try:
                node.execute(state, self.log, self.run_id)
                return True
            except GateError as e:
                last_reason = e.reason
                # Rollback WITHOUT deleting history: mark the attempt invalid.
                self.log.append(Event(self.run_id, task.name, "rollback_occurred",
                                      {"rolled_back_node": task.name}))
                self.log.append(Event(self.run_id, "controller", "retry",
                                      {"task": task.name, "attempt": attempt,
                                       "gate": e.gate, "reason": e.reason}))
        return False

    def run(self) -> EventLog:
        self.log.append(Event(self.run_id, "controller", "run_started", {}))

        max_passes = 100
        passes = 0

        while not self.graph.is_complete():
            passes += 1
            if passes > max_passes:
                self.log.append(Event(self.run_id, "controller", "safe_stop",
                                      {"reason": "max passes exceeded"}))
                break

            ready = self.graph.ready_tasks()
            if not ready:
                self.log.append(Event(self.run_id, "controller", "safe_stop",
                                      {"reason": "no ready tasks but not complete"}))
                break

            for task in ready:
                task.status = RUNNING
                passed = self._run_one(task)

                if passed:
                    task.status = DONE
                else:
                    task.status = FAILED
                    last_fail = self.log.latest("retry")
                    reason = last_fail.payload.get("reason", "unknown") if last_fail else "unknown"
                    gate = last_fail.payload.get("gate", "exit") if last_fail else "exit"

                    package = build_escalation(task.name, gate, reason,
                                               RETRY_BUDGET, self.log)
                    choice = present_and_await(package, self.log, self.run_id)

                    if choice.strip().lower() == "stop":
                        self.log.append(Event(self.run_id, "controller", "human_halted",
                                              {"task": task.name}))
                    else:
                        self.log.append(Event(self.run_id, "controller", "human_approved_fix",
                                              {"task": task.name, "choice": choice}))
                    return self.log

        self.log.append(Event(self.run_id, "controller", "run_finished", {}))
        return self.log
