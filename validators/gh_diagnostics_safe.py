"""Allow a small set of repository-scoped, read-only GitHub diagnostics."""

import re
from pathlib import Path

from _helpers import contains_shell_operators, cwd_is_within_project
from dispatcher import Context, Decision, Result

NAME = "gh_diagnostics_safe"
PRIORITY = 30

REPOSITORY = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9_][A-Za-z0-9_.-]*\Z"
)
IDENTIFIER = re.compile(r"[1-9][0-9]*\Z")
OPERATIONS = {
    ("run", "view"),
    ("run", "list"),
    ("pr", "checks"),
    ("pr", "view"),
    ("issue", "view"),
}


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv
    if argv[:1] != ["gh"]:
        return Result(Decision.ABSTAIN)

    # The command is parsed by the dispatcher with shlex. Reject shell syntax
    # in the original string as well, since shlex.split alone accepts it.
    command = ctx.command
    if (
        not command
        or contains_shell_operators(command)
        or any(char in command for char in "$`\n\r;&|<>")
    ):
        return Result(Decision.ABSTAIN, "shell syntax or expansion")

    if config.get("enabled") is not True:
        return Result(Decision.ABSTAIN, "diagnostics not enabled")
    repository = config.get("repository")
    root_value = config.get("project_root")
    if not isinstance(repository, str) or REPOSITORY.fullmatch(repository) is None:
        return Result(Decision.ABSTAIN, "invalid repository scope")
    if not isinstance(root_value, str) or not Path(root_value).is_absolute():
        return Result(Decision.ABSTAIN, "invalid project root")
    root = Path(root_value).resolve()
    if not root.is_dir() or not cwd_is_within_project(ctx.cwd, root):
        return Result(Decision.ABSTAIN, "outside configured project root")
    if type(config.get("allow_failed_logs", False)) is not bool or type(
        config.get("allow_full_logs", False)
    ) is not bool:
        return Result(Decision.ABSTAIN, "invalid log configuration")

    if len(argv) < 3 or tuple(argv[1:3]) not in OPERATIONS:
        return Result(Decision.ABSTAIN, "unsupported GitHub operation")
    operation = tuple(argv[1:3])
    needs_id = operation != ("run", "list")
    identifier = None
    target = None
    log_flag = None
    index = 3
    while index < len(argv):
        arg = argv[index]
        if arg == "--repo":
            index += 1
            if target is not None or index >= len(argv):
                return Result(Decision.ABSTAIN, "missing or duplicate repository")
            target = argv[index]
        elif arg.startswith("--repo="):
            if target is not None:
                return Result(Decision.ABSTAIN, "duplicate repository")
            target = arg[len("--repo="):]
        elif arg in ("--log-failed", "--log") and operation == ("run", "view"):
            if log_flag is not None:
                return Result(Decision.ABSTAIN, "duplicate log option")
            log_flag = arg
        elif needs_id and identifier is None and IDENTIFIER.fullmatch(arg):
            identifier = arg
        else:
            return Result(Decision.ABSTAIN, "unexpected GitHub argument")
        index += 1

    if target != repository or (needs_id and identifier is None):
        return Result(Decision.ABSTAIN, "missing or unauthorized target")
    if log_flag == "--log-failed" and not config.get("allow_failed_logs", False):
        return Result(Decision.ABSTAIN, "failed logs not enabled")
    if log_flag == "--log" and not config.get("allow_full_logs", False):
        return Result(Decision.ABSTAIN, "full logs not enabled")
    return Result(Decision.ALLOW, "scoped read-only GitHub diagnostic")
