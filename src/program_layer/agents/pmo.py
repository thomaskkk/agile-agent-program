"""PMO Agent — converts a parsed SDD into a DeliveryPlan.

Primary model: PMO_AGENT_MODEL (default claude-sonnet-4-6)
Fallback: FALLBACK_MODEL (OpenAI, default gpt-4o)

Also handles re-entry from mitigation routes (rollback, rescope) and from PM Agent on product_gap.
"""
from __future__ import annotations

import copy
from typing import cast

from anthropic import Anthropic, APIError
from openai import OpenAI

from program_layer import config as cfg
from program_layer.schemas.models import DeliveryPlan, ProgramState, SDD


def _inline_refs(schema: dict) -> dict:
    """Resolve $ref/$defs into inline definitions so the schema needs no JSON Schema resolver."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})
    schema.pop("title", None)

    def resolve(node: object) -> object:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = str(node["$ref"]).split("/")[-1]
                return resolve(copy.deepcopy(defs[ref_name]))
            return {k: resolve(v) for k, v in node.items()}  # type: ignore[union-attr]
        if isinstance(node, list):
            return [resolve(item) for item in node]  # type: ignore[union-attr]
        return node

    return resolve(schema)  # type: ignore[return-value]


_DELIVERY_PLAN_TOOL_SCHEMA: dict = _inline_refs(DeliveryPlan.model_json_schema())

_SYSTEM_PROMPT = (
    "You are a senior PMO. Given a parsed SDD, produce a concrete DeliveryPlan that breaks "
    "the work into project scopes with clear acceptance criteria and inter-project artifact "
    "dependencies in correct topological order."
)


def _sdd_to_prompt(sdd: SDD) -> str:
    constraints_text = "\n".join(f"- {c}" for c in sdd.constraints) if sdd.constraints else "None"
    projects_text = "\n".join(f"- {p}" for p in sdd.projects)
    return (
        f"Title: {sdd.title}\n\n"
        f"Summary: {sdd.summary}\n\n"
        f"Projects:\n{projects_text}\n\n"
        f"Constraints:\n{constraints_text}"
    )


def pmo_agent(state: ProgramState) -> ProgramState:
    retry_counts: dict[str, int] = dict(state.get("retry_counts") or {})
    retry_counts["pmo"] = retry_counts.get("pmo", 0) + 1

    sdd: SDD | None = state.get("sdd")
    if sdd is None:
        raise ValueError("PMO Agent requires a parsed SDD in state")

    user_message = f"Produce a DeliveryPlan for this SDD:\n\n{_sdd_to_prompt(sdd)}"

    # Primary: Anthropic
    try:
        client = Anthropic()
        response = client.messages.create(
            model=cfg.PMO_AGENT_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=[
                {
                    "name": "return_delivery_plan",
                    "description": "Return the DeliveryPlan",
                    "input_schema": _DELIVERY_PLAN_TOOL_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": "return_delivery_plan"},
            messages=[{"role": "user", "content": user_message}],
        )
        for block in response.content:
            if block.type == "tool_use":
                delivery_plan = DeliveryPlan(**cast(dict, block.input))
                return {"delivery_plan": delivery_plan, "retry_counts": retry_counts}
    except APIError:
        pass

    # Fallback: OpenAI
    _fail_msg = (
        f"Both {cfg.PMO_AGENT_MODEL} and fallback {cfg.FALLBACK_MODEL} failed to produce DeliveryPlan"
    )
    try:
        client = OpenAI()
        response = client.chat.completions.parse(
            model=cfg.FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=DeliveryPlan,
        )
        delivery_plan = response.choices[0].message.parsed
        if delivery_plan is None:
            raise RuntimeError(_fail_msg)
        return {"delivery_plan": delivery_plan, "retry_counts": retry_counts}
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(_fail_msg) from exc
