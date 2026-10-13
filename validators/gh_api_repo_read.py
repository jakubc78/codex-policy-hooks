from dispatcher import Context, Decision, Result


NAME = "gh_api_repo_read"
PRIORITY = 20


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

    repo_prefix = f"repos/{repository}"

    method = "GET"
    endpoint = None

    i = 2
    while i < len(argv):
        arg = argv[i]

        if arg in {"-X", "--method"}:
            if i + 1 >= len(argv):
                return Result(Decision.ABSTAIN)

            method = argv[i + 1].upper()
            i += 2
            continue

        if arg in {"-f", "--raw-field", "-F", "--field", "--input"}:
            # Fields/input can affect request semantics and may implicitly
            # change GET into POST in gh api.
            return Result(
                Decision.ABSTAIN,
                f"request contains data-bearing option: {arg}",
            )

        if not arg.startswith("-") and endpoint is None:
            endpoint = arg

        i += 1

    if method != "GET":
        return Result(
            Decision.ABSTAIN,
            f"HTTP method is {method}, not GET",
        )

    if endpoint is None:
        return Result(
            Decision.ABSTAIN,
            "no API endpoint found",
        )

    # Strip query string for repository-prefix validation.
    endpoint_path = endpoint.split("?", 1)[0]

    if endpoint_path != repo_prefix and not endpoint_path.startswith(
        repo_prefix + "/"
    ):
        return Result(
            Decision.ABSTAIN,
            f"endpoint is outside repository scope: {endpoint}",
        )

    return Result(
        Decision.ALLOW,
        f"read-only GitHub API request within {repository}",
    )
