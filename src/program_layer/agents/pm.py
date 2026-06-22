"""PM Agent — LLM-powered value assessment of ProjectOutput against the SDD intent.

Primary model: PM_AGENT_MODEL (default claude-sonnet-4-6)
Fallback: FALLBACK_MODEL (OpenAI, default gpt-4o)

Receives the SDD, DeliveryPlan, and ProjectOutput from Project B.
Produces a ValueAssessment (meets_value, gap_type, findings, recommendation).
Includes a loop guard: increments retry_counts["pm"] on every entry and forces
escalate when MAX_RETRIES is reached without calling the LLM.
"""
from __future__ import annotations

import json
from typing import cast

from anthropic import Anthropic, APIError
from anthropic.types import ToolParam
from openai import OpenAI

from program_layer import config
from program_layer.schemas.models import (
    ProgramState,
    ValueAssessment,
)

_TOOL_SCHEMA: ToolParam = {
    "name": "assess_value",
    "description": (
        "Assess whether the project output meets the value intent described in the SDD. "
        "Identify whether any gap is a product gap (design/planning issue) or an "
        "implementation gap (execution issue)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "meets_value": {
                "type": "boolean",
                "description": "True if the output satisfies the SDD's value intent.",
            },
            "gap_type": {
                "type": "string",
                "enum": ["product_gap", "implementation_gap"],
                "description": (
                    "Required when meets_value=false. "
                    "product_gap: the requirements or design are wrong and need replanning. "
                    "implementation_gap: the design is correct but execution was poor."
                ),
            },
            "findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific observations about the output quality and gaps.",
            },
            "recommendation": {
                "type": "string",
                "description": "Recommended next action.",
            },
        },
        "required": ["meets_value", "findings", "recommendation"],
    },
}


def _build_assessment(data: dict) -> ValueAssessment:
    gap_type = None
    if not data["meets_value"]:
        gap_type = data.get("gap_type")
    return ValueAssessment(
        meets_value=data["meets_value"],
        gap_type=gap_type,
        findings=data.get("findings", []),
        recommendation=data.get("recommendation", ""),
    )


def pm_agent(state: ProgramState) -> ProgramState:
    retry_counts: dict[str, int] = dict(state.get("retry_counts") or {})
    retry_counts["pm"] = retry_counts.get("pm", 0) + 1

    if retry_counts["pm"] >= config.MAX_RETRIES:
        # Return None so _route_pm_agent hits the va-is-None → "escalate" branch.
        return {"value_assessment": None, "retry_counts": retry_counts}

    sdd = state.get("sdd")
    delivery_plan = state.get("delivery_plan")
    project_b_output = state.get("project_b_output")

    criteria_lines = "\n".join(
        f"- {ac.criterion_id}: {ac.description} (artifact_key: {ac.artifact_key})"
        for ac in (delivery_plan.acceptance_criteria if delivery_plan else [])
    )
    artifacts_json = json.dumps(
        project_b_output.artifacts if project_b_output else {},
        indent=2,
    )
    project_status = project_b_output.status if project_b_output else "unknown"

    sdd_context = (
        f"Title: {sdd.title}\nSummary: {sdd.summary}"
        if sdd
        else "No SDD available."
    )

    prompt = (
        "You are the PM Agent (Value Assurance). Assess whether the Project B output "
        "meets the value intent described in the SDD.\n\n"
        f"SDD:\n{sdd_context}\n\n"
        f"Acceptance Criteria:\n{criteria_lines}\n\n"
        f"Project B Output:\n"
        f"  status: {project_status}\n"
        f"  artifacts:\n{artifacts_json}\n\n"
        "Call the assess_value tool with your assessment."
    )

    # Primary: Anthropic
    try:
        ant_client = Anthropic()
        response = ant_client.messages.create(
            model=config.PM_AGENT_MODEL,
            max_tokens=1024,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": prompt}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        return {
            "value_assessment": _build_assessment(cast(dict, tool_use.input)),
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
            response_format=ValueAssessment,
        )
        assessment = oai_response.choices[0].message.parsed
        if assessment is not None:
            return {"value_assessment": assessment, "retry_counts": retry_counts}
    except Exception as exc:
        raise RuntimeError(
            f"Both {config.PM_AGENT_MODEL} and fallback {config.FALLBACK_MODEL} "
            "failed to assess value"
        ) from exc

    raise RuntimeError(
        f"Both {config.PM_AGENT_MODEL} and fallback {config.FALLBACK_MODEL} "
        "failed to assess value"
    )
