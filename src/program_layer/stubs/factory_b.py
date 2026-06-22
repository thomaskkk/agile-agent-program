"""Dark Factory B stub — deterministic happy-path ProjectOutput.

Mode controlled via FACTORY_B_MODE env var:
  - "happy"  (default): complete with final product artifact
  - "failed": status=failed to exercise PM Agent gap paths
"""
import os

from program_layer.schemas.models import ProgramState, ProjectOutput


def factory_b(state: ProgramState) -> ProgramState:
    mode = os.getenv("FACTORY_B_MODE", "happy")

    if mode == "failed":
        output = ProjectOutput(
            project_id="project_b",
            artifacts={},
            status="failed",
        )
    else:
        output = ProjectOutput(
            project_id="project_b",
            artifacts={"frontend_bundle": "stub-bundle-v1"},
            status="complete",
        )

    return {"project_b_output": output}
