from __future__ import annotations

from src.vyu.evaluation.comparison import WorkflowComparison


def render_adoption_report(comparison: WorkflowComparison) -> str:
    lines = [
        "# RAG-Gym-Style Workflow Adoption Report",
        "",
        "| Workflow | Quality | Cost Units | Latency Units | Auditability | Trajectories |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for workflow, metrics in comparison.workflow_metrics.items():
        lines.append(
            "| "
            f"{workflow} | "
            f"{metrics.quality:.2f} | "
            f"{metrics.estimated_cost_units} | "
            f"{metrics.estimated_latency_units} | "
            f"{metrics.auditability:.2f} | "
            f"{metrics.trajectory_count} |"
        )
    lines.extend(
        [
            "",
            f"Recommendation: {comparison.recommendation}",
            f"Rationale: {comparison.rationale}",
            "",
            "Auditability note: trajectories are exported as deterministic JSON events; no training, reward model, or imported RAG-Gym source is used.",
        ]
    )
    return "\n".join(lines)
