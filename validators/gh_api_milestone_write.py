import re

from dispatcher import Context, Decision, Result


NAME = "gh_api_milestone_write"
PRIORITY = 30


def evaluate(ctx: Context, config: dict) -> Result:
    argv = ctx.argv

    if len(argv) < 3:
        return Result(Decision.ABSTAIN)

    if argv[:2] != ["gh", "api"]:
        return Result(Decision.ABSTAIN)

    repository = config.get("repository")
    if not isinstance(repository, str) or "/" not in repository:
        return Result(
            Decision.ABSTAIN,
            "repository is not configured correctly",
        )

    endpoint = None
    method = "GET"
    fields: list[str] = []

    i = 2
    while i < len(argv):
        arg = argv[i]

        if arg in {"-X", "--method"}:
            if i + 1 >= len(argv):
                return Result(
                    Decision.ABSTAIN,
                    "missing HTTP method value",
                )

            method = argv[i + 1].upper()
            i += 2
            continue

        if arg in {"-f", "--raw-field", "-F", "--field"}:
            if i + 1 >= len(argv):
                return Result(
                    Decision.ABSTAIN,
                    f"missing value for {arg}",
                )

            fields.append(argv[i + 1])
            i += 2
            continue

        if arg == "--input":
            return Result(
                Decision.ABSTAIN,
                "--input is not allowed for milestone writes",
            )

        if not arg.startswith("-") and endpoint is None:
            endpoint = arg

        i += 1

    if method != "PATCH":
        return Result(
            Decision.ABSTAIN,
            f"HTTP method is {method}, not PATCH",
        )

    if endpoint is None:
        return Result(
            Decision.ABSTAIN,
            "no API endpoint found",
        )

    expected = (
        rf"repos/{re.escape(repository)}/milestones/\d+"
    )

    if re.fullmatch(expected, endpoint) is None:
        return Result(
            Decision.ABSTAIN,
            f"endpoint is not a milestone resource: {endpoint}",
        )

    if not fields:
        return Result(
            Decision.ABSTAIN,
            "PATCH contains no fields",
        )

    allowed_fields = {
        "state=open",
        "state=closed",
    }

    for field in fields:
        if field not in allowed_fields:
            return Result(
                Decision.ABSTAIN,
                f"field is not allowed: {field}",
            )

    return Result(
        Decision.ALLOW,
        "milestone PATCH limited to state=open/closed",
    )
