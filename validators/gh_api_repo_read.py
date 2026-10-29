import re

from _helpers import contains_shell_operators
from dispatcher import Context, Decision, Result


NAME = "gh_api_repo_read"
PRIORITY = 20
TARGET_REPOSITORY = "jakubc78/qnap-document-router"


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv
    if argv[:2] != ["gh", "api"]:
        return Result(Decision.ABSTAIN)

    command = ctx.command
    if (
        not command
        or contains_shell_operators(command)
        or any(char in command for char in ("$", "`", "\n", "\r"))
        or config.get("repository") != TARGET_REPOSITORY
    ):
        return Result(Decision.ABSTAIN, "unsafe command or repository scope")

    endpoint: str | None = None
    method: str | None = None
    jq_seen = False
    paginate_seen = False
    index = 2
    while index < len(argv):
        arg = argv[index]
        if arg in {"--method", "-X"}:
            if method is not None or index + 1 >= len(argv):
                return Result(Decision.ABSTAIN, "ambiguous HTTP method")
            method = argv[index + 1]
            index += 2
            continue
        if arg == "--jq":
            if jq_seen or index + 1 >= len(argv) or not argv[index + 1]:
                return Result(Decision.ABSTAIN, "ambiguous jq filter")
            jq_seen = True
            index += 2
            continue
        if arg == "--paginate":
            if paginate_seen:
                return Result(Decision.ABSTAIN, "duplicate pagination option")
            paginate_seen = True
            index += 1
            continue
        if arg.startswith("-") or endpoint is not None:
            return Result(Decision.ABSTAIN, "unexpected API argument")
        endpoint = arg
        index += 1

    if method not in {None, "GET"} or endpoint is None:
        return Result(Decision.ABSTAIN, "request is not one repository GET")

    path, separator, query = endpoint.partition("?")
    prefix = f"repos/{TARGET_REPOSITORY}"
    if path != prefix and not path.startswith(prefix + "/"):
        return Result(Decision.ABSTAIN, "endpoint is outside repository scope")
    if (
        re.fullmatch(r"[A-Za-z0-9_./-]+", path) is None
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or (separator and re.fullmatch(r"[A-Za-z0-9_.~%=&:+,-]+", query) is None)
        or "?" in query
    ):
        return Result(Decision.ABSTAIN, "invalid repository endpoint")

    return Result(
        Decision.ALLOW,
        f"read-only GitHub API request within {TARGET_REPOSITORY}",
    )
