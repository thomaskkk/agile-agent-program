"""Tests for PB-6: escalation interrupt handler.

Covers:
  AC6 — Contract Gate escalate route triggers interrupt; resume injects resolution.
  AC7 — Loop guard threshold routes to the shared interrupt node.
  AC8 — Auto-approve stub completes a full Delivery Run without manual input.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from langgraph.types import Command

from program_layer import config as cfg
from program_layer.graph import build_graph


_PARSER_TOOL_INPUT = {
    "title": "Test SDD",
    "summary": "Test delivery for interrupt tests.",
    "projects": ["project_a", "project_b"],
    "constraints": [],
}

_PMO_TOOL_INPUT = {
    "projects": [
        {
            "project_id": "project_a",
            "name": "Core API",
            "description": "Backend service",
            "dependencies": [],
        },
        {
            "project_id": "project_b",
            "name": "Frontend UI",
            "description": "Frontend application",
            "dependencies": ["project_a"],
        },
    ],
    "acceptance_criteria": [
        {
            "criterion_id": "ac-1",
            "description": "API schema is published",
            "artifact_key": "api_schema",
        },
    ],
    "dependencies": [],
}

_ESCALATE_CONTRACT_TOOL_INPUT = {
    "valid": False,
    "failures": [
        {
            "criterion": "ac-1",
            "artifact_key": "api_schema",
            "reason": "critical schema failure",
        }
    ],
    "mitigation_route": "escalate",
}


def _make_tool_response(input_data: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = input_data
    response = MagicMock()
    response.content = [tool_block]
    return response


def test_escalate_route_from_contract_gate_triggers_interrupt_and_resumes(
    tmp_path, monkeypatch
):
    """Contract Gate escalate route pauses the graph; injecting a resolution resumes it.

    AC6: escalate route triggers interrupt; contract_validation is in state; resume works.
    """
    monkeypatch.setenv("AUTO_APPROVE_ESCALATION", "false")
    db_path = str(tmp_path / "checkpoints.db")
    thread_config = {"configurable": {"thread_id": "interrupt-test-ac6"}}

    with (
        patch("program_layer.agents.parser.Anthropic") as mock_parser,
        patch("program_layer.agents.pmo.Anthropic") as mock_pmo,
        patch("program_layer.agents.contract_gate.Anthropic") as mock_gate,
    ):
        mock_parser.return_value.messages.create.return_value = _make_tool_response(
            _PARSER_TOOL_INPUT
        )
        mock_pmo.return_value.messages.create.return_value = _make_tool_response(
            _PMO_TOOL_INPUT
        )
        mock_gate.return_value.messages.create.return_value = _make_tool_response(
            _ESCALATE_CONTRACT_TOOL_INPUT
        )

        graph = build_graph(checkpoint_db_path=db_path)

        # First invocation — graph should pause at the interrupt node
        graph.invoke(
            {"sdd_raw": "# Test SDD\n\nTest delivery."},
            config=thread_config,
        )

        # Graph is paused: contract_validation is in state and next steps are pending
        snapshot = graph.get_state(thread_config)
        assert len(snapshot.next) > 0, "Graph should be paused at the interrupt node"
        assert snapshot.values.get("contract_validation") is not None, (
            "ProgramState must contain the ContractValidation that triggered the interrupt"
        )

        # Resume by injecting a human resolution
        final_state = graph.invoke(Command(resume="approved"), config=thread_config)

    assert "resumed_after_escalation" in final_state["status"]
    assert final_state.get("escalation_resolution") == "approved"


def test_loop_guard_threshold_reaches_interrupt_node(tmp_path, monkeypatch):
    """Loop guard trigger (retry_counts >= MAX_RETRIES) routes to the shared interrupt node.

    AC7: the same escalate node handles the loop guard path, not a separate node.
    LLM must NOT be called when the guard fires.
    """
    monkeypatch.setenv("AUTO_APPROVE_ESCALATION", "true")
    db_path = str(tmp_path / "checkpoints.db")

    with (
        patch("program_layer.agents.parser.Anthropic") as mock_parser,
        patch("program_layer.agents.pmo.Anthropic") as mock_pmo,
        patch("program_layer.agents.contract_gate.Anthropic") as mock_gate,
    ):
        mock_parser.return_value.messages.create.return_value = _make_tool_response(
            _PARSER_TOOL_INPUT
        )
        mock_pmo.return_value.messages.create.return_value = _make_tool_response(
            _PMO_TOOL_INPUT
        )

        graph = build_graph(checkpoint_db_path=db_path)
        # One retry short of the limit so the first entry into contract_gate triggers the guard
        initial_state = {
            "sdd_raw": "# Test SDD\n\nTest delivery.",
            "retry_counts": {"contract_gate": cfg.MAX_RETRIES - 1},
        }
        final_state = graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": "loop-guard-test-ac7"}},
        )

    # Loop guard bypassed the LLM entirely
    mock_gate.return_value.messages.create.assert_not_called()
    # Graph reached the shared escalate interrupt node (auto-approved in test mode)
    assert final_state["status"] == "escalated_auto_approved"


def test_auto_approve_stub_allows_full_run_without_manual_input(tmp_path, monkeypatch):
    """Auto-approve stub lets an escalated Delivery Run complete without human intervention.

    AC8: end-to-end run with escalation path completes automatically via AUTO_APPROVE_ESCALATION.
    """
    monkeypatch.setenv("AUTO_APPROVE_ESCALATION", "true")
    db_path = str(tmp_path / "checkpoints.db")

    with (
        patch("program_layer.agents.parser.Anthropic") as mock_parser,
        patch("program_layer.agents.pmo.Anthropic") as mock_pmo,
        patch("program_layer.agents.contract_gate.Anthropic") as mock_gate,
    ):
        mock_parser.return_value.messages.create.return_value = _make_tool_response(
            _PARSER_TOOL_INPUT
        )
        mock_pmo.return_value.messages.create.return_value = _make_tool_response(
            _PMO_TOOL_INPUT
        )
        mock_gate.return_value.messages.create.return_value = _make_tool_response(
            _ESCALATE_CONTRACT_TOOL_INPUT
        )

        graph = build_graph(checkpoint_db_path=db_path)
        final_state = graph.invoke(
            {"sdd_raw": "# Test SDD\n\nTest delivery."},
            config={"configurable": {"thread_id": "auto-approve-test-ac8"}},
        )

    assert final_state["status"] == "escalated_auto_approved"
