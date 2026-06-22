"""Tests verifying each factory_a stub variant triggers the correct mitigation route.

Each test:
  1. Sets FACTORY_A_MODE to a failure-scenario stub.
  2. Calls factory_a to get the ProjectOutput.
  3. Calls contract_gate_agent with a mocked LLM returning the expected route.
  4. Asserts the ContractValidation route matches expectations.

These tests also validate the loop-guard with the repeated_failure stub.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from program_layer import config
from program_layer.agents.contract_gate import contract_gate_agent
from program_layer.schemas.models import (
    AcceptanceCriterion,
    DeliveryPlan,
    ProjectScope,
    ProgramState,
)
from program_layer.stubs.factory_a import factory_a

_DELIVERY_PLAN = DeliveryPlan(
    projects=[
        ProjectScope(project_id="project_a", name="Core API", description="Backend")
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


def _tool_response(valid: bool, route: str | None = None, failures: list | None = None):
    tool_use = MagicMock()
    tool_use.type = "tool_use"
    payload: dict = {"valid": valid, "failures": failures or []}
    if route:
        payload["mitigation_route"] = route
    tool_use.input = payload
    resp = MagicMock()
    resp.content = [tool_use]
    return resp


def _run(mode: str, llm_response) -> dict:
    """Set FACTORY_A_MODE, produce ProjectOutput, then run the contract gate."""
    base_state: ProgramState = {"sdd_raw": "", "delivery_plan": _DELIVERY_PLAN, "retry_counts": {}}
    fa_result = factory_a({**base_state, **{"FACTORY_A_MODE_OVERRIDE": mode}})
    # factory_a reads the env var directly, so we set it via monkeypatch-style
    return fa_result


@patch("program_layer.agents.contract_gate.Anthropic")
def test_happy_stub_produces_valid(mock_cls, monkeypatch):
    monkeypatch.setenv("FACTORY_A_MODE", "happy")
    mock_cls.return_value.messages.create.return_value = _tool_response(True)

    fa_out = factory_a({})
    state: ProgramState = {
        "sdd_raw": "",
        "delivery_plan": _DELIVERY_PLAN,
        "project_a_output": fa_out["project_a_output"],
        "retry_counts": {},
    }
    result = contract_gate_agent(state)

    assert result["contract_validation"].valid is True
    assert result["contract_validation"].mitigation_route is None


@patch("program_layer.agents.contract_gate.Anthropic")
def test_update_contract_stub_routes_to_update_contract(mock_cls, monkeypatch):
    monkeypatch.setenv("FACTORY_A_MODE", "update_contract")
    failure = [{"criterion": "ac-1", "artifact_key": "api_schema", "reason": "draft schema"}]
    mock_cls.return_value.messages.create.return_value = _tool_response(
        False, "update_contract", failure
    )

    fa_out = factory_a({})
    state: ProgramState = {
        "sdd_raw": "",
        "delivery_plan": _DELIVERY_PLAN,
        "project_a_output": fa_out["project_a_output"],
        "retry_counts": {},
    }
    result = contract_gate_agent(state)

    assert result["contract_validation"].mitigation_route == "update_contract"


@patch("program_layer.agents.contract_gate.Anthropic")
def test_rollback_stub_routes_to_rollback(mock_cls, monkeypatch):
    monkeypatch.setenv("FACTORY_A_MODE", "rollback")
    failure = [{"criterion": "ac-1", "artifact_key": "api_schema", "reason": "missing"}]
    mock_cls.return_value.messages.create.return_value = _tool_response(
        False, "rollback", failure
    )

    fa_out = factory_a({})
    state: ProgramState = {
        "sdd_raw": "",
        "delivery_plan": _DELIVERY_PLAN,
        "project_a_output": fa_out["project_a_output"],
        "retry_counts": {},
    }
    result = contract_gate_agent(state)

    assert result["contract_validation"].mitigation_route == "rollback"


@patch("program_layer.agents.contract_gate.Anthropic")
def test_rescope_stub_routes_to_rescope(mock_cls, monkeypatch):
    monkeypatch.setenv("FACTORY_A_MODE", "rescope")
    failure = [{"criterion": "ac-1", "artifact_key": "api_schema", "reason": "scope exceeded"}]
    mock_cls.return_value.messages.create.return_value = _tool_response(
        False, "rescope", failure
    )

    fa_out = factory_a({})
    state: ProgramState = {
        "sdd_raw": "",
        "delivery_plan": _DELIVERY_PLAN,
        "project_a_output": fa_out["project_a_output"],
        "retry_counts": {},
    }
    result = contract_gate_agent(state)

    assert result["contract_validation"].mitigation_route == "rescope"


@patch("program_layer.agents.contract_gate.Anthropic")
def test_repeated_failure_stub_triggers_loop_guard(mock_cls, monkeypatch):
    """After MAX_RETRIES-1 prior re-entries, the repeated_failure stub causes loop guard."""
    monkeypatch.setenv("FACTORY_A_MODE", "repeated_failure")

    fa_out = factory_a({})
    state: ProgramState = {
        "sdd_raw": "",
        "delivery_plan": _DELIVERY_PLAN,
        "project_a_output": fa_out["project_a_output"],
        "retry_counts": {"contract_gate": config.MAX_RETRIES - 1},
    }
    result = contract_gate_agent(state)

    assert result["contract_validation"].mitigation_route == "escalate"
    assert result["retry_counts"]["contract_gate"] == config.MAX_RETRIES
    mock_cls.return_value.messages.create.assert_not_called()
