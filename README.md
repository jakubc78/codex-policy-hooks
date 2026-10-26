# codex-policy-hooks

Custom permission-policy framework for OpenAI Codex CLI.

The project provides a dispatcher and modular validators for selectively
auto-approving commands that would otherwise require manual permission.

## Included validators

- curl requests restricted to loopback
- read-only GitHub API access scoped to one repository
- restricted milestone state updates
- repository- and project-scoped native GitHub sub-issue linking
- safe `find`
- safe `rg`
- restricted `git push`
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
        +-- validators/gh_api_milestone_write.py
        +-- validators/find_safe.py
        +-- validators/rg_safe.py
        +-- validators/git_push_safe.py
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

## Self-test

Run:

    python3 dispatcher.py --self-test

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
