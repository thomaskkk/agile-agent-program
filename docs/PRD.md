# PRD: Program Layer — Agile Agent Orchestration

> Jira: [PB-1](https://thomaskury.atlassian.net/browse/PB-1)

## Problem Statement

Building software with autonomous AI agents requires more than individual agents that can write code or run tests — it requires an orchestration layer that can plan delivery, coordinate sequencing, enforce contracts between dependent components, and validate that the final output actually meets product intent. Without a program layer, dark factory projects operate in isolation: there is no system that sequences their execution, validates the interfaces between them, or catches scope drift before it reaches release.

## Solution

Build a **Program Layer** — a LangGraph graph that sits above the dark factory projects and orchestrates end-to-end software delivery. It accepts a human-written Solution Design Document (PRD), breaks it into a structured delivery plan, triggers dark factory projects in sequence, validates the contracts between them, and assures that the final product increment meets the original intent before release. The program layer is not a dark factory itself — it is the coordinator that decides what gets built, in what order, and whether the results are acceptable.

## User Stories

1. As a delivery lead, I want to hand the system a Markdown PRD and have it automatically produce a structured delivery plan, so that I don't have to manually translate requirements into agent tasks.
2. As a delivery lead, I want the PMO Agent to sequence dependent projects correctly, so that downstream projects only start when their dependencies are complete and validated.
3. As a delivery lead, I want the system to validate API schemas, event contracts, data models, and SLAs produced by Project A before Project B begins, so that integration failures are caught early rather than at the end.
4. As a delivery lead, I want the Contract Gate to automatically select a mitigation route when a contract fails, so that the system recovers without requiring manual intervention for routine failures.
5. As a delivery lead, I want the system to pause and notify me when a failure cannot be resolved autonomously, so that I can provide a decision and let the run resume.
6. As a delivery lead, I want the PM Agent to evaluate the final product increment against the original PRD, so that I know whether the delivered software actually solves the stated problem.
7. As a delivery lead, I want the PM Agent to distinguish between a product gap (wrong thing built) and an implementation gap (right thing built poorly), so that the system re-routes correctly without re-planning when unnecessary.
8. As a delivery lead, I want the system to track retry counts per node, so that persistent failures automatically escalate to a human rather than looping indefinitely.
9. As a delivery lead, I want all agent runs traced in LangSmith under a single project, so that I can inspect every decision made during a delivery run.
10. As a developer, I want each agent's LLM to be independently configurable via environment variables, so that I can tune model selection per agent without changing code.
11. As a developer, I want a global fallback OpenAI model configured separately from the per-agent models, so that I have a consistent fallback without per-agent redundancy.
12. As a developer, I want graph state persisted to SQLite, so that interrupted or escalated runs survive process restarts and can be resumed.
13. As a developer, I want to invoke the program layer from the CLI with a path to a PRD file, so that I can trigger a delivery run without writing Python.
14. As a developer, I want dark factory projects represented as stubbed subgraphs, so that I can develop and test the program layer before the real factories exist.
15. As a developer, I want all Pydantic schemas for agent inputs and outputs defined in a single `schemas/` module, so that contracts between agents are explicit and centrally versioned.
16. As a developer, I want the SDD Parser Agent to isolate raw Markdown parsing from the PMO Agent, so that the PMO only ever sees structured data and never has to reason about document format.
17. As a developer, I want the escalation interrupt to be stubbable with an auto-approve response, so that I can run full graph tests without manual intervention during development.

## Implementation Decisions

- **SDD Parser Agent**: A dedicated LLM agent that receives raw PRD Markdown and produces a structured `SDD` Pydantic model. The PMO Agent never sees raw Markdown. The parser is the first node in the graph.

- **PMO Agent**: An orchestrator node that receives the parsed `SDD` and produces a `DeliveryPlan` Pydantic model containing: `projects: list[ProjectScope]` (ordered work packages), `acceptance_criteria: list[AcceptanceCriterion]`, and `dependencies: list[Dependency]`. The PMO also handles re-entry from mitigation routes (rollback, rescope) and from the PM Agent on a product gap.

- **Dark factory interface**: Each dark factory project is compiled as a LangGraph subgraph node. It receives its `ProjectScope` from the `DeliveryPlan` and returns a `ProjectOutput` Pydantic model containing `project_id: str`, `artifacts: dict[str, str]` (keyed by artifact type: `api_schema`, `event_contract`, `data_model`, `sla`), and `status: Literal["complete", "failed"]`. Stubs return deterministic fixed outputs during development.

- **Contract Gate Agent**: An LLM agent with structured output that receives the `ProjectOutput` from Project A and the `acceptance_criteria` from the `DeliveryPlan`. It returns a `ContractValidation` model: `valid: bool`, `failures: list[ContractFailure]` (each with `criterion`, `artifact_key`, `reason`), and `mitigation_route: Literal["update_contract", "rollback", "rescope", "escalate"] | None`. The LLM reasons about the failure type to select the mitigation route.

- **Mitigation routes**: Four branches off the Contract Gate — `update_contract` loops back to the Contract Gate, `rollback` and `rescope` return to the PMO, `escalate` triggers a LangGraph interrupt.

- **LangGraph interrupt (escalation)**: When the `escalate` route is taken, or when `retry_counts` hits `max_retries` (default: 3) on any node, the graph raises a LangGraph interrupt. The run pauses, surfaces the `ContractValidation` or `ValueAssessment` failure details to a human operator, and resumes after a resolution is injected into state. During development, an auto-approve stub bypasses the interrupt.

- **Value Assurance (PM Agent)**: An LLM agent that receives the `SDD`, `DeliveryPlan`, and `ProjectOutput` from Project B. Returns `ValueAssessment`: `meets_value: bool`, `gap_type: Literal["product_gap", "implementation_gap"] | None`, `findings: list[str]`, `recommendation: str`. A `product_gap` routes to the PMO for replanning; an `implementation_gap` routes back to Project B for re-execution.

- **Loop guard**: The `ProgramState` carries `retry_counts: dict[str, int]`. Every re-entrant node increments its counter. When it reaches `max_retries` the node forces the `escalate` route. `max_retries` is configurable via `.env`.

- **LLM configuration**: Per-agent model selection via `PARSER_AGENT_MODEL`, `PMO_AGENT_MODEL`, `CONTRACT_GATE_MODEL`, `PM_AGENT_MODEL` env vars, all defaulting to `claude-sonnet-4-6`. A single `FALLBACK_MODEL` env var sets the global OpenAI fallback model for all agents.

- **Checkpointer**: SQLite checkpointer — persistent across restarts, no infrastructure required. Configured via `CHECKPOINT_DB_PATH` env var, defaulting to `./checkpoints.db`.

- **LangSmith tracing**: Configured via `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT=agile-agent-program` in `.env`.

- **Project structure**: Standard LangGraph layout under `src/program_layer/` with `agents/`, `nodes/`, `schemas/`, `stubs/`, and `config.py`. Package managed with `uv`.

- **CLI entrypoint**: `uv run python -m program_layer.main --sdd path/to/sdd.md`. Loads the file, initialises the graph with a SQLite checkpointer, and streams execution to stdout.

## Testing Decisions

Good tests assert the external behaviour of the system — what goes in, what comes out, and what routing decision was made — without asserting which internal LLM calls were made or how many tokens were used.

- **Full graph tests (primary seam)**: The program graph is invoked end-to-end with dark factory subgraphs replaced by deterministic stubs. Stubs are configured to return fixed `ProjectOutput` values. Tests assert on the final `ProgramState` (e.g. did the run reach `RELEASE`? did a contract failure trigger `rescope`? did hitting `max_retries` produce an interrupt?). This is the highest seam and covers orchestration logic, routing, and retry guards in one place.

- **Contract Gate Agent tests**: Given a fixed `ProjectOutput` and `AcceptanceCriteria`, assert that `ContractValidation.valid` is correct and `ContractValidation.mitigation_route` matches the expected route for the failure type. These tests exercise the LLM's structured output and routing judgment in isolation.

- **PM Agent tests**: Given a fixed `SDD`, `DeliveryPlan`, and `ProjectOutput`, assert that `ValueAssessment.meets_value` and `ValueAssessment.gap_type` are correct. Tests should cover both gap types to ensure routing is driven by the right signal.

No prior art exists in the codebase — this is a greenfield project.

## Out of Scope

- Implementation of Project A (Core API / Pix dark factory)
- Implementation of Project B (Frontend UI App dark factory)
- A REST API or async server wrapper around the program layer
- Multi-worker or distributed execution
- Postgres checkpointer
- Per-agent OpenAI fallback (the fallback is global, not per-agent)
- Budget, timeline, or team-assignment fields in `DeliveryPlan`
- A UI for reviewing escalation interrupts (LangSmith UI is the surface for now)

## Further Notes

The dark factory stubs in `stubs/` should be designed to cover at least three scenarios: a clean happy-path run, a contract failure that triggers each mitigation route, and a retry-limit breach that forces escalation. This makes the stubs reusable as test fixtures without additional mocking infrastructure.

The `escalate` mitigation route and the retry-limit guard both produce LangGraph interrupts. A single interrupt handler node should serve both entry points to avoid duplicating the resume logic.
