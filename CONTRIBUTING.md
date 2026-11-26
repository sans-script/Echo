# Contributing

Thanks for helping keep Echo useful, predictable and slightly less spreadsheet-shaped. Contributions should improve the local monitoring and coordination workflow without obscuring where provider data comes from or what a send action will do.

## Before You Start

- Search existing issues and pull requests for related work.
- For larger changes, open an issue first to discuss scope and compatibility.
- Keep reports and examples in English, consistent with the repository.
- Never include provider credentials, API keys, account identifiers, private transcripts or unredacted logs.

## Reporting Issues

For a bug report, include the steps to reproduce, expected behavior, observed behavior and relevant software versions. Redact paths, account names and message content from logs. For security concerns, follow the private reporting guidance in [SECURITY.md](SECURITY.md); do not post vulnerabilities or secrets in a public issue.

## Making Changes

- Keep changes focused and follow the existing code style and architecture.
- Explain new dependencies and provider-specific behavior in the pull request.
- Preserve read-only access to provider data where possible. If a change writes or deletes provider data, document the behavior and require a clear user action.
- Update the README or technical documentation when setup, data handling or user-visible behavior changes.
- Use synthetic data in examples and interface captures.

## Local Validation

Run the checks relevant to your change and include their results in the pull request:

```powershell
python test_snapshot.py
python tests/convs_check.py
node tests/room_check.js ui/index.html
```

If a check cannot run in your environment, say which one and why. Do not claim an unrun check passed. The `build.ps1` script compiles Echo, stops a running Echo instance, updates the installation and Start Menu shortcut, and creates a portable package.

## Pull Requests

Use a concise title and describe the problem, approach, user-visible impact and validation performed. Link related issues when applicable. Keep unrelated formatting or generated files out of the change. A maintainer will review the proposal and follow up if changes are needed.

## Licensing

By contributing, you agree that your contribution is provided under the repository's [MIT License](LICENSE). Keep existing third-party copyright and license notices intact.
