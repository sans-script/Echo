# Security and Privacy

Echo is designed as a local dashboard for account data already present on your computer. It is not a credential manager or a quota workaround.

## What Echo Reads

- Codex session and authentication files in configured Codex homes.
- Antigravity files and its local SQLite database. The database is opened read-only.
- Claude Code session files and credentials needed to request usage information.
- Local process information for supported agent CLIs.
- Optional `agents.json` configuration beside the Python scripts.

The status collector does not write to provider homes. It can create or migrate Echo-owned group-chat files under `chat/rooms/`. Sending prompts also creates Echo-owned logs and process markers under `chat/`. Echo's conversation tools can delete provider-owned Codex and Claude Code session data when you explicitly choose Delete; Claude session sidecar directories may be removed with the selected transcript. Antigravity's database is opened read-only, so Echo hides Antigravity rows locally instead of deleting their provider records. Deleting a group conversation removes its Echo-owned log.

Echo also writes its configuration and diagnostic logs under `%LOCALAPPDATA%\Echo`. The optional ElevenLabs credential is stored there in a DPAPI-protected file. During startup, the host may copy its bundled Python helpers into the configured scripts directory; it does not overwrite `agents.json` or chat logs.

## What Echo Sends

Status collection reads local files and process state, and makes network requests for provider usage data. In particular, Claude usage is requested from Anthropic's usage endpoint using a credential maintained by Claude Code. Antigravity usage is queried through the `agy` CLI. Sending a prompt starts the selected provider CLI, which sends the prompt using that CLI's normal account and network behavior. Optional voice features send requested text or audio to ElevenLabs. Echo itself does not send product analytics or telemetry to an Echo service.

## Credentials

Provider credentials remain in the provider homes configured for the CLIs. The optional ElevenLabs key is encrypted with Windows DPAPI for the current Windows user and is not returned to the page after saving. Do not commit `agents.json`, chat logs, credentials, API keys or real screenshots of account data.

The repository ignores local `agents.json`, `chat/`, build output, credentials with common extensions and audit notes. Ignore rules are a convenience, not a secret scanner: review staged files before committing. Demo images use generated data; do not publish captures of real account information.

## Access Modes

When sending a prompt, Echo passes the selected access mode to the provider CLI. Full access modes can bypass CLI approval or sandbox safeguards. Review the selected mode and working folder before sending, and consult the provider CLI's own documentation for the exact behavior of its flags.

Current defaults are Workspace Write for Codex, Accept Edits for Claude Code, and Full Access for Antigravity. Antigravity's default skips its CLI permission prompts. Group chat's Full Access mode can send eligible agent hand-offs automatically.

## Usage Limits

Usage figures depend on provider interfaces and local session data and may be incomplete or stale. Echo reports limits; it does not switch accounts, queue work for a different account, or alter rate limits. Account selection and provider terms remain your responsibility.

## Reporting a Vulnerability

Do not report vulnerabilities in a public issue. Use [GitHub's private vulnerability reporting form for Echo](https://github.com/sans-script/Echo/security/advisories/new). Private vulnerability reporting is enabled for this repository.

Include a concise description, affected commit or build, impact, and steps to reproduce or a proof of concept. Use synthetic or redacted data. Never attach credentials, tokens, private transcripts, account screenshots or unredacted logs. The repository does not publish a response-time target; use the private advisory for follow-up and disclosure coordination.

Echo has no published release or version support matrix. Identify the affected commit or local build in a report.
