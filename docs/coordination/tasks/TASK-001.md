# TASK-001 — Establish coordination MVP

- **Owner:** Clove
- **Status:** DONE
- **GitHub Issue:** Pending GitHub authentication and API access

## Scope

Establish the smallest Git-tracked, documentation-only coordination fallback
for this repository. It must provide a discoverable team protocol, an explicit
task record, and a durable record of the fallback decision.

## Acceptance Criteria

- `docs/coordination/README.md` defines the local protocol, security boundary,
  concurrent-editing caution, and migration to GitHub Issues and pull requests.
- One task file records a title, owner, status, scope, acceptance criteria, and
  handoff area.
- One decision record explains why the local fallback exists and its
  consequences.
- The records are English-only and contain no copied agent-private context or
  credentials.

## Handoff

Clove will hand this task to Dipper for an independent documentation and
security-boundary review after the files are created. Aaron decides whether the
MVP is accepted and coordinates migration when GitHub access is restored.

## Activity Log

- 2026-10-13: Task created; documentation implementation started by Clove.
- 2026-10-13: Breeze supplied shared-finding evidence in
  `handoffs/TASK-001-breeze-20261013.md` and requested review.
- 2026-10-13: Dipper independently reviewed the records in
  `handoffs/TASK-001-dipper-20261013.md` and passed the acceptance criteria.
- 2026-10-13: Aaron accepted the MVP and transitioned the task to `DONE`.
