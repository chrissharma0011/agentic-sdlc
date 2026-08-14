"""
metrics.py  —  reliability metrics, computed by folding over the event log.

Nothing new is instrumented. Because every action is already an event with a
timestamp, each metric is just a different count or time-difference over the
log. This is the event-sourcing payoff.
"""

from datetime import datetime
from core.event_log import EventLog


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def compute_metrics(log: EventLog) -> dict:
    events = log.all()

    passes    = [e for e in events if e.kind == "node_passed"]
    fails     = [e for e in events if e.kind == "gate_failed"]
    retries   = [e for e in events if e.kind == "retry"]
    rollbacks = [e for e in events if e.kind == "rollback_occurred"]
    escalations = [e for e in events if e.kind == "awaiting_human"]

    total_attempts = len(passes) + len(fails)
    success_rate = (len(passes) / total_attempts) if total_attempts else 0.0

    recovery_times = []
    for f in fails:
        later_pass = next(
            (p for p in passes
             if p.stage == f.stage and _parse(p.ts) > _parse(f.ts)),
            None,
        )
        if later_pass:
            recovery_times.append((_parse(later_pass.ts) - _parse(f.ts)).total_seconds())
    mttr = (sum(recovery_times) / len(recovery_times)) if recovery_times else None

    started  = next((e for e in events if e.kind == "run_started"), None)
    finished = next((e for e in reversed(events)
                     if e.kind in ("run_finished", "human_halted", "human_approved_fix", "safe_stop")),
                    None)
    if started and finished:
        latency = (_parse(finished.ts) - _parse(started.ts)).total_seconds()
    else:
        latency = None

    return {
        "success_rate": round(success_rate, 3),
        "node_passes": len(passes),
        "node_failures": len(fails),
        "retries": len(retries),
        "rollbacks": len(rollbacks),
        "escalations": len(escalations),
        "mttr_seconds": round(mttr, 4) if mttr is not None else "n/a (no recovery)",
        "latency_seconds": round(latency, 4) if latency is not None else "n/a",
    }


def print_metrics(log: EventLog) -> None:
    m = compute_metrics(log)
    print("=== RELIABILITY METRICS (folded from the event log) ===")
    for k, v in m.items():
        print(f"  {k:18}: {v}")
