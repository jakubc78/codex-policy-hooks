"""Approve only scoped creation of a new Git worktree and branch."""

import os
import re
import stat
import subprocess
from pathlib import Path

from _helpers import contains_shell_operators, cwd_is_within_project
from dispatcher import Context, Decision, Result

NAME = "git_worktree_safe"
PRIORITY = 57
GIT = "/usr/bin/git"
SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
BRANCH_PREFIX = re.compile(r"[A-Za-z][A-Za-z0-9_-]*/\Z")
DEFAULT_PREFIXES = ["codex/", "fix/", "feat/"]
DEFAULT_BASE_REFS = ["origin/main"]


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run only read-only built-in Git commands, with inherited Git overrides removed."""
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    environment.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    })
    try:
        return subprocess.run(
            [GIT, "-C", str(cwd), *args],
            capture_output=True, text=True, timeout=5, env=environment, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _plain_absolute_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.startswith("/"):
        return None
    if any(part in ("", ".", "..") for part in value[1:].split("/")):
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    return Path(value)


def _no_symlink_components(path: Path) -> bool:
    current = Path("/")
    for part in path.parts[1:]:
        current /= part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                return False
        except FileNotFoundError:
            return False
    return True


def _safe_parent(parent: Path, *, temporary: bool) -> bool:
    try:
        info = parent.stat()
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode):
        return False
    if temporary:
        # Some sandboxes map the host's root-owned /tmp to the overflow uid.
        return (parent == Path("/tmp") and info.st_uid in (0, 65534)
                and bool(info.st_mode & stat.S_ISVTX))
    return (info.st_uid == os.getuid()
            and not bool(info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)))


def _valid_base(root: Path, base: object) -> bool:
    if not isinstance(base, str) or not base.startswith("origin/") or base == "origin/HEAD":
        return False
    result = _git(root, "check-ref-format", f"refs/remotes/{base}")
    return result is not None and result.returncode == 0


def _valid_config(config: dict) -> tuple[Path, list[Path], bool, list[str], list[str]] | None:
    root = _plain_absolute_path(config.get("project_root"))
    roots_value = config.get("worktree_roots")
    allow_tmp = config.get("allow_tmp_worktrees", False)
    tmp_prefix = config.get("tmp_name_prefix", "qdr-")
    prefixes = config.get("allowed_branch_prefixes", DEFAULT_PREFIXES)
    bases = config.get("allowed_base_refs", DEFAULT_BASE_REFS)
    if (
        config.get("enabled") is not True
        or root is None
        or not root.is_dir()
        or not _no_symlink_components(root)
        or not isinstance(roots_value, list)
        or type(allow_tmp) is not bool
        or tmp_prefix != "qdr-"
        or not isinstance(prefixes, list) or not prefixes
        or not all(isinstance(p, str) and BRANCH_PREFIX.fullmatch(p) for p in prefixes)
        or not isinstance(bases, list) or not bases
        or not all(_valid_base(root, b) for b in bases)
    ):
        return None
    roots = [_plain_absolute_path(value) for value in roots_value]
    if any(path is None for path in roots) or (not roots and not allow_tmp):
        return None
    if any(path == root or root in path.parents or path in root.parents for path in roots):
        return None
    if any(not path.is_dir() or not _no_symlink_components(path) or
           not _safe_parent(path, temporary=False) for path in roots):
        return None
    return root, roots, allow_tmp, prefixes, bases


def evaluate(ctx: Context, config: dict) -> Result:
    if ctx.argv[:3] != ["git", "worktree", "add"]:
        return Result(Decision.ABSTAIN)
    command = ctx.command
    if (
        not command or len(ctx.argv) != 7 or ctx.argv[3] != "-b"
        or contains_shell_operators(command)
        or any(char in command for char in "$`\n\r;&|<>\\")
    ):
        return Result(Decision.ABSTAIN, "unsupported worktree syntax")
    branch, destination_value, base = ctx.argv[4:7]
    if branch.startswith("-") or destination_value.startswith("-"):
        return Result(Decision.ABSTAIN, "option-like argument")

    validated = _valid_config(config)
    if validated is None:
        return Result(Decision.ABSTAIN, "invalid worktree configuration")
    root, roots, allow_tmp, prefixes, bases = validated
    if not cwd_is_within_project(ctx.cwd, root) or not (root / ".git").is_dir() or (root / ".git").is_symlink():
        return Result(Decision.ABSTAIN, "outside primary repository")
    identity = _git(ctx.cwd, "rev-parse", "--show-toplevel", "--absolute-git-dir",
                    "--is-inside-work-tree", "--is-bare-repository")
    if identity is None or identity.returncode != 0:
        return Result(Decision.ABSTAIN, "cannot identify Git repository")
    lines = identity.stdout.splitlines()
    if lines != [str(root), str(root / ".git"), "true", "false"]:
        return Result(Decision.ABSTAIN, "unexpected Git repository")

    if not any(branch.startswith(prefix) for prefix in prefixes):
        return Result(Decision.ABSTAIN, "branch prefix not allowed")
    valid_branch = _git(root, "check-ref-format", "--branch", branch)
    if valid_branch is None or valid_branch.returncode != 0:
        return Result(Decision.ABSTAIN, "invalid Git branch name")
    existing = _git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    if existing is None or existing.returncode != 1:
        return Result(Decision.ABSTAIN, "branch exists or cannot be checked")
    if base not in bases:
        return Result(Decision.ABSTAIN, "base reference not allowed")
    base_result = _git(root, "show-ref", "--verify", "--quiet", f"refs/remotes/{base}")
    if base_result is None or base_result.returncode != 0:
        return Result(Decision.ABSTAIN, "base reference unavailable")
    symbolic = _git(root, "symbolic-ref", "-q", f"refs/remotes/{base}")
    if symbolic is None or symbolic.returncode != 1:
        return Result(Decision.ABSTAIN, "symbolic base reference")

    destination = _plain_absolute_path(destination_value)
    if (destination is None or os.path.lexists(destination)
            or root == destination or root in destination.parents
            or SAFE_COMPONENT.fullmatch(destination.name) is None):
        return Result(Decision.ABSTAIN, "invalid or existing destination")
    parent = destination.parent
    if not _no_symlink_components(parent):
        return Result(Decision.ABSTAIN, "symlinked destination parent")
    dedicated = parent in roots and _safe_parent(parent, temporary=False)
    temporary = (
        allow_tmp and parent == Path("/tmp")
        and destination.name.startswith("qdr-")
        and SAFE_COMPONENT.fullmatch(destination.name[4:]) is not None
        and _safe_parent(parent, temporary=True)
    )
    if not dedicated and not temporary:
        return Result(Decision.ABSTAIN, "destination outside approved roots")
    return Result(Decision.ALLOW, "scoped new Git worktree and branch")
