"""Unit tests for the Contract Gate Agent — PB-5.

Tests cover:
- happy path (valid=True, no LLM route needed)
- each mitigation route (update_contract, rollback, rescope, escalate)
- loop guard forces escalate when retry_counts hits MAX_RETRIES
- CONTRACT_GATE_MODEL is read from env (verified via mock assertion)
- routing function for each route
"""
from unittest.mock import MagicMock, patch

import pytest

from program_layer import config
from program_layer.agents.contract_gate import contract_gate_agent
from program_layer.graph import _route_contract_gate
from program_layer.schemas.models import (
    AcceptanceCriterion,
    ContractFailure,
    ContractValidation,
    DeliveryPlan,
    Dependency,
    ProjectOutput,
    ProjectScope,
    ProgramState,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_DELIVERY_PLAN = DeliveryPlan(
    projects=[
        ProjectScope(
            project_id="project_a",
            name="Core API",
            description="Backend service",
        )
    ],
    acceptance_criteria=[
        AcceptanceCriterion(
            criterion_id="ac-1",
            description="API schema is published",
            artifact_key="api_schema",
        ),
    ],
    dependencies=[],
)

_HAPPY_OUTPUT = ProjectOutput(
    project_id="project_a",
    artifacts={"api_schema": "stub-schema-v1"},
    status="complete",
)

_FAILED_OUTPUT = ProjectOutput(
    project_id="project_a",
    artifacts={},
    status="failed",
)


def _make_tool_response(
    valid: bool,
    failures: list | None = None,
    mitigation_route: str | None = None,
) -> MagicMock:
    """Return a mock anthropic messages.create() response with a single tool_use block."""
    tool_use = MagicMock()
    tool_use.type = "tool_use"
    payload: dict = {"valid": valid, "failures": failures or []}
    if mitigation_route:
        payload["mitigation_route"] = mitigation_route
    tool_use.input = payload

    response = MagicMock()
    response.content = [tool_use]
    return response


def _state(output=_HAPPY_OUTPUT, retry_counts=None) -> ProgramState:
    return {
        "sdd_raw": "",
        "delivery_plan": _DELIVERY_PLAN,
        "project_a_output": output,
        "retry_counts": dict(retry_counts or {}),
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@patch("program_layer.agents.contract_gate.Anthropic")
def test_happy_path_valid(mock_cls):
    mock_cls.return_value.messages.create.return_value = _make_tool_response(True)

    result = contract_gate_agent(_state())

    cv = result["contract_validation"]
    assert cv.valid is True
    assert cv.failures == []
    assert cv.mitigation_route is None
    assert result["retry_counts"]["contract_gate"] == 1


# ---------------------------------------------------------------------------
# Mitigation routes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "route",
    ["update_contract", "rollback", "rescope", "escalate"],
)
@patch("program_layer.agents.contract_gate.Anthropic")
def test_mitigation_routes(mock_cls, route):
    failure = [{"criterion": "ac-1", "artifact_key": "api_schema", "reason": "test"}]
    mock_cls.return_value.messages.create.return_value = _make_tool_response(
        False, failures=failure, mitigation_route=route
    )

    result = contract_gate_agent(_state(output=_FAILED_OUTPUT))

    cv = result["contract_validation"]
    assert cv.valid is False
    assert cv.mitigation_route == route
    assert len(cv.failures) == 1
    assert cv.failures[0].criterion == "ac-1"


# ---------------------------------------------------------------------------
# Loop guard
# ---------------------------------------------------------------------------


@patch("program_layer.agents.contract_gate.Anthropic")
def test_loop_guard_forces_escalate(mock_cls):
    """When retry_counts["contract_gate"] is already MAX_RETRIES-1, the next
    increment hits MAX_RETRIES and must escalate without calling the LLM."""
    initial_count = config.MAX_RETRIES - 1
    result = contract_gate_agent(_state(retry_counts={"contract_gate": initial_count}))

    cv = result["contract_validation"]
    assert cv.valid is False
    assert cv.mitigation_route == "escalate"
    assert result["retry_counts"]["contract_gate"] == config.MAX_RETRIES
    mock_cls.return_value.messages.create.assert_not_called()


@patch("program_layer.agents.contract_gate.Anthropic")
def test_loop_guard_increments_count(mock_cls):
    mock_cls.return_value.messages.create.return_value = _make_tool_response(True)

    result = contract_gate_agent(_state(retry_counts={"contract_gate": 0}))
    assert result["retry_counts"]["contract_gate"] == 1


# ---------------------------------------------------------------------------
# Model env var
# ---------------------------------------------------------------------------


@patch("program_layer.agents.contract_gate.Anthropic")
def test_uses_contract_gate_model(mock_cls):
    """The agent must pass CONTRACT_GATE_MODEL (from config) to messages.create."""
    mock_cls.return_value.messages.create.return_value = _make_tool_response(True)

    contract_gate_agent(_state())

    call_kwargs = mock_cls.return_value.messages.create.call_args
    assert call_kwargs.kwargs["model"] == config.CONTRACT_GATE_MODEL


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------


def test_route_valid_goes_to_factory_b():
    state = {"contract_validation": ContractValidation(valid=True, failures=[], mitigation_route=None)}
    assert _route_contract_gate(state) == "factory_b"


def test_route_update_contract():
    state = {
        "contract_validation": ContractValidation(
            valid=False, failures=[], mitigation_route="update_contract"
        )
    }
    assert _route_contract_gate(state) == "update_contract"


def test_route_rollback_goes_to_pmo():
    state = {
        "contract_validation": ContractValidation(
            valid=False, failures=[], mitigation_route="rollback"
        )
    }
    assert _route_contract_gate(state) == "pmo"


def test_route_rescope_goes_to_pmo():
    state = {
        "contract_validation": ContractValidation(
            valid=False, failures=[], mitigation_route="rescope"
        )
    }
    assert _route_contract_gate(state) == "pmo"


def test_route_escalate():
    state = {
        "contract_validation": ContractValidation(
            valid=False, failures=[], mitigation_route="escalate"
        )
    }
    assert _route_contract_gate(state) == "escalate"


def test_route_none_validation_escalates():
    assert _route_contract_gate({"contract_validation": None}) == "escalate"
