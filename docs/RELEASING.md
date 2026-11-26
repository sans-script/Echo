# Release Process

Echo releases are built and published by the GitHub Actions workflow in `.github/workflows/release.yml`.

## Version Format

Stable releases use Semantic Versioning tags in the form `vMAJOR.MINOR.PATCH`, for example `v0.1.0`. The workflow rejects tags that do not match this format. Pre-release and build-metadata tags are not currently supported.

## Publish a Release

1. Confirm the changes intended for release are on `main` and the working tree is clean.
2. Create and push the version tag for the release commit:

   ```powershell
   git switch main
   git pull --ff-only
   git tag -a v0.1.0 -m "Echo v0.1.0"
   git push origin v0.1.0
   ```

3. GitHub Actions checks out the tagged commit on a Windows runner, runs `build.ps1`, and creates a GitHub Release with generated notes.
4. Download `Echo-v0.1.0-portable.zip` and its `.sha256` checksum from that release. Verify the checksum before distributing or installing the package. The package still requires the WebView2 Runtime and a supported Python/CLI setup.

Replace `v0.1.0` with the intended version in both commands. Choose the version according to the change: increment PATCH for compatible fixes, MINOR for backward-compatible features, and MAJOR for incompatible changes. Before publishing, review the release commit and confirm the generated package does not contain local profiles, logs or credentials.

The initial release line is `0.x`; while the major version is zero, compatibility is not guaranteed between minor releases. The workflow does not create a version tag automatically. A pushed tag identifies the source commit; the Action performs the Windows build, writes a SHA-256 checksum, and publishes the tagged version.
