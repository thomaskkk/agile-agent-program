"""Full-graph integration test: happy-path delivery run reaches RELEASE terminal state."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from program_layer.graph import build_graph


_CONTRACT_GATE_TOOL_INPUT = {
    "valid": True,
    "failures": [],
}

_PARSER_TOOL_INPUT = {
    "title": "Sample SDD",
    "summary": "Build a simple API with a frontend UI.",
    "projects": ["project_a", "project_b"],
    "constraints": [],
}

_PMO_TOOL_INPUT = {
    "projects": [
        {
            "project_id": "project_a",
            "name": "Core API",
            "description": "Backend service with API and events",
            "dependencies": [],
        },
        {
            "project_id": "project_b",
            "name": "Frontend UI",
            "description": "Frontend application consuming the API",
            "dependencies": ["project_a"],
        },
    ],
    "acceptance_criteria": [
        {
            "criterion_id": "ac-1",
            "description": "API schema is published",
            "artifact_key": "api_schema",
        },
        {
            "criterion_id": "ac-2",
            "description": "Frontend integrates successfully",
            "artifact_key": "frontend_bundle",
        },
    ],
    "dependencies": [
        {
            "from_project": "project_a",
            "to_project": "project_b",
            "artifact_key": "api_schema",
        },
    ],
}

_PM_AGENT_TOOL_INPUT = {
    "meets_value": True,
    "findings": ["All acceptance criteria satisfied."],
    "recommendation": "Release.",
}


def _make_tool_response(input_data: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = input_data
    response = MagicMock()
    response.content = [tool_block]
    return response


def test_happy_path_reaches_release(tmp_path):
    """A delivery run with mocked LLM agents and happy-path Dark Factory stubs reaches RELEASE."""
    db_path = str(tmp_path / "checkpoints.db")

    with patch("program_layer.agents.parser.Anthropic") as mock_parser_ant, \
         patch("program_layer.agents.pmo.Anthropic") as mock_pmo_ant, \
         patch("program_layer.agents.contract_gate.Anthropic") as mock_gate_ant, \
         patch("program_layer.agents.pm.Anthropic") as mock_pm_ant:

        mock_parser_ant.return_value.messages.create.return_value = _make_tool_response(
            _PARSER_TOOL_INPUT
        )
        mock_pmo_ant.return_value.messages.create.return_value = _make_tool_response(
            _PMO_TOOL_INPUT
        )
        mock_gate_ant.return_value.messages.create.return_value = _make_tool_response(
            _CONTRACT_GATE_TOOL_INPUT
        )
        mock_pm_ant.return_value.messages.create.return_value = _make_tool_response(
            _PM_AGENT_TOOL_INPUT
        )

        graph = build_graph(checkpoint_db_path=db_path)
        initial_state = {"sdd_raw": "# Sample SDD\n\nBuild a simple API with a frontend UI."}
        result = graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": "test-run-1"}},
        )

    assert result["status"] == "RELEASE"
