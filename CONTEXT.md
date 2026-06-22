# Program Layer

The orchestration layer that coordinates end-to-end software delivery across autonomous dark factory projects. It accepts a human-authored SDD, produces a Delivery Plan, sequences Dark Factory execution, validates contracts between them, and assures the final output meets the original intent before Release.

## Language

### Inputs and planning

**SDD** (Solution Design Document):
A human-authored Markdown document that initiates a Delivery Run by specifying scope, goals, and constraints.
_Avoid_: PRD, Product Requirements Document, spec

**Delivery Plan**:
The structured, machine-readable breakdown of an SDD into ordered Project Scopes, Acceptance Criteria, and Dependencies — produced by the PMO Agent.
_Avoid_: Roadmap, plan, backlog

**Project Scope**:
A single bounded unit of work within a Delivery Plan, assigned to exactly one Dark Factory for execution.
_Avoid_: Work package, task, sprint

**Acceptance Criterion**:
A named, testable condition that a Dark Factory's Project Output must satisfy for the Contract Gate to pass.
_Avoid_: Done criterion, requirement, definition of done

**Dependency**:
A sequencing constraint between two Project Scopes — the upstream Scope must produce a valid Project Output before the downstream Scope begins.
_Avoid_: Blocker, prerequisite

### Agents

**SDD Parser Agent**:
The first node in the graph; converts raw SDD Markdown into a structured Pydantic model so that downstream agents never see raw text.
_Avoid_: Intake agent, parser

**PMO Agent**:
The orchestrator that translates a parsed SDD into a Delivery Plan; re-enters and re-plans when a Mitigation Route routes back to it.
_Avoid_: Planner, orchestrator, coordinator

**Contract Gate Agent**:
Evaluates a Dark Factory's Project Output against the Delivery Plan's Acceptance Criteria and selects a Mitigation Route on failure.
_Avoid_: Validator, dependency checker, quality gate

**PM Agent**:
The Value Assurance agent; evaluates the final Project Output against the original SDD intent and classifies any gap as a Product Gap or Implementation Gap.
_Avoid_: Product Manager Agent, value checker, release gate

### Execution

**Dark Factory**:
An autonomous LangGraph subgraph that executes a Project Scope independently, with no visibility into the Program Layer's orchestration logic.
_Avoid_: Agent project, worker, executor

**Project Output**:
The structured result returned by a Dark Factory after completing a Project Scope, containing typed Artifacts and a completion status.
_Avoid_: Delivery artifact, result, output

**Artifact**:
A named piece of content within a Project Output, identified by a typed key (`api_schema`, `event_contract`, `data_model`, `sla`).
_Avoid_: Output, deliverable, asset

**Delivery Run**:
A single end-to-end execution of the Program Layer graph, from SDD input to either Release or a paused Escalation.
_Avoid_: Run, execution, pipeline run

### Quality gates

**Contract Validation**:
The structured verdict produced by the Contract Gate Agent — includes pass/fail, per-criterion Contract Failures, and the selected Mitigation Route.
_Avoid_: Gate result, validation result

**Contract Failure**:
A single Acceptance Criterion that was not satisfied by the corresponding Artifact in a Project Output.
_Avoid_: Violation, breach, failure

**Mitigation Route**:
One of four recovery paths selected by the Contract Gate Agent on a failed Contract Validation: `update_contract`, `rollback`, `rescope`, or `escalate`.
_Avoid_: Fallback, recovery path, error route

**Value Assessment**:
The structured verdict produced by the PM Agent — includes a value pass/fail, a Gap Type, specific findings, and a recommendation.
_Avoid_: Product review, QA result

**Product Gap**:
A gap type indicating the delivered output does not match the SDD's intent; routes the Delivery Run back to the PMO Agent for replanning.
_Avoid_: Scope gap, "wrong thing built"

**Implementation Gap**:
A gap type indicating the SDD's intent was correct but execution was poor; routes the Delivery Run back to the Dark Factory for re-execution.
_Avoid_: Quality gap, "right thing built badly"

### Control flow

**Escalation**:
A domain event signalling that the system cannot autonomously resolve a failure and requires a human decision before the Delivery Run can continue.
_Avoid_: Human escalation, pause, alert

**Loop Guard**:
The mechanism that tracks re-entry counts per node and forces an Escalation when a configurable maximum (`max_retries`) is reached.
_Avoid_: Retry limit, cycle breaker

**Release**:
The terminal success state of a Delivery Run — reached only when both the Contract Gate and the PM Agent pass.
_Avoid_: Ship, deploy, done
