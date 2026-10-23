"""The workspace sandbox is Echo's main safety claim, so it is the most tested part."""

import os
from pathlib import Path

import pytest

from echo.tools.filesystem import FilesystemSandboxError, FilesystemToolHandler


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root


@pytest.fixture
def fs(workspace: Path) -> FilesystemToolHandler:
    return FilesystemToolHandler(workspace)


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@pytest.mark.parametrize("bad", ["", "   ", "\t"])
def test_empty_paths_are_rejected(fs, bad):
    with pytest.raises(FilesystemSandboxError):
        fs.resolve_path(bad)


@pytest.mark.parametrize(
    "bad",
    ["../outside.txt", "../../outside.txt", "notes/../../outside.txt", "a/b/../../../outside.txt"],
)
def test_relative_traversal_is_rejected(fs, bad):
    with pytest.raises(FilesystemSandboxError):
        fs.resolve_path(bad)


def test_plain_relative_path_resolves_inside(fs, workspace):
    resolved, shown = fs.resolve_path("notes/today.txt")
    assert inside(resolved, workspace)
    assert shown == "notes/today.txt"


def test_dot_means_the_workspace_itself(fs, workspace):
    resolved, shown = fs.resolve_path(".")
    assert resolved == workspace.resolve()
    assert shown == "./"


def test_absolute_path_inside_the_workspace_is_allowed(fs, workspace):
    target = workspace / "inside.txt"
    resolved, shown = fs.resolve_path(str(target))
    assert resolved == target.resolve()
    assert shown == "inside.txt"


def test_absolute_path_outside_never_escapes(fs, workspace, tmp_path):
    """Depending on the platform an absolute outside path is either refused or
    re-rooted inside the workspace. It must never point outside."""
    outside = tmp_path / "outside.txt"
    try:
        resolved, _ = fs.resolve_path(str(outside))
    except FilesystemSandboxError:
        return
    assert inside(resolved, workspace)


@pytest.mark.skipif(os.name == "nt", reason="POSIX system directories")
@pytest.mark.parametrize("bad", ["/etc/passwd", "/root/.ssh/id_rsa", "/var/log/syslog", "/proc/self/environ"])
def test_system_directories_are_refused(fs, bad):
    with pytest.raises(FilesystemSandboxError):
        fs.resolve_path(bad)


def test_symlink_pointing_outside_is_refused(fs, workspace, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("do not read")
    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    with pytest.raises(FilesystemSandboxError):
        fs.resolve_path("link.txt")


def test_write_then_read_round_trip(fs):
    message = fs.write_file("greeting.txt", "hello, echo")
    assert "11 bytes" in message
    assert fs.read_file("greeting.txt") == "hello, echo"


def test_write_creates_missing_parent_directories(fs, workspace):
    fs.write_file("a/b/c.txt", "x")
    assert (workspace / "a" / "b" / "c.txt").read_text() == "x"


def test_write_outside_the_workspace_writes_nothing(fs, tmp_path):
    with pytest.raises(FilesystemSandboxError):
        fs.write_file("../escaped.txt", "nope")
    assert not (tmp_path / "escaped.txt").exists()


def test_reading_a_missing_file_raises(fs):
    with pytest.raises(FileNotFoundError):
        fs.read_file("missing.txt")


def test_reading_a_directory_raises(fs, workspace):
    (workspace / "folder").mkdir()
    with pytest.raises(IsADirectoryError):
        fs.read_file("folder")


def test_large_files_are_truncated_with_a_notice(fs):
    fs.write_file("big.txt", "a" * 200)
    text = fs.read_file("big.txt", max_bytes=50)
    assert text.startswith("a" * 50)
    assert "File truncated" in text
