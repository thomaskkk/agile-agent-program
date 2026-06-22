"""Dark Factory A stub — deterministic ProjectOutput scenarios.

Mode is controlled via the FACTORY_A_MODE environment variable:

  happy           (default) complete output with all required artifacts.
  update_contract complete status but artifact value signals it needs contract
                  revision (e.g. schema version is a draft placeholder).
  rollback        complete status with entirely wrong artifacts — required
                  artifact_key is absent, indicating fundamental rework.
  rescope         failed status with a partial artifact indicating the project
                  boundary was exceeded and scope must be renegotiated.
  repeated_failure complete status, always-wrong artifact to trigger the loop
                  guard after MAX_RETRIES re-entries.
  failed          status=failed, no artifacts (legacy alias for rollback-like
                  behaviour in earlier tests).
  partial         missing some artifacts (legacy; used by existing tests).
"""
import os

from program_layer.schemas.models import ProjectOutput, ProgramState


def factory_a(state: ProgramState) -> ProgramState:
    mode = os.getenv("FACTORY_A_MODE", "happy")

    if mode == "update_contract":
        output = ProjectOutput(
            project_id="project_a",
            artifacts={"api_schema": "draft-schema-v0-needs-revision"},
            status="complete",
        )
    elif mode == "rollback":
        output = ProjectOutput(
            project_id="project_a",
            artifacts={"wrong_artifact": "incompatible-output"},
            status="complete",
        )
    elif mode == "rescope":
        output = ProjectOutput(
            project_id="project_a",
            artifacts={"api_schema": "partial"},
            status="failed",
        )
    elif mode == "repeated_failure":
        output = ProjectOutput(
            project_id="project_a",
            artifacts={"api_schema": "broken-schema"},
            status="complete",
        )
    elif mode == "failed":
        output = ProjectOutput(
            project_id="project_a",
            artifacts={},
            status="failed",
        )
    elif mode == "partial":
        output = ProjectOutput(
            project_id="project_a",
            artifacts={"api_schema": "stub-schema-v1"},
            status="complete",
        )
    else:
        output = ProjectOutput(
            project_id="project_a",
            artifacts={
                "api_schema": "stub-schema-v1",
                "event_contract": "stub-events-v1",
                "data_model": "stub-data-model-v1",
                "sla": "stub-sla-v1",
            },
            status="complete",
        )

    return {"project_a_output": output}
