# Coordination Protocol (Local Fallback)

This directory is the temporary, Git-tracked coordination record while GitHub
authentication or network access is unavailable. When GitHub is available,
GitHub Issues and pull requests are the canonical task and review records.

## Protocol

- Create one Markdown file per task in `tasks/`, named `TASK-NNN.md`.
- Before substantial work, read the task files and recent decision records to
  avoid duplicate work.
- Each task records its title, owner, status, scope, acceptance criteria, and
  handoff information. The task owner performs the work; Aaron records
  authoritative status transitions after considering dated contributor
  handoffs. Contributors do not edit another agent's entry or overwrite a
  task's status.
- Put evidence, review results, and requested status changes in a new dated
  file under `handoffs/`, named `TASK-NNN-<agent>-<YYYYMMDD>.md`. Preserve
  conflicting requests; Aaron resolves them with a new transition in the task
  record.
- Use `decisions/` only for durable architectural or process decisions that
  affect later work. Keep each decision in a separate numbered file.
- Write all coordination records in English.

Suggested task statuses are `READY`, `IN PROGRESS`, `BLOCKED`, `IN REVIEW`,
and `DONE`. Task ownership is explicit: an agent must not take over an owned
task without recording the agreed handoff in that task file.

## Security and Boundaries

Only project-shared, non-sensitive coordination information belongs here:
task intent, ownership, status, public technical findings, decisions, links to
commits or pull requests, and reproducible validation results.

Do not copy, commit, or link agent-private Codex state. This includes
`auth.json`, `config.toml`, `state_*.sqlite`, `logs_*.sqlite`,
`memories_*.sqlite`, `queue_*.sqlite`, `goals_*.sqlite`, session histories,
shell snapshots, tokens, credentials, or personal paths. Do not use this
directory to transfer secrets or raw private conversation context.

The documents are collaboration metadata, not a lock service. Concurrent
editors must check Git status and the current task file before editing; avoid
overwriting another agent's changes and resolve conflicts explicitly.

## Migration to GitHub

Once GitHub authentication and API access are verified, create a GitHub Issue
for each active local task and put its URL in the corresponding task file.
Carry over only the shared task metadata and durable findings. Thereafter the
Issue is canonical for status, assignment, discussion, and blockers; pull
requests are canonical for code review. Close or mark the local task `DONE`
with the Issue link rather than maintaining two independent sources of truth.

Use a lightweight label set at first: status labels (`status:ready`,
`status:in-progress`, `status:blocked`, `status:review`) and optional agent
labels. Do not create a GitHub Project unless the issue and pull-request views
are no longer sufficient.
