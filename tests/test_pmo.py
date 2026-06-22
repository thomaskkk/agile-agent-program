"""Tests for PMO Agent."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from anthropic import APIConnectionError

from program_layer.schemas.models import (
    DeliveryPlan,
    ProgramState,
    SDD,
)

SAMPLE_SDD = SDD(
    title="Build a Simple API with Frontend",
    summary="REST API backend and React frontend",
    projects=["project_a", "project_b"],
    constraints=["Must use OpenAPI spec"],
)

_PLAN_INPUT = {
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
            "description": "React frontend",
            "dependencies": ["project_a"],
        },
    ],
    "acceptance_criteria": [
        {
            "criterion_id": "ac-1",
            "description": "API schema published",
            "artifact_key": "api_schema",
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


def _make_ant_response(input_data: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = input_data
    response = MagicMock()
    response.content = [tool_block]
    return response


def test_pmo_agent_returns_delivery_plan():
    """PMO agent returns a valid DeliveryPlan with at least one project, AC, and dependency."""
    from program_layer.agents.pmo import pmo_agent

    state: ProgramState = {"sdd": SAMPLE_SDD, "retry_counts": {}}

    with patch("program_layer.agents.pmo.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _make_ant_response(_PLAN_INPUT)
        result = pmo_agent(state)

    plan = result.get("delivery_plan")
    assert isinstance(plan, DeliveryPlan)
    assert len(plan.projects) >= 1
    assert len(plan.acceptance_criteria) >= 1
    assert len(plan.dependencies) >= 1
    # Dependency ordering: source project must precede its dependant
    dep = plan.dependencies[0]
    assert dep.from_project == "project_a"
    assert dep.to_project == "project_b"


def test_pmo_agent_increments_retry_count():
    """PMO agent increments the pmo key in retry_counts each call."""
    from program_layer.agents.pmo import pmo_agent

    state: ProgramState = {"sdd": SAMPLE_SDD, "retry_counts": {"pmo": 1}}

    with patch("program_layer.agents.pmo.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = _make_ant_response(_PLAN_INPUT)
        result = pmo_agent(state)

    assert result["retry_counts"]["pmo"] == 2


def test_pmo_agent_falls_back_to_openai_on_anthropic_failure():
    """PMO agent returns a valid DeliveryPlan via OpenAI fallback when Anthropic raises."""
    from program_layer.agents.pmo import pmo_agent

    state: ProgramState = {"sdd": SAMPLE_SDD, "retry_counts": {}}

    fallback_plan = DeliveryPlan(**_PLAN_INPUT)
    mock_oai_response = MagicMock()
    mock_oai_response.choices[0].message.parsed = fallback_plan

    with patch("program_layer.agents.pmo.Anthropic") as mock_ant_cls, \
         patch("program_layer.agents.pmo.OpenAI") as mock_oai_cls:
        mock_ant_cls.return_value.messages.create.side_effect = APIConnectionError(request=None)
        mock_oai_cls.return_value.chat.completions.parse.return_value = mock_oai_response

        result = pmo_agent(state)

    assert isinstance(result.get("delivery_plan"), DeliveryPlan)


def test_pmo_agent_raises_when_both_fail():
    """PMO agent raises RuntimeError when both primary and fallback fail."""
    from program_layer.agents.pmo import pmo_agent

    state: ProgramState = {"sdd": SAMPLE_SDD, "retry_counts": {}}

    with patch("program_layer.agents.pmo.Anthropic") as mock_ant_cls, \
         patch("program_layer.agents.pmo.OpenAI") as mock_oai_cls:
        mock_ant_cls.return_value.messages.create.side_effect = APIConnectionError(request=None)
        mock_oai_cls.return_value.chat.completions.parse.side_effect = Exception("OpenAI error")

        with pytest.raises(RuntimeError):
            pmo_agent(state)
