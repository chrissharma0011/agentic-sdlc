"""
controller.py  —  the engine that walks the graph, with governed recovery,
concurrent fork-join execution, and dynamic re-planning.

On a gate failure it:
    1. ROLLS BACK by appending a 'rollback_occurred' event (never deletes history).
    2. RETRIES up to a bounded budget, feeding the failure reason back in.
    3. RE-PLANS: on exhausted retries it can inject a repair task into the graph
       and loop back (dynamic graph mutation), bounded by a replan budget.
    4. ESCALATES to a human when retries AND replans are exhausted. On human
       approval it RESUMES (the loop is closed), on 'stop' it halts.

Execution is concurrent within a parallel_group (fork-join): tasks sharing a
group run on a thread pool and synchronize at their common dependant. The event
log is append-only, so concurrent appends are the only shared write.
"""

from concurrent.futures import ThreadPoolExecutor
from core.event_log import EventLog, build_state, Event
from core.graph import TaskGraph, Task, DONE, RUNNING, FAILED, PENDING
from core.node import Node, GateError
from core.replanner import build_escalation, present_and_await

RETRY_BUDGET = 3
REPLAN_BUDGET = 1   # how many times we may inject a repair task and loop back


class Controller:
    def __init__(self, graph: TaskGraph, nodes: dict[str, Node], run_id: str):
        self.graph = graph
        self.nodes = nodes
        self.run_id = run_id
        self.log = EventLog()
        self._replans_used = 0

    def _run_one(self, task) -> bool:
        """Run one task with adaptive retries. True if it passed."""
        node = self.nodes[task.name]
        last_reason = None
        for attempt in range(1, RETRY_BUDGET + 1):
            state = build_state(self.log)
            state["attempt"] = attempt
            state["last_failure"] = last_reason
            try:
                node.execute(state, self.log, self.run_id)
                return True
            except GateError as e:
                last_reason = e.reason
                self.log.append(Event(self.run_id, task.name, "rollback_occurred",
                                      {"rolled_back_node": task.name}))
                self.log.append(Event(self.run_id, "controller", "retry",
                                      {"task": task.name, "attempt": attempt,
                                       "gate": e.gate, "reason": e.reason}))
        return False

    def _inject_repair(self, failed_task) -> bool:
        """
        DYNAMIC RE-PLANNING: on a verify failure, mutate the graph — insert a
        'repair' task that regenerates the implementation using the failure
        reason, and re-route the failed task to depend on it, then re-run.
        Returns True if a repair was injected (bounded by REPLAN_BUDGET).
        """
        if self._replans_used >= REPLAN_BUDGET:
            return False
        if failed_task.name != "verify":
            return False  # we only auto-replan verification failures
        if "repair" in [t.name for t in self.graph.all()]:
            return False  # already repaired once

        self._replans_used += 1

        # Insert the repair node into the graph (real mutation).
        repair = Task("repair", depends_on=["architect"],
                      acceptance="repaired code addresses the failure",
                      rationale="dynamic re-plan: injected after verify failure")
        self.graph.add(repair)

        # Re-route: verify now depends on repair; reset verify + downstream to pending.
        verify = self.graph.get("verify")
        verify.depends_on = ["repair", "test"]
        for name in ("verify", "document", "release"):
            if name in [t.name for t in self.graph.all()]:
                self.graph.get(name).status = PENDING

        self.log.append(Event(self.run_id, "controller", "replan_injected",
                              {"injected": "repair", "reason": "verify failed after retries",
                               "rerouted": "verify now depends on repair"}))
        return True

    def _handle_failure(self, task) -> str:
        """A task exhausted retries. Try re-planning; else escalate to a human.
        Returns one of: 'replanned', 'resumed', 'halted'."""
        # 1. Try dynamic re-planning first (autonomous recovery).
        if self._inject_repair(task):
            return "replanned"

        # 2. Re-planning unavailable/exhausted -> escalate to a human.
        last_fail = self.log.latest("retry")
        reason = last_fail.payload.get("reason", "unknown") if last_fail else "unknown"
        gate = last_fail.payload.get("gate", "exit") if last_fail else "exit"

        package = build_escalation(task.name, gate, reason, RETRY_BUDGET, self.log)
        choice = present_and_await(package, self.log, self.run_id)

        if choice.strip().lower() == "stop":
            self.log.append(Event(self.run_id, "controller", "human_halted",
                                  {"task": task.name}))
            return "halted"

        # CLOSED LOOP: human approved -> record, reset the failed task to pending,
        # and RESUME (the caller's while-loop will re-run it).
        self.log.append(Event(self.run_id, "controller", "human_approved_fix",
                              {"task": task.name, "choice": choice}))
        task.status = PENDING
        return "resumed"

    def _execute_ready(self, ready) -> str | None:
        """
        Run all currently-ready tasks. Tasks sharing a parallel_group run
        concurrently (fork-join); others run sequentially. Returns a control
        signal ('halt') if a human halted, else None.
        """
        # Split into parallel groups and singletons.
        groups: dict[str, list] = {}
        singles = []
        for task in ready:
            if task.parallel_group:
                groups.setdefault(task.parallel_group, []).append(task)
            else:
                singles.append(task)

        # Run singletons first (deterministic), then each parallel group concurrently.
        batches = [[t] for t in singles] + list(groups.values())

        for batch in batches:
            for t in batch:
                t.status = RUNNING

            if len(batch) == 1:
                results = {batch[0].name: self._run_one(batch[0])}
            else:
                self.log.append(Event(self.run_id, "controller", "parallel_start",
                                      {"group": batch[0].parallel_group,
                                       "tasks": [t.name for t in batch]}))
                with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                    futures = {t.name: pool.submit(self._run_one, t) for t in batch}
                    results = {name: f.result() for name, f in futures.items()}
                self.log.append(Event(self.run_id, "controller", "parallel_join",
                                      {"group": batch[0].parallel_group}))

            for t in batch:
                if results[t.name]:
                    t.status = DONE
                else:
                    outcome = self._handle_failure(t)
                    if outcome == "halted":
                        return "halt"
                    # 'replanned' or 'resumed' -> leave status PENDING, loop re-runs it
        return None

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

            signal = self._execute_ready(ready)
            if signal == "halt":
                return self.log

        self.log.append(Event(self.run_id, "controller", "run_finished", {}))
        return self.log
