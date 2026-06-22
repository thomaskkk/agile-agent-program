## Codebase orientation

- **Language & package manager**: Python 3.12+, managed with `uv` (`uv sync` to install, `uv run` to execute)
- **Entry point**: `uv run python -m program_layer.main --sdd path/to/sdd.md`
- **Run tests**: `uv run pytest`
- **Domain glossary**: `CONTEXT.md` — use these terms in code, issues, and discussions; do not use the aliases-to-avoid listed there.
- **Architecture decisions**: `docs/adr/` — read ADRs before modifying graph structure, checkpointer, or factory integration
- **Architecture diagram**: `layout.md` (Mermaid source)
- **Source root**: `src/program_layer/` — agents in `agents/`, schemas in `schemas/`, dark factory stubs in `stubs/`, graph assembly in `graph.py`

## Agent skills

### Issue tracker

Issues live in Jira Cloud. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role label vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo — `UBIQUITOUS_LANGUAGE.md` serves as `CONTEXT.md`; no `docs/adr/` directory exists yet. See `docs/agents/domain.md` for the general convention.
