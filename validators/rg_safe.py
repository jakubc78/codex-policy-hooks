from pathlib import Path

from dispatcher import Context, Decision, Result
from _helpers import (
    contains_shell_operators,
    cwd_is_within_project,
    resolve_project_root,
)


NAME = "rg_safe"
PRIORITY = 50


FORBIDDEN_OPTIONS = {
    "--pre",
    "--pre-glob",

    # Following symlinks can escape the project.
    "--follow",
    "-L",

    # May invoke external decompression helpers.
    "--search-zip",
    "-z",

    # Avoid automatic traversal of normally hidden material.
    "--hidden",
    "-.",
}


def looks_like_external_path(value: str) -> bool:
    if value == "..":
        return True

    if value.startswith("../"):
        return True

    try:
        return Path(value).is_absolute()
    except (TypeError, ValueError):
        return True


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv

    if not argv or argv[0] != "rg":
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
        if arg in FORBIDDEN_OPTIONS:
            return Result(
                Decision.ABSTAIN,
                f"unsafe rg option: {arg}",
            )

        if arg.startswith("--pre="):
            return Result(
                Decision.ABSTAIN,
                "unsafe rg option: --pre",
            )

        if arg.startswith("--pre-glob="):
            return Result(
                Decision.ABSTAIN,
                "unsafe rg option: --pre-glob",
            )

    #
    # This is intentionally conservative. An absolute pathname or ../ is
    # treated as suspicious even though in rare cases it could be a regex.
    #
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue

        if looks_like_external_path(arg):
            return Result(
                Decision.ABSTAIN,
                f"possible path outside project: {arg}",
            )

    return Result(
        Decision.ALLOW,
        "ripgrep restricted to project without external preprocessors",
    )
