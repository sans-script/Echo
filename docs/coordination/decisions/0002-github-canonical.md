# 0002 — Make GitHub canonical for active coordination

- **Date:** 2026-10-13
- **Status:** Accepted
- **Participants:** Aaron, Breeze, Clove, Dipper
- **Related task:** [TASK-002](https://github.com/sans-script/echo/issues/2)

## Context

GitHub CLI authentication and API access have been verified for
`sans-script/echo`. The temporary local-fallback condition in Decision 0001
no longer applies.

## Decision

Use GitHub Issues for active tasks, ownership, state, blockers, and handoffs;
use pull requests for code review. Keep `docs/coordination/` for the runbook,
durable decisions, and historical fallback artifacts. Do not create a Project
board yet.

## Consequences

- Existing completed local TASK-001 remains historical evidence only.
- TASK-002 is the first GitHub-native operational task.
- During a future GitHub outage, use the documented local fallback and migrate
  active records back to Issues after service is restored.
