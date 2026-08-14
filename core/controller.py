"""
controller.py  —  the engine that walks the graph.

This is the state machine. It does NOT know anything about URL shorteners or
LLMs. It only knows how to drive a TaskGraph: repeatedly ask "what's ready?",
run those nodes through their gates, record what happened, and stop when done.

This first version handles the HAPPY PATH only (everything passes). We add
retry / rollback / replan in the next pass, on purpose.
"""

from core.event_log import EventLog, build_state, Event
from core.graph import TaskGraph, DONE, RUNNING, FAILED
from core.node import Node, GateError


class Controller:
    def __init__(self, graph: TaskGraph, nodes: dict[str, Node], run_id: str):
        self.graph = graph
        self.nodes = nodes
        self.run_id = run_id
        self.log = EventLog()

    def run(self) -> EventLog:
        self.log.append(Event(self.run_id, "controller", "run_started", {}))

        max_passes = 100      # safe-stop: never loop forever
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
                node = self.nodes[task.name]
                task.status = RUNNING
                state = build_state(self.log)
                try:
                    node.execute(state, self.log, self.run_id)
                    task.status = DONE
                except GateError:
                    task.status = FAILED
                    self.log.append(Event(self.run_id, "controller", "halted_on_failure",
                                          {"task": task.name}))
                    return self.log

        self.log.append(Event(self.run_id, "controller", "run_finished", {}))
        return self.log
