from dispatcher import Context, Decision, Result
from _helpers import (
    contains_shell_operators,
    cwd_is_within_project,
    is_within,
    resolve_from_cwd,
    resolve_project_root,
)


NAME = "find_safe"
PRIORITY = 40


FORBIDDEN_TOKENS = {
    "-delete",
    "-exec",
    "-execdir",
    "-ok",
    "-okdir",

    # Actions writing output to arbitrary files
    "-fprint",
    "-fprint0",
    "-fprintf",
    "-fls",

    # Following symlinks could escape project root
    "-L",
    "-H",

    # Read path list from an arbitrary file
    "-files0-from",
}


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv

    if not argv or argv[0] != "find":
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

    for arg in argv[1:]:
        if arg in FORBIDDEN_TOKENS:
            return Result(
                Decision.ABSTAIN,
                f"unsafe find option: {arg}",
            )

    # find paths occur before the first expression/option.
    paths: list[str] = []

    for arg in argv[1:]:
        if arg.startswith("-") or arg in {"!", "(", ")"}:
            break

        paths.append(arg)

    if not paths:
        paths = ["."]

    for value in paths:
        resolved = resolve_from_cwd(value, ctx.cwd)

        if not is_within(resolved, project_root):
            return Result(
                Decision.ABSTAIN,
                f"find path outside project: {value}",
            )

    return Result(
        Decision.ALLOW,
        "read-only find restricted to project tree",
    )
