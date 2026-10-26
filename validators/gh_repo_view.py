from _helpers import contains_shell_operators
from dispatcher import Context, Decision, Result


NAME = "gh_repo_view"
PRIORITY = 20
TARGET_REPOSITORY = "jakubc78/qnap-document-router"
EXPECTED = ["gh", "repo", "view", TARGET_REPOSITORY, "--json", "nameWithOwner"]


def evaluate(ctx: Context, config: dict) -> Result:
    if ctx.argv[:3] != ["gh", "repo", "view"]:
        return Result(Decision.ABSTAIN)

    command = ctx.command
    if (
        config.get("repository") != TARGET_REPOSITORY
        or not command
        or contains_shell_operators(command)
        or any(char in command for char in ("$", "`", "\n", "\r"))
        or ctx.argv != EXPECTED
    ):
        return Result(Decision.ABSTAIN, "repo view differs from exact read-only form")

    return Result(Decision.ALLOW, "exact repository identity read")
