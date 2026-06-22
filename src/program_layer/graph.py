"""Program Layer LangGraph graph assembly."""
from __future__ import annotations

import asyncio
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from program_layer import config as cfg
from program_layer.agents.contract_gate import contract_gate_agent
from program_layer.agents.parser import parse_sdd
from program_layer.agents.pm import pm_agent
from program_layer.agents.pmo import pmo_agent
from program_layer.nodes.interrupt import escalation_interrupt
from program_layer.schemas.models import ProgramState
from program_layer.stubs.factory_a import factory_a
from program_layer.stubs.factory_b import factory_b


def _route_contract_gate(state: ProgramState) -> str:
    cv = state.get("contract_validation")
    if cv is None:
        return "escalate"
    if cv.valid:
        return "factory_b"
    route = cv.mitigation_route or "escalate"
    if route == "update_contract":
        return "update_contract"
    if route in ("rollback", "rescope"):
        return "pmo"
    return "escalate"


def _route_pm_agent(state: ProgramState) -> str:
    va = state.get("value_assessment")
    if va is None:
        return "escalate"
    if va.meets_value:
        return "release"
    if va.gap_type == "product_gap":
        return "pmo"
    return "factory_b"


def _set_release(state: ProgramState) -> ProgramState:
    return {"status": "RELEASE"}


def build_graph(checkpoint_db_path: str | None = None) -> CompiledStateGraph:
    db_path = checkpoint_db_path or cfg.CHECKPOINT_DB_PATH

    builder = StateGraph(ProgramState)

    builder.add_node("parse_sdd", parse_sdd)
    builder.add_node("pmo", pmo_agent)
    builder.add_node("factory_a", factory_a)
    builder.add_node("contract_gate", contract_gate_agent)
    builder.add_node("factory_b", factory_b)
    builder.add_node("pm_agent", pm_agent)
    builder.add_node("escalate", escalation_interrupt)
    builder.add_node("release", _set_release)

    builder.add_edge(START, "parse_sdd")
    builder.add_edge("parse_sdd", "pmo")
    builder.add_edge("pmo", "factory_a")
    builder.add_edge("factory_a", "contract_gate")

    builder.add_conditional_edges(
        "contract_gate",
        _route_contract_gate,
        {
            "factory_b": "factory_b",
            "update_contract": "contract_gate",
            "pmo": "pmo",
            "escalate": "escalate",
        },
    )

    builder.add_edge("factory_b", "pm_agent")

    builder.add_conditional_edges(
        "pm_agent",
        _route_pm_agent,
        {
            "release": "release",
            "pmo": "pmo",
            "factory_b": "factory_b",
            "escalate": "escalate",
        },
    )

    builder.add_edge("escalate", END)
    builder.add_edge("release", END)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()

    return builder.compile(checkpointer=checkpointer)


async def make_graph() -> CompiledStateGraph:
    return await asyncio.to_thread(build_graph)
