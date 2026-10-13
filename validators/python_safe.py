from dispatcher import Context, Decision, Result
from _helpers import (
    contains_shell_operators,
    cwd_is_within_project,
    resolve_project_root,
)


NAME = "python_safe"
PRIORITY = 70


DEFAULT_ALLOWED_MODULES = {
    "pytest",
    "mypy",
    "ruff",
    "py_compile",
    "compileall",
}


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv

    if not argv or argv[0] not in {"python", "python3"}:
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

    if len(argv) < 3 or argv[1] != "-m":
        return Result(
            Decision.ABSTAIN,
            "only approved python -m tools are auto-approved",
        )

    module = argv[2]

    allowed_modules = set(
        config.get(
            "allowed_modules",
            DEFAULT_ALLOWED_MODULES,
        )
    )

    if module not in allowed_modules:
        return Result(
            Decision.ABSTAIN,
            f"python module is not approved: {module}",
        )

    return Result(
        Decision.ALLOW,
        f"approved Python development module: {module}",
    )
