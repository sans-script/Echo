# 0001 — Use Git-tracked coordination documents until GitHub is available

- **Date:** 2026-10-13
- **Status:** Accepted for the MVP
- **Participants:** Aaron, Breeze, Clove, Dipper

## Context

The intended canonical coordination system is GitHub Issues and pull requests.
At MVP setup, the configured GitHub CLI credential is invalid and GitHub API
access cannot be verified. Remote Issues, labels, assignment, and project
capabilities therefore cannot reliably coordinate the team.

## Decision

Use the version-controlled `docs/coordination/` directory as the temporary
shared coordination record. Store one task per file and record durable process
decisions separately. Keep the data minimal and non-sensitive. Do not inspect,
modify, or copy another agent's private Codex state.

When GitHub authentication and API access are restored, create Issues for
active tasks, transfer the shared task metadata and relevant findings, and make
Issues and pull requests canonical. Leave the local files as a migration trail
and avoid two independently maintained task states.

## Consequences

- The fallback is simple, durable, reviewable in Git, and works without a
  network connection.
- It has no live assignment, notification, or lock semantics; agents must
  check the files and Git status before substantial work.
- Git merge conflicts are possible if agents edit the same record, so each
  task has a single owner and handoffs must be recorded.
- GitHub-only capabilities such as PR review and issue comments remain
  unavailable until authentication is repaired.
