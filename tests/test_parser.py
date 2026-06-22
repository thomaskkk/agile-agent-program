"""Tests for SDD Parser Agent."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from anthropic import APIConnectionError

from program_layer.schemas.models import ProgramState, SDD

SAMPLE_PRD = """\
# Build a Simple API with Frontend

## Overview
Build a REST API backend and a React frontend that consumes it.

## Projects
- project_a: Core API service
- project_b: Frontend UI application

## Constraints
- Must use OpenAPI specification
- Frontend must be responsive
"""


def test_parse_sdd_returns_valid_sdd():
    """Parser returns an SDD with a non-empty title, summary, and at least one project."""
    from program_layer.agents.parser import parse_sdd

    state: ProgramState = {"sdd_raw": SAMPLE_PRD}

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {
        "title": "Build a Simple API with Frontend",
        "summary": "Build a REST API backend and a React frontend",
        "projects": ["project_a", "project_b"],
        "constraints": ["Must use OpenAPI specification", "Frontend must be responsive"],
    }
    mock_response = MagicMock()
    mock_response.content = [tool_block]

    with patch("program_layer.agents.parser.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        result = parse_sdd(state)

    sdd = result.get("sdd")
    assert isinstance(sdd, SDD)
    assert sdd.title
    assert sdd.summary
    assert len(sdd.projects) >= 1


def test_parse_sdd_falls_back_to_openai_on_anthropic_failure():
    """Parser returns a valid SDD via the OpenAI fallback when Anthropic raises."""
    from program_layer.agents.parser import parse_sdd

    state: ProgramState = {"sdd_raw": SAMPLE_PRD}

    fallback_sdd = SDD(
        title="Build a Simple API",
        summary="REST API and frontend",
        projects=["project_a", "project_b"],
    )
    mock_oai_response = MagicMock()
    mock_oai_response.choices[0].message.parsed = fallback_sdd

    with patch("program_layer.agents.parser.Anthropic") as mock_ant_cls, \
         patch("program_layer.agents.parser.OpenAI") as mock_oai_cls:
        mock_ant_cls.return_value.messages.create.side_effect = APIConnectionError(request=None)
        mock_oai_cls.return_value.chat.completions.parse.return_value = mock_oai_response

        result = parse_sdd(state)

    assert isinstance(result.get("sdd"), SDD)


def test_parse_sdd_raises_when_both_fail():
    """Parser raises RuntimeError when both primary and fallback fail."""
    from program_layer.agents.parser import parse_sdd

    state: ProgramState = {"sdd_raw": SAMPLE_PRD}

    with patch("program_layer.agents.parser.Anthropic") as mock_ant_cls, \
         patch("program_layer.agents.parser.OpenAI") as mock_oai_cls:
        mock_ant_cls.return_value.messages.create.side_effect = APIConnectionError(request=None)
        mock_oai_cls.return_value.chat.completions.parse.side_effect = Exception("OpenAI error")

        with pytest.raises(RuntimeError):
            parse_sdd(state)
