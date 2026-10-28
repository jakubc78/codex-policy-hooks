# codex-policy-hooks

Custom permission-policy framework for OpenAI Codex CLI.

The project provides a dispatcher and modular validators for selectively
auto-approving commands that would otherwise require manual permission.

## Included validators

- curl requests restricted to loopback
- read-only GitHub API access scoped to one repository
- exact QDR repository identity read
- QDR native sub-issue POST syntax allowance
- restricted milestone state updates
- repository- and project-scoped native GitHub sub-issue linking
- safe `find`
- safe `rg`
- restricted `git push`
- read-only `git ls-remote` for configured project remotes
- restricted Python development tooling
- restricted Docker operations

## Architecture

Codex PermissionRequest
        |
        v
dispatcher.py
        |
        +-- validators/curl_loopback.py
        +-- validators/gh_api_repo_read.py
        +-- validators/gh_repo_view.py
        +-- validators/gh_api_subissue_create.py
        +-- validators/gh_api_milestone_write.py
        +-- validators/find_safe.py
        +-- validators/rg_safe.py
        +-- validators/git_push_safe.py
        +-- validators/git_ls_remote_safe.py
        +-- validators/python_safe.py
        +-- validators/docker_safe.py

Validators return:

- ALLOW
- DENY
- ABSTAIN

ABSTAIN leaves the decision to the normal Codex approval flow.

## Configuration

Copy:

    config.example.json

to:

    ~/.codex/policy/config.json

and configure the repository and project root.

The real `config.json` should not be committed because it is environment-specific.
`git_ls_remote_safe` allows `git ls-remote` from its configured project root
to an exact name in `allowed_remotes` (for example, `origin`). It accepts
`--heads`, `--tags`, `--refs`, `--symref`, `--exit-code`, `--quiet`, `-q`, and
simple ref patterns. It rejects remote URLs unless explicitly configured,
upload-pack overrides, shell expansion, and compound commands.
The three QDR GitHub validators require `repository` to be exactly
`jakubc78/qnap-document-router`. Their source is intentionally scoped to that
repository; changing the config alone cannot widen this allowance. The
`hooks.example.json` command path must be adjusted for the local user.

The sub-issue validator allows only a single `gh api` POST to
`repos/jakubc78/qnap-document-router/issues/N/sub_issues` with a positive
numeric `sub_issue_id` via `-F` or `--field`. It accepts `--method POST` or
`-X POST`, optional `--jq '.number'`, and optional `--silent`. Unexpected
options, another repository, method, endpoint, `replace_parent=true`, shell
expansion, and command chaining do not receive this allowance. Read-only
`gh api` requests must stay within the QDR repository and cannot include
data-bearing fields.

This hook checks command syntax, not issue types or existing native parents.
Before a relationship write, use QDR's
`scripts/link-issue-hierarchy.sh --dry-run --child N` and its `--apply`
mode for an authorized, recorded relationship. The helper verifies Epic →
Story → Task/Bug/Spike/Chore, refuses conflicting parents, and reads the
relationship back after POST. A hook allowance does not grant network access,
GitHub authentication, or Issues write permission. Codex sandbox network
restrictions may still require a command-scoped escalation.

## Self-test

Run:

    python3 dispatcher.py --self-test
    python3 test_validators.py
    python3 -m unittest discover -s tests -v

## QDR native issue hierarchy approvals

Enable `gh_api_subissue_link` in your local (untracked) policy config with
`repository: jakubc78/qnap-document-router` and `project_root` pointing to the
checked-out QDR repository. This validator approves **only** a single explicit
`gh api --method POST repos/jakubc78/qnap-document-router/issues/123/sub_issues -F sub_issue_id=456`
command with numeric issue identifiers. It cannot verify whether the child
already has a parent: callers must first verify hierarchy and read it back
after linking. It does not approve generic writes or GitHub API access outside
that repo. Existing GET validation remains separate.

The policy hooks do not grant sandbox network access or override Codex's
permission/approval layer. Run `python3 -m unittest discover -s tests -v`
to execute the regression tests. Apply the reviewed change to the local hook
checkout before using it.
