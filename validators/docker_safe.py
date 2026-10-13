from pathlib import Path

from dispatcher import Context, Decision, Result
from _helpers import (
    contains_shell_operators,
    cwd_is_within_project,
    is_within,
    resolve_from_cwd,
    resolve_project_root,
)


NAME = "docker_safe"
PRIORITY = 80


DANGEROUS_RUN_OPTIONS = {
    "--privileged",

    "--volume",
    "-v",
    "--mount",
    "--volumes-from",

    "--device",
    "--device-cgroup-rule",

    "--cap-add",
    "--security-opt",

    "--env-file",

    "--pid",
    "--ipc",
    "--uts",
    "--userns",
    "--cgroupns",
    "--network",
}


DANGEROUS_RUN_PREFIXES = {
    "--volume=",
    "--mount=",
    "--volumes-from=",
    "--device=",
    "--device-cgroup-rule=",
    "--cap-add=",
    "--security-opt=",
    "--env-file=",

    "--pid=",
    "--ipc=",
    "--uts=",
    "--userns=",
    "--cgroupns=",
}


SAFE_COMPOSE_COMMANDS = {
    "build",
    "config",
    "images",
    "logs",
    "ps",
    "pull",
    "start",
    "stop",
    "restart",
    "up",
}


def evaluate_build(
    ctx: Context,
    argv: list[str],
    project_root: Path,
) -> Result:
    forbidden = {
        "--ssh",
        "--secret",
        "--build-context",
        "--output",
        "-o",
    }

    for arg in argv[2:]:
        if arg in forbidden:
            return Result(
                Decision.ABSTAIN,
                f"unsafe docker build option: {arg}",
            )

        for prefix in (
            "--ssh=",
            "--secret=",
            "--build-context=",
            "--output=",
        ):
            if arg.startswith(prefix):
                return Result(
                    Decision.ABSTAIN,
                    f"unsafe docker build option: {prefix[:-1]}",
                )

        if arg == "--network=host":
            return Result(
                Decision.ABSTAIN,
                "docker build host networking",
            )

    # Validate Dockerfile path when explicitly supplied.
    for i, arg in enumerate(argv):
        if arg in {"-f", "--file"}:
            if i + 1 >= len(argv):
                return Result(Decision.ABSTAIN)

            dockerfile = resolve_from_cwd(
                argv[i + 1],
                ctx.cwd,
            )

            if not is_within(dockerfile, project_root):
                return Result(
                    Decision.ABSTAIN,
                    "Dockerfile is outside project",
                )

        if arg.startswith("--file="):
            dockerfile = resolve_from_cwd(
                arg.split("=", 1)[1],
                ctx.cwd,
            )

            if not is_within(dockerfile, project_root):
                return Result(
                    Decision.ABSTAIN,
                    "Dockerfile is outside project",
                )

    return Result(
        Decision.ALLOW,
        "Docker build restricted to project",
    )


def evaluate_run(
    argv: list[str],
) -> Result:
    i = 2

    while i < len(argv):
        arg = argv[i]

        if arg in DANGEROUS_RUN_OPTIONS:
            return Result(
                Decision.ABSTAIN,
                f"unsafe docker run option: {arg}",
            )

        if any(
            arg.startswith(prefix)
            for prefix in DANGEROUS_RUN_PREFIXES
        ):
            return Result(
                Decision.ABSTAIN,
                f"unsafe docker run option: {arg}",
            )

        if arg == "--network=host":
            return Result(
                Decision.ABSTAIN,
                "docker run host networking",
            )

        i += 1

    return Result(
        Decision.ALLOW,
        "docker run without host escape/mount options",
    )


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv

    if not argv or argv[0] != "docker":
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

    if len(argv) < 2:
        return Result(Decision.ABSTAIN)

    command = argv[1]

    if command == "build":
        return evaluate_build(
            ctx,
            argv,
            project_root,
        )

    if command == "run":
        return evaluate_run(argv)

    if command == "compose":
        if len(argv) < 3:
            return Result(Decision.ABSTAIN)

        compose_command = argv[2]

        if compose_command not in SAFE_COMPOSE_COMMANDS:
            return Result(
                Decision.ABSTAIN,
                f"docker compose command requires approval: "
                f"{compose_command}",
            )

        if compose_command == "up" and "--remove-orphans" in argv:
            return Result(
                Decision.ABSTAIN,
                "compose up --remove-orphans can remove containers",
            )

        return Result(
            Decision.ALLOW,
            f"approved docker compose command: {compose_command}",
        )

    if argv[:3] == [
        "docker",
        "buildx",
        "inspect",
    ]:
        allowed = {
            "docker",
            "buildx",
            "inspect",
            "--bootstrap",
        }

        if all(arg in allowed for arg in argv):
            return Result(
                Decision.ALLOW,
                "docker buildx inspect",
            )

    if argv[:4] == [
        "docker",
        "buildx",
        "imagetools",
        "inspect",
    ]:
        return Result(
            Decision.ALLOW,
            "docker buildx imagetools inspect",
        )

    return Result(Decision.ABSTAIN)
