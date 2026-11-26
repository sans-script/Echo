# Echo

Echo is a local Windows dashboard for monitoring Codex, Antigravity and Claude Code sessions, usage and conversations. It can also send prompts to those CLIs and coordinate agents in a shared room.

Echo turns the increasingly artisanal task of checking which coding account still has quota into a local dashboard. It centralizes account visibility; it does not centralize or bypass provider limits. Subscription arithmetic remains between you and your providers.

## Capabilities

- Aggregate agent status, recent activity, process usage and reported quota windows.
- Inspect recorded conversations and continue them through the corresponding CLI.
- Send prompts with a selected model, reasoning effort, working directory and provider access mode.
- Coordinate agents through mentions and optional hand-offs, with turn limits and a ping-pong guard.
- Browse, rename, archive and delete supported conversation records. Antigravity's database is not modified; its conversations can only be hidden in Echo.
- Optionally use ElevenLabs for speech playback and transcription.

## Architecture

```text
Windows Forms host (Echo.cs)
  |-- WebView2 interface (ui/)
  |-- Python status collector (snapshot.py)
  |-- CLI invocation bridge (send.py)
  `-- Conversation manager (convs.py)
```

The C# host launches the Python helpers on Windows or through WSL. The collector streams newline-delimited JSON snapshots to the host, which forwards them to the WebView2 page. User actions are sent back to the host and handled by the appropriate helper or provider CLI.

| Component | Responsibility |
| --- | --- |
| `Echo.cs` | Hosts WebView2, manages per-user settings, starts helpers and handles optional ElevenLabs requests. |
| `ui/index.html` | Renders the dashboard, agent details, chat, group coordination and settings. |
| `snapshot.py` | Reads provider state and reports usage snapshots. Antigravity's SQLite database is opened read-only. It can create or migrate Echo-owned group-chat logs. |
| `send.py` | Starts the selected provider CLI with the user's prompt and options. |
| `convs.py` | Lists and opens conversation records, and applies provider-specific delete or hide behavior. |
| `agents.json` | Optional local mapping of display names and roles to provider profile directories. |

## Data Sources and Limits

Echo uses the local files and usage interfaces already available to the provider CLIs. Data freshness and detail vary by provider; quota figures are best effort and may be incomplete or stale.

Antigravity usage is queried through its `/usage` command without a model prompt. Codex usage is derived from local session data. Claude Code usage is requested from its authenticated usage endpoint using the credential maintained by the CLI.

Echo does not rotate accounts, automatically fail over to an account with remaining quota, reset limits or enqueue work for another profile. Sending is initiated by the user and performed by the selected provider CLI under its existing sign-in. A quota monitor is not a quota bypass; it is just less spreadsheet.

## Security and Privacy

The collector reads local files and process state and makes network requests to provider usage interfaces. Prompt execution follows the selected CLI's normal network behavior. Optional voice requests send the requested text or audio to ElevenLabs. Echo does not send product analytics or telemetry to an Echo service.

Provider credentials remain in their provider homes. An optional ElevenLabs key is encrypted with Windows DPAPI for the current Windows user. Do not commit `agents.json`, chat logs, credentials, API keys or real account data. The repository ignores common local configuration and credential files; demo data is synthetic.

Access modes are passed to the provider CLI. The default is **Workspace Write** for Codex, **Accept Edits** for Claude Code, and **Full Access** for Antigravity. The Antigravity default skips its CLI permission prompts. Group chat also offers **Full Access**, which sends eligible hand-offs automatically. Review the selected mode and working directory before sending; consult the CLI documentation for exact flag behavior.

See the [Security Policy](SECURITY.md) for local file and network behavior, credential handling and private vulnerability reporting.

## Requirements

- Windows 10 or 11 with the Microsoft Edge WebView2 Runtime.
- .NET Framework 4.8 compiler, included with Windows.
- Python 3.10 or newer on Windows or in WSL.
- One or more installed and signed-in CLIs: `codex`, `agy` (Antigravity) or `claude` (Claude Code).

## Build and Install

Run from PowerShell:

```powershell
./build.ps1
```

The build script compiles Echo, stops a running Echo instance, installs it under `%LOCALAPPDATA%\Programs\Echo`, updates the Echo Start Menu shortcut, and creates `dist\Echo-portable.zip`.

Without a configuration file, Echo checks its built-in provider home list and keeps the directories that exist. To monitor separate Codex or Antigravity accounts, prepare and sign in to each account using that CLI's supported profile or home-directory mechanism. Give every profile a distinct home, then map each one in an `agents.json` beside `snapshot.py`:

```json
{
  "agyQuotaEvery": 300,
  "agents": [
    { "team": "Codex", "name": "CodexWork", "role": "Implementation", "home": "~/.codex-work" },
    { "team": "Codex", "name": "CodexPersonal", "role": "Research", "home": "~/.codex-personal" },
    { "team": "Antigravity", "name": "GeminiWork", "role": "Review", "home": "~/.gemini-work" },
    { "team": "Antigravity", "name": "GeminiPersonal", "role": "Research", "home": "~/.gemini-personal" }
  ]
}
```

Each entry's `team` must be `Codex`, `Antigravity`, or `Claude Code`; `name` and `role` label its dashboard card, and `home` points to that profile's existing provider data. Give entries unique names so the UI and conversation actions can identify them unambiguously. For Codex, `home` is the directory containing that profile's `auth.json` and `sessions/`; Echo launches the CLI with that path as `CODEX_HOME`. For Antigravity, `home` is the directory passed to `agy --gemini_dir`, with the account data under its `antigravity-cli/` subdirectory. Echo does not copy credentials or create signed-in profiles.

Use paths visible to the configured Python runtime: Windows paths for native Python, or Linux paths for WSL. For example, `~/.codex-work` in a WSL config means the home directory inside that WSL distribution, not a Windows path with the same spelling.

Claude Code has a current limitation: its configured home is used to read sessions and usage credentials, while sends use the Claude CLI configuration inherited by Echo. Echo does not set `CLAUDE_CONFIG_DIR` separately for each entry, so listing multiple Claude homes alone does not isolate their sign-ins.

The optional `agyQuotaEvery` value sets Antigravity usage polling in seconds. It defaults to `300`; values below `60` are clamped to `60`. Keep `agents.json` local because it maps your account profiles. In **Settings > Installation**, configure the Python command and script location for Windows or WSL.

## Development Checks

The repository includes offline checks for collector parsing, conversation handling and group-chat UI logic:

```powershell
python test_snapshot.py
python tests/convs_check.py
node tests/room_check.js ui/index.html
```

## Project Documentation

- [Architecture and Data Flow](docs/ARCHITECTURE.md)
- [Security and Privacy](SECURITY.md)
- [Contribution Guidelines](CONTRIBUTING.md)
- [Release Process](docs/RELEASING.md)
- [MIT License](LICENSE)
- [Third-Party Notices](ui/NOTICE.txt)

## Contributions

Bug reports, focused fixes and documentation improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for issue and pull request guidance.

## Third-Party Components

The repository includes Geist and Geist Mono fonts under the SIL Open Font License, KaTeX under MIT, Codex and Antigravity icons from `@lobehub/icons-static-svg` under MIT, and WebView2 SDK assemblies under Microsoft's license. See [ui/NOTICE.txt](ui/NOTICE.txt) for notices and license details.

Echo is an independent project and is not affiliated with OpenAI, Google, Anthropic or ElevenLabs. Their product names and marks belong to their respective owners.

The project is licensed under MIT. Bundled third-party components retain their own licenses; see [ui/NOTICE.txt](ui/NOTICE.txt).
