from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel


class SDD(BaseModel):
    title: str
    summary: str
    projects: list[str]
    constraints: list[str] = []


class ProjectScope(BaseModel):
    project_id: str
    name: str
    description: str
    dependencies: list[str] = []


class AcceptanceCriterion(BaseModel):
    criterion_id: str
    description: str
    artifact_key: str


class Dependency(BaseModel):
    from_project: str
    to_project: str
    artifact_key: str


class DeliveryPlan(BaseModel):
    projects: list[ProjectScope]
    acceptance_criteria: list[AcceptanceCriterion]
    dependencies: list[Dependency]


class ProjectOutput(BaseModel):
    project_id: str
    artifacts: dict[str, str]
    status: Literal["complete", "failed"]


class ContractFailure(BaseModel):
    criterion: str
    artifact_key: str
    reason: str


class ContractValidation(BaseModel):
    valid: bool
    failures: list[ContractFailure]
    mitigation_route: Literal["update_contract", "rollback", "rescope", "escalate"] | None


class ValueAssessment(BaseModel):
    meets_value: bool
    gap_type: Literal["product_gap", "implementation_gap"] | None
    findings: list[str]
    recommendation: str


class ProgramState(TypedDict, total=False):
    sdd_raw: str
    sdd: SDD | None
    delivery_plan: DeliveryPlan | None
    project_a_output: ProjectOutput | None
    project_b_output: ProjectOutput | None
    contract_validation: ContractValidation | None
    value_assessment: ValueAssessment | None
    retry_counts: dict[str, int]
    status: str
    escalation_resolution: str | None
