# Coordination MVP Architecture Meeting — 2026-10-13

- **Participants:** Aaron, Breeze, Clove, Dipper
- **Topics:** shared state, SQLite safety, GitHub workflow, ownership, and
  the local prototype.

## Findings

- The installed GitHub CLI has an invalid credential and cannot reach the API,
  so remote Issues and pull requests could not be used or verified.
- Private Codex SQLite databases use WAL and can contain sensitive context.
  A raw copy of an active main database is not a reliable snapshot; a brief
  read-only query or an owner-authorized SQLite online backup is the safe
  exception, not routine team communication.
- The repository had no existing coordination convention.

## Decision

Use Git-tracked coordination documents temporarily. When GitHub access is
restored, Issues and pull requests become canonical, with local files retained
only as a migration trail. Private Codex state is never routine shared state.

## Disagreement and resolution

Dipper proposed a single central task ledger to prevent concurrent edits;
Breeze proposed one file per task to avoid that bottleneck. The team adopted
one task file per task, dated per-agent handoffs, and Aaron-only authoritative
status transitions. This preserves a single current status while keeping most
contributions in disjoint files.

## Action items

- **Aaron:** commit the reviewed MVP and migrate active work to GitHub once
  authentication is restored.
- **All agents:** read current tasks and recent decisions before substantial
  work; create dated handoffs instead of sharing private context.
