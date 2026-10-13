# Coordination Protocol

GitHub Issues and pull requests are the canonical task, ownership, status,
blocker, and review records for this repository. This Git-tracked directory is
the durable runbook, decision record, and migration history. Use it as a
temporary fallback only when GitHub is unavailable.

## Protocol

- Before substantial work, read open GitHub Issues, relevant pull requests,
  and recent decision records to avoid duplicate work.
- Create one Issue per task. Its title starts with `TASK-NNN`, and it carries
  exactly one status label plus an optional agent label. The issue owner does
  the work; Aaron reconciles status changes after considering comments.
- Use issue comments for handoffs, findings, and status requests. Preserve
  conflicting requests and record the resolution in a comment.
- Use a branch named `task-<issue-number>-<slug>` for code changes and link
  its pull request with `Fixes #<issue-number>`. Dipper reviews the pull
  request before it is merged or the task is marked `DONE`.
- Use `decisions/` only for durable architectural or process decisions that
  affect later work. Keep each decision in a separate numbered file.
- Write all coordination records in English.

Use `status:ready`, `status:in-progress`, `status:blocked`, or
`status:review`. Task ownership is explicit: an agent must not take over an
owned task without a recorded issue comment.

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
editors must check Git status and any relevant local fallback file before
editing; avoid overwriting another agent's changes and resolve conflicts
explicitly.

## GitHub Outage Fallback

If GitHub is unavailable, create a local `tasks/TASK-NNN.md` and dated
`handoffs/` files using the preserved TASK-001 pattern. When access returns,
create an Issue for every active local task, link it, and cease local status
updates. Do not maintain two independent sources of truth.

The label set is intentionally small: status labels and `agent:*` ownership
labels. Do not create a GitHub Project unless issue and pull-request views are
no longer sufficient.
