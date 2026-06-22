"""Contract Gate Agent — LLM-powered evaluation of ProjectOutput vs AcceptanceCriteria.

Primary model: CONTRACT_GATE_MODEL (default claude-sonnet-4-6)
Fallback: FALLBACK_MODEL (OpenAI, default gpt-4o)

Includes a loop guard: increments retry_counts["contract_gate"] on every entry
and forces escalate when MAX_RETRIES is reached without calling the LLM.
"""
from __future__ import annotations

import json
from typing import cast

from anthropic import Anthropic, APIError
from anthropic.types import ToolParam
from openai import OpenAI

from program_layer import config
from program_layer.schemas.models import (
    ContractFailure,
    ContractValidation,
    ProgramState,
)

_TOOL_SCHEMA: ToolParam = {
    "name": "evaluate_contract",
    "description": (
        "Evaluate whether project output satisfies the acceptance criteria "
        "and select a mitigation route if it does not."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "valid": {
                "type": "boolean",
                "description": "True if all acceptance criteria are met.",
            },
            "failures": {
                "type": "array",
                "description": "List of unmet criteria. Empty when valid=true.",
                "items": {
                    "type": "object",
                    "properties": {
                        "criterion": {"type": "string"},
                        "artifact_key": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["criterion", "artifact_key", "reason"],
                },
            },
            "mitigation_route": {
                "type": "string",
                "enum": ["update_contract", "rollback", "rescope", "escalate"],
                "description": (
                    "Required when valid=false. "
                    "update_contract: artifact needs minor improvement. "
                    "rollback: artifact is missing or fundamentally wrong. "
                    "rescope: project scope must change at planning level. "
                    "escalate: critical failure requiring human review."
                ),
            },
        },
        "required": ["valid", "failures"],
    },
}


def _build_validation(data: dict) -> ContractValidation:
    failures = [
        ContractFailure(
            criterion=f["criterion"],
            artifact_key=f["artifact_key"],
            reason=f["reason"],
        )
        for f in data.get("failures", [])
    ]
    mitigation_route = None
    if not data["valid"]:
        mitigation_route = data.get("mitigation_route", "escalate")
    return ContractValidation(
        valid=data["valid"],
        failures=failures,
        mitigation_route=mitigation_route,
    )


def contract_gate_agent(state: ProgramState) -> ProgramState:
    retry_counts: dict[str, int] = dict(state.get("retry_counts") or {})
    retry_counts["contract_gate"] = retry_counts.get("contract_gate", 0) + 1

    if retry_counts["contract_gate"] >= config.MAX_RETRIES:
        return {
            "contract_validation": ContractValidation(
                valid=False,
                failures=[],
                mitigation_route="escalate",
            ),
            "retry_counts": retry_counts,
        }

    project_output = state.get("project_a_output")
    delivery_plan = state.get("delivery_plan")

    criteria_lines = "\n".join(
        f"- {ac.criterion_id}: {ac.description} (artifact_key: {ac.artifact_key})"
        for ac in (delivery_plan.acceptance_criteria if delivery_plan else [])
    )
    artifacts_json = json.dumps(
        project_output.artifacts if project_output else {},
        indent=2,
    )
    project_status = project_output.status if project_output else "unknown"

    prompt = (
        "Evaluate whether the project output satisfies all acceptance criteria.\n\n"
        f"Acceptance Criteria:\n{criteria_lines}\n\n"
        f"Project Output:\n"
        f"  status: {project_status}\n"
        f"  artifacts:\n{artifacts_json}\n\n"
        "Call the evaluate_contract tool with your assessment."
    )

    # Primary: Anthropic
    try:
        ant_client = Anthropic()
        response = ant_client.messages.create(
            model=config.CONTRACT_GATE_MODEL,
            max_tokens=1024,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": prompt}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        return {
            "contract_validation": _build_validation(cast(dict, tool_use.input)),
            "retry_counts": retry_counts,
        }
    except APIError:
        pass

    # Fallback: OpenAI
    try:
        oai_client = OpenAI()
        oai_response = oai_client.chat.completions.parse(
            model=config.FALLBACK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format=ContractValidation,
        )
        validation = oai_response.choices[0].message.parsed
        if validation is not None:
            return {"contract_validation": validation, "retry_counts": retry_counts}
    except Exception as exc:
        raise RuntimeError(
            f"Both {config.CONTRACT_GATE_MODEL} and fallback {config.FALLBACK_MODEL} "
            "failed to evaluate contract"
        ) from exc

    raise RuntimeError(
        f"Both {config.CONTRACT_GATE_MODEL} and fallback {config.FALLBACK_MODEL} "
        "failed to evaluate contract"
    )
