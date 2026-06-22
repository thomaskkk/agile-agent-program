"""Unit tests for the PM Agent — PB-7.

Tests cover:
- PM_AGENT_MODEL is read from env (verified via mock assertion)
- meets_value=True produces RELEASE routing
- product_gap produces PMO Agent routing
- implementation_gap produces Project B Dark Factory routing
- retry_counts increments on each re-entry
- loop guard forces escalate when retry_counts hits MAX_RETRIES
"""
from unittest.mock import MagicMock, patch

import pytest

from program_layer import config
from program_layer.agents.pm import pm_agent
from program_layer.graph import _route_pm_agent
from program_layer.schemas.models import (
    AcceptanceCriterion,
    DeliveryPlan,
    Dependency,
    ProjectOutput,
    ProjectScope,
    ProgramState,
    SDD,
    ValueAssessment,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_SDD = SDD(
    title="Test SDD",
    summary="Build a simple web app with API and frontend.",
    projects=["project_a", "project_b"],
    constraints=["Must deploy on AWS"],
)

_DELIVERY_PLAN = DeliveryPlan(
    projects=[
        ProjectScope(
            project_id="project_b",
            name="Frontend UI",
            description="Frontend consuming the API",
            dependencies=["project_a"],
        )
    ],
    acceptance_criteria=[
        AcceptanceCriterion(
            criterion_id="ac-1",
            description="Frontend bundle is deployed",
            artifact_key="frontend_bundle",
        ),
    ],
    dependencies=[
        Dependency(
            from_project="project_a",
            to_project="project_b",
            artifact_key="api_schema",
        )
    ],
)

_HAPPY_OUTPUT = ProjectOutput(
    project_id="project_b",
    artifacts={"frontend_bundle": "bundle-v1.js"},
    status="complete",
)

_FAILED_OUTPUT = ProjectOutput(
    project_id="project_b",
    artifacts={},
    status="failed",
)


def _make_tool_response(
    meets_value: bool,
    gap_type: str | None = None,
    findings: list[str] | None = None,
    recommendation: str = "Release.",
) -> MagicMock:
    tool_use = MagicMock()
    tool_use.type = "tool_use"
    payload: dict = {
        "meets_value": meets_value,
        "findings": findings or ["All criteria satisfied."],
        "recommendation": recommendation,
    }
    if gap_type is not None:
        payload["gap_type"] = gap_type
    tool_use.input = payload

    response = MagicMock()
    response.content = [tool_use]
    return response


def _state(output=_HAPPY_OUTPUT, retry_counts=None) -> ProgramState:
    return {
        "sdd": _SDD,
        "delivery_plan": _DELIVERY_PLAN,
        "project_b_output": output,
        "retry_counts": dict(retry_counts or {}),
    }


# ---------------------------------------------------------------------------
# Happy path — meets_value=True
# ---------------------------------------------------------------------------


@patch("program_layer.agents.pm.Anthropic")
def test_happy_path_meets_value(mock_cls):
    mock_cls.return_value.messages.create.return_value = _make_tool_response(True)

    result = pm_agent(_state())

    va = result["value_assessment"]
    assert va.meets_value is True
    assert va.gap_type is None
    assert result["retry_counts"]["pm"] == 1


# ---------------------------------------------------------------------------
# Gap types
# ---------------------------------------------------------------------------


@patch("program_layer.agents.pm.Anthropic")
def test_product_gap(mock_cls):
    mock_cls.return_value.messages.create.return_value = _make_tool_response(
        False,
        gap_type="product_gap",
        findings=["Requirements not met at design level."],
        recommendation="Replan with PMO.",
    )

    result = pm_agent(_state(output=_FAILED_OUTPUT))

    va = result["value_assessment"]
    assert va.meets_value is False
    assert va.gap_type == "product_gap"


@patch("program_layer.agents.pm.Anthropic")
def test_implementation_gap(mock_cls):
    mock_cls.return_value.messages.create.return_value = _make_tool_response(
        False,
        gap_type="implementation_gap",
        findings=["Bundle file is empty."],
        recommendation="Re-execute factory_b.",
    )

    result = pm_agent(_state(output=_FAILED_OUTPUT))

    va = result["value_assessment"]
    assert va.meets_value is False
    assert va.gap_type == "implementation_gap"


# ---------------------------------------------------------------------------
# Loop guard
# ---------------------------------------------------------------------------


@patch("program_layer.agents.pm.Anthropic")
def test_loop_guard_forces_escalate(mock_cls):
    """When retry_counts["pm"] is already MAX_RETRIES-1, the next increment
    hits MAX_RETRIES and must escalate without calling the LLM."""
    initial_count = config.MAX_RETRIES - 1
    result = pm_agent(_state(retry_counts={"pm": initial_count}))

    assert result["value_assessment"] is None
    assert result["retry_counts"]["pm"] == config.MAX_RETRIES
    mock_cls.return_value.messages.create.assert_not_called()
    # None value_assessment routes to escalate, not pmo or factory_b
    assert _route_pm_agent(result) == "escalate"


@patch("program_layer.agents.pm.Anthropic")
def test_loop_guard_increments_count(mock_cls):
    mock_cls.return_value.messages.create.return_value = _make_tool_response(True)

    result = pm_agent(_state(retry_counts={"pm": 0}))
    assert result["retry_counts"]["pm"] == 1


@patch("program_layer.agents.pm.Anthropic")
def test_loop_guard_preserves_other_counts(mock_cls):
    mock_cls.return_value.messages.create.return_value = _make_tool_response(True)

    result = pm_agent(_state(retry_counts={"contract_gate": 2, "pmo": 1}))
    assert result["retry_counts"]["contract_gate"] == 2
    assert result["retry_counts"]["pmo"] == 1
    assert result["retry_counts"]["pm"] == 1


# ---------------------------------------------------------------------------
# Model env var
# ---------------------------------------------------------------------------


@patch("program_layer.agents.pm.Anthropic")
def test_uses_pm_agent_model(mock_cls):
    """The agent must pass PM_AGENT_MODEL (from config) to messages.create."""
    mock_cls.return_value.messages.create.return_value = _make_tool_response(True)

    pm_agent(_state())

    call_kwargs = mock_cls.return_value.messages.create.call_args
    assert call_kwargs.kwargs["model"] == config.PM_AGENT_MODEL


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------


def test_route_meets_value_goes_to_release():
    state: ProgramState = {
        "value_assessment": ValueAssessment(
            meets_value=True,
            gap_type=None,
            findings=["All good."],
            recommendation="Release.",
        )
    }
    assert _route_pm_agent(state) == "release"


def test_route_product_gap_goes_to_pmo():
    state: ProgramState = {
        "value_assessment": ValueAssessment(
            meets_value=False,
            gap_type="product_gap",
            findings=["Design issue."],
            recommendation="Replan.",
        )
    }
    assert _route_pm_agent(state) == "pmo"


def test_route_implementation_gap_goes_to_factory_b():
    state: ProgramState = {
        "value_assessment": ValueAssessment(
            meets_value=False,
            gap_type="implementation_gap",
            findings=["Execution issue."],
            recommendation="Re-execute.",
        )
    }
    assert _route_pm_agent(state) == "factory_b"


def test_route_none_assessment_escalates():
    assert _route_pm_agent({"value_assessment": None}) == "escalate"
