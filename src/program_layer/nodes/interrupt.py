"""Interrupt handler node for escalation.

Called when Contract Gate or PM Agent selects the 'escalate' route,
or when retry_counts hits MAX_RETRIES.

In dev mode (AUTO_APPROVE_ESCALATION=true), injects an auto-approval and
continues without halting. In production, raises a LangGraph interrupt so a
human operator can inject a resolution.
"""
import os

from langgraph.types import interrupt

from program_layer.schemas.models import ProgramState


def escalation_interrupt(state: ProgramState) -> ProgramState:
    auto_approve = os.getenv("AUTO_APPROVE_ESCALATION", "true").lower() == "true"

    contract_validation = state.get("contract_validation")
    value_assessment = state.get("value_assessment")
    context = {
        "contract_validation": contract_validation.model_dump() if contract_validation else None,
        "value_assessment": value_assessment.model_dump() if value_assessment else None,
    }

    if auto_approve:
        return {"status": "escalated_auto_approved", "escalation_resolution": None}

    resolution = interrupt({"reason": "escalation_required", "context": context})
    return {
        "status": f"resumed_after_escalation:{resolution}",
        "escalation_resolution": str(resolution),
    }
