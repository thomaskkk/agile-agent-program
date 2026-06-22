# SQLite for graph state persistence

We use SQLite as the LangGraph checkpointer rather than Postgres. A Delivery Run can be interrupted (Escalation) and must survive process restarts; we need durable state. SQLite was chosen because it requires zero infrastructure — no separate database process, no credentials to manage, no migration tooling — which makes local development and CI identical to production for this layer. Postgres is explicitly out of scope (see PRD). If the deployment target changes to a multi-worker setup, this decision should be revisited.
