import re

from _helpers import (
    contains_shell_operators,
    cwd_is_within_project,
    resolve_project_root,
)

from dispatcher import Context, Decision, Result

NAME = "git_ls_remote_safe"
PRIORITY = 55

ALLOWED_OPTIONS = {
    "--heads",
    "--tags",
    "--refs",
    "--symref",
    "--exit-code",
    "--quiet",
    "-q",
}
REF_PATTERN = re.compile(r"[A-Za-z0-9_./*?+-]+")


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv
    if argv[:2] != ["git", "ls-remote"]:
        return Result(Decision.ABSTAIN)

    command = ctx.command
    if (
        not command
        or contains_shell_operators(command)
        or any(char in command for char in ("$", "`", "\n", "\r"))
    ):
        return Result(Decision.ABSTAIN, "shell expansion or compound command")

    project_root = resolve_project_root(config)
    if project_root is None or not cwd_is_within_project(ctx.cwd, project_root):
        return Result(Decision.ABSTAIN, "outside configured project root")

    allowed_remotes = config.get("allowed_remotes", ["origin"])
    if not isinstance(allowed_remotes, list) or not all(
        isinstance(remote, str) for remote in allowed_remotes
    ):
        return Result(Decision.ABSTAIN, "invalid remote configuration")

    index = 2
    while index < len(argv) and argv[index] in ALLOWED_OPTIONS:
        index += 1
    if index < len(argv) and argv[index] == "--":
        index += 1
    if index >= len(argv) or argv[index] not in allowed_remotes:
        return Result(Decision.ABSTAIN, "remote is not configured as allowed")

    for pattern in argv[index + 1 :]:
        if (
            REF_PATTERN.fullmatch(pattern) is None
            or pattern.startswith("/")
            or ".." in pattern
            or "//" in pattern
        ):
            return Result(Decision.ABSTAIN, "invalid ref pattern")

    return Result(Decision.ALLOW, "read refs from configured project remote")
