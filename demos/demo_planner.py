"""demo_planner.py — feed 3 requirements, watch the Planner emit 3 different graphs."""
from core.planner import plan

REQUIREMENTS = {
    "GREENFIELD": "Build a URL shortener with redirect and click counting",
    "BROWNFIELD": "Add click analytics to the existing shortener",
    "AMBIGUOUS":  "Make the shortener more reliable",
}

for label, req in REQUIREMENTS.items():
    graph, artifact = plan(req)
    print("=" * 66)
    print(f"{label}: \"{req}\"")
    print(f"  classified as: {artifact['classification']}")
    print(f"  task graph ({len(graph.all())} tasks):")
    for t in graph.all():
        deps = f" <- {t.depends_on}" if t.depends_on else ""
        print(f"    - {t.name}{deps}")
    print()
