from __future__ import annotations

import shlex
from pathlib import Path


SHELL_PUNCTUATION = ";&|<>"


def contains_shell_operators(command: str | None) -> bool:
    """
    Detect shell control operators outside quoted strings.

    We deliberately re-tokenize with punctuation_chars because ordinary
    shlex.split() does not reliably separate operators such as && or ;.
    """
    if not command:
        return False

    try:
        lexer = shlex.shlex(
            command,
            posix=True,
            punctuation_chars=";&|<>",
        )
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return True

    # shlex groups adjacent punctuation. Bash also accepts combinations
    # such as |& and >&, so an exact-token allowlist misses real operators.
    return any(
        token and all(char in SHELL_PUNCTUATION for char in token)
        for token in tokens
    )


def resolve_project_root(config: dict) -> Path | None:
    value = config.get("project_root")

    if not isinstance(value, str) or not value:
        return None

    return Path(value).expanduser().resolve()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def cwd_is_within_project(cwd: Path, root: Path) -> bool:
    return is_within(cwd, root)


def resolve_from_cwd(value: str, cwd: Path) -> Path:
    path = Path(value).expanduser()

    if not path.is_absolute():
        path = cwd / path

    return path.resolve()
