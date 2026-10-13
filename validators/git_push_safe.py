from dispatcher import Context, Decision, Result
from _helpers import (
    contains_shell_operators,
    cwd_is_within_project,
    resolve_project_root,
)


NAME = "git_push_safe"
PRIORITY = 60


FORBIDDEN_OPTIONS = {
    "--force",
    "-f",
    "--force-with-lease",
    "--force-if-includes",
    "--delete",
    "-d",
    "--mirror",
    "--prune",
}


OPTIONS_WITH_VALUE = {
    "--repo",
    "--receive-pack",
    "--exec",
    "-o",
    "--push-option",
}


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv

    if len(argv) < 2 or argv[:2] != ["git", "push"]:
        return Result(Decision.ABSTAIN)

    if contains_shell_operators(ctx.command):
        return Result(
            Decision.ABSTAIN,
            "compound shell command",
        )

    project_root = resolve_project_root(config)

    if project_root is None:
        return Result(
            Decision.ABSTAIN,
            "project_root is not configured",
        )

    if not cwd_is_within_project(ctx.cwd, project_root):
        return Result(
            Decision.ABSTAIN,
            "current directory is outside project root",
        )

    for arg in argv[2:]:
        if arg in FORBIDDEN_OPTIONS:
            return Result(
                Decision.ABSTAIN,
                f"unsafe git push option: {arg}",
            )

        if arg.startswith("--force-with-lease="):
            return Result(
                Decision.ABSTAIN,
                "unsafe git push option: --force-with-lease",
            )

    allowed_remotes = set(
        config.get("allowed_remotes", ["origin"])
    )

    #
    # Identify the first positional argument. For ordinary git push this is
    # the remote. No positional argument means Git uses the configured
    # upstream, which is permitted.
    #
    positional: list[str] = []

    i = 2
    while i < len(argv):
        arg = argv[i]

        if arg in OPTIONS_WITH_VALUE:
            i += 2
            continue

        if arg.startswith("-"):
            i += 1
            continue

        positional.append(arg)
        i += 1

    if positional:
        remote = positional[0]

        if remote not in allowed_remotes:
            return Result(
                Decision.ABSTAIN,
                f"git push remote is not allowed: {remote}",
            )

    return Result(
        Decision.ALLOW,
        "normal git push to configured project remote",
    )
