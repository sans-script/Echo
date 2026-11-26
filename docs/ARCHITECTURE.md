# Architecture

Echo is a Windows desktop shell around a local web interface and a small set of Python helpers. The helpers run beside the provider CLIs, on Windows or in WSL, and communicate with the host through newline-delimited JSON over standard output and input.

## Components

| Component | Responsibility |
| --- | --- |
| `Echo.cs` | Hosts WebView2, stores per-user settings, launches the collector and selected CLI commands, and handles optional ElevenLabs requests. |
| `ui/index.html` | Renders the dashboard, agent details, conversations, group chat and settings. |
| `snapshot.py` | Emits agent activity, usage and process data. Its watch mode sends a fresh snapshot every few seconds. |
| `send.py` | Converts a user action into the appropriate Codex, Antigravity or Claude Code CLI invocation. |
| `convs.py` | Lists and opens conversations, and implements provider-specific delete or hide behavior. |
| `agents.json` | Optional local mapping from display names and roles to provider homes. It is intentionally untracked. |

## Data Flow

1. Echo starts `snapshot.py --watch` using the Python command and script location configured in Settings.
2. The collector reads provider files and local process state, then writes one JSON snapshot per line.
3. Echo forwards snapshots into WebView2. The page renders the cards and quota indicators locally.
4. When a user sends a message, Echo starts `send.py` with the selected agent and options. The prompt travels over standard input; the provider's own CLI performs the actual request with its existing sign-in.
5. Conversation operations are handled by `convs.py`, with behavior varying by provider because their session formats and deletion support differ.

Antigravity usage is queried with `agy -p /usage --output-format json`, which requests usage information without a model prompt. Codex usage is inferred from local session data. Claude Code usage is read through its usage endpoint with the local CLI credential. These sources differ, so values and freshness can differ too.

## Local Configuration

Without `agents.json`, the collector uses its built-in provider home list and keeps entries whose directories exist. An optional `agents.json` beside the Python scripts can define display names and homes for multiple profiles. It also accepts `agyQuotaEvery`, the Antigravity usage polling interval in seconds; values below 60 are clamped to 60 and the default is 300. Settings store the Python command, scripts location and zoom per Windows user under `%LOCALAPPDATA%\Echo`.

Echo-owned conversation logs are stored under `chat/` beside the scripts. The collector may move an older single-room log into `chat/rooms/`. Sending also creates per-agent logs and process markers there. The collector is read-only with respect to provider homes; explicit conversation deletion can remove Codex or Claude Code session data, as described in the [Security Policy](../SECURITY.md).

## Build

`build.ps1` compiles the C# host with the .NET Framework compiler, copies the UI and Python scripts into the install folder, and creates a portable ZIP. WebView2 assemblies are included under `lib/`; the WebView2 Runtime is a machine prerequisite.
