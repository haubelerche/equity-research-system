from __future__ import annotations

from typing import Any, Callable

GRAPH_STAGES = [
    "PREFLIGHT",
    "BUILD_FACTS",
    "DATA_QUALITY_GATE",
    "BUILD_INDEX",
    "VALUATION_DRAFT",
    "VALUATION_GATE",
    "WAITING_ASSUMPTIONS_APPROVAL",
    "VALUATION_LOCKED",
    "REPORT_GENERATION",
    "QUALITY_EVALUATION",
    "CITATION_GATE",
    "RESEARCH_REVIEW",
    "AUDIT_REVIEW",
    "EXPORT_GATE",
    "WAITING_FINAL_APPROVAL",
    "PUBLISHED",
]


def build_langgraph(node_map: dict[str, Callable[[dict[str, Any]], dict[str, Any]]]):
    """Build a LangGraph when the dependency is available.

    The runner also supports a deterministic fallback so local environments can
    execute contract tests before dependencies are installed.
    """
    try:
        from langgraph.graph import END, StateGraph
    except Exception:  # noqa: BLE001
        return None

    graph = StateGraph(dict)
    for stage, node in node_map.items():
        graph.add_node(stage, node)

    graph.set_entry_point("PREFLIGHT")
    for current, nxt in zip(GRAPH_STAGES, GRAPH_STAGES[1:]):
        if current in {"WAITING_ASSUMPTIONS_APPROVAL", "WAITING_FINAL_APPROVAL", "PUBLISHED"}:
            continue
        graph.add_edge(current, nxt)

    graph.add_edge("WAITING_ASSUMPTIONS_APPROVAL", END)
    graph.add_edge("WAITING_FINAL_APPROVAL", END)
    graph.add_edge("PUBLISHED", END)
    return graph.compile()
