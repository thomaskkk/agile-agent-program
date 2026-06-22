"""SDD Parser Agent — converts raw Markdown SDD/PRD into a structured SDD Pydantic model.

Primary model: PARSER_AGENT_MODEL (default claude-sonnet-4-6)
Fallback: FALLBACK_MODEL (OpenAI, default gpt-4o)
"""
from __future__ import annotations

from typing import cast

from anthropic import Anthropic, APIError
from openai import OpenAI

from program_layer import config as cfg
from program_layer.schemas.models import ProgramState, SDD

_SDD_TOOL_SCHEMA: dict = SDD.model_json_schema()

_SYSTEM_PROMPT = (
    "You are an expert software architect. Parse the given SDD/PRD Markdown document "
    "and extract structured information about the project."
)


def parse_sdd(state: ProgramState) -> ProgramState:
    sdd_raw = state.get("sdd_raw", "")
    user_message = f"Parse this SDD/PRD document into structured information:\n\n{sdd_raw}"

    # Primary: Anthropic
    try:
        client = Anthropic()
        response = client.messages.create(
            model=cfg.PARSER_AGENT_MODEL,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            tools=[
                {
                    "name": "return_sdd",
                    "description": "Return the parsed SDD structure",
                    "input_schema": _SDD_TOOL_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": "return_sdd"},
            messages=[{"role": "user", "content": user_message}],
        )
        for block in response.content:
            if block.type == "tool_use":
                return {"sdd": SDD(**cast(dict, block.input))}
    except APIError:
        pass

    # Fallback: OpenAI
    _fail_msg = (
        f"Both {cfg.PARSER_AGENT_MODEL} and fallback {cfg.FALLBACK_MODEL} failed to parse SDD"
    )
    try:
        client = OpenAI()
        response = client.chat.completions.parse(
            model=cfg.FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=SDD,
        )
        sdd = response.choices[0].message.parsed
        if sdd is None:
            raise RuntimeError(_fail_msg)
        return {"sdd": sdd}
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(_fail_msg) from exc
