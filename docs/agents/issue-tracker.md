# Issue tracker: Jira Cloud

Issues for this repo live in Jira Cloud (`*.atlassian.net`). Use the Jira REST API or a `jira` CLI tool for all operations.

## Conventions

- **Create an issue**: `POST /rest/api/3/issue` with `project`, `issuetype`, `summary`, and `description` fields. Use a `jira` CLI wrapper if available.
- **Read an issue**: `GET /rest/api/3/issue/{issueIdOrKey}` — returns fields, labels, status, and comments.
- **List issues**: JQL via `GET /rest/api/3/search?jql=...` (e.g. `project = PROJ AND labels = "needs-triage" ORDER BY created DESC`).
- **Comment on an issue**: `POST /rest/api/3/issue/{issueIdOrKey}/comment`.
- **Apply labels**: `PUT /rest/api/3/issue/{issueIdOrKey}` with `{ "update": { "labels": [{ "add": "label-name" }] } }`.
- **Transition status / close**: `POST /rest/api/3/issue/{issueIdOrKey}/transitions` with the target transition ID.

**Auth**: Set `JIRA_BASE_URL` (e.g. `https://yourcompany.atlassian.net`), `JIRA_USER_EMAIL`, and `JIRA_API_TOKEN` as environment variables. Use HTTP Basic Auth: email + API token.

## Pull requests as a triage surface

Not applicable — Jira is not a code-hosting platform; PRs are managed separately.

## When a skill says "publish to the issue tracker"

Create a Jira issue via `POST /rest/api/3/issue`.

## When a skill says "fetch the relevant ticket"

Run `GET /rest/api/3/issue/{issueIdOrKey}` with `?fields=summary,description,labels,status,comment`.
