"""Approve only narrowly scoped native GitHub sub-issue linking commands."""

import re

from dispatcher import Context, Decision, Result
from _helpers import contains_shell_operators, cwd_is_within_project, resolve_project_root

NAME = "gh_api_subissue_link"
PRIORITY = 25


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv
    if argv[:2] != ["gh", "api"]:
        return Result(Decision.ABSTAIN)
    if contains_shell_operators(ctx.command):
        return Result(Decision.ABSTAIN, "compound shell command")

    repository = config.get("repository")
    root = resolve_project_root(config)
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        return Result(Decision.ABSTAIN, "invalid repository scope")
    if root is None or not cwd_is_within_project(ctx.cwd, root):
        return Result(Decision.ABSTAIN, "outside configured project root")

    # Fail closed for unknown or repeated flags. No --input, aliases, or
    # implicit POST via -F without an explicit --method POST.
    if len(argv) != 7:
        return Result(Decision.ABSTAIN, "unexpected argument count")
    if argv[2:4] != ["--method", "POST"]:
        return Result(Decision.ABSTAIN, "requires explicit POST")
    endpoint = argv[4]
    if not re.fullmatch(rf"repos/{re.escape(repository)}/issues/[1-9][0-9]*/sub_issues", endpoint):
        return Result(Decision.ABSTAIN, "endpoint outside scoped sub-issue API")
    if argv[5] != "-F" or not re.fullmatch(r"sub_issue_id=[1-9][0-9]*", argv[6]):
        return Result(Decision.ABSTAIN, "requires exactly one numeric sub_issue_id")
    return Result(Decision.ALLOW, "scoped native sub-issue link")
