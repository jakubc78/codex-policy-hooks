import re

from _helpers import contains_shell_operators
from dispatcher import Context, Decision, Result

NAME = "gh_api_subissue_create"
PRIORITY = 25
TARGET_REPOSITORY = "jakubc78/qnap-document-router"
ENDPOINT = re.compile(
    r"repos/jakubc78/qnap-document-router/issues/([1-9][0-9]*)/sub_issues"
)
FIELD = re.compile(r"sub_issue_id=([1-9][0-9]*)")


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv
    if argv[:2] != ["gh", "api"]:
        return Result(Decision.ABSTAIN)

    command = ctx.command
    if (
        config.get("repository") != TARGET_REPOSITORY
        or not command
        or contains_shell_operators(command)
        or any(char in command for char in ("$", "`", "\n", "\r"))
    ):
        return Result(Decision.ABSTAIN, "not one scoped Sub-issue POST")

    method = endpoint = field = jq = None
    silent = False
    index = 2
    while index < len(argv):
        arg = argv[index]
        if arg in {"--method", "-X", "-F", "--field", "--jq"}:
            if index + 1 >= len(argv):
                return Result(Decision.ABSTAIN, "missing API option value")
            value = argv[index + 1]
            index += 2
        elif arg.startswith(("--method=", "--field=", "--jq=")):
            arg, value = arg.split("=", 1)
            index += 1
        elif arg == "--silent" and not silent:
            silent = True
            index += 1
            continue
        elif not arg.startswith("-") and endpoint is None:
            endpoint = arg
            index += 1
            continue
        else:
            return Result(Decision.ABSTAIN, "unexpected API argument")

        if arg in {"--method", "-X"}:
            if method is not None:
                return Result(Decision.ABSTAIN, "duplicate method")
            method = value
        elif arg in {"-F", "--field"}:
            if field is not None:
                return Result(Decision.ABSTAIN, "duplicate field")
            field = value
        elif arg == "--jq":
            if jq is not None:
                return Result(Decision.ABSTAIN, "duplicate jq")
            jq = value

    if (
        method != "POST"
        or endpoint is None
        or field is None
        or jq not in {None, ".number"}
    ):
        return Result(Decision.ABSTAIN, "invalid Sub-issue request")
    if ENDPOINT.fullmatch(endpoint) is None or FIELD.fullmatch(field) is None:
        return Result(Decision.ABSTAIN, "invalid parent or child database ID")

    return Result(
        Decision.ALLOW,
        "one syntactically scoped Sub-issue POST; verify hierarchy separately",
    )
