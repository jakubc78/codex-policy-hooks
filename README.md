# codex-policy-hooks

Custom permission-policy framework for OpenAI Codex CLI.

The project provides a dispatcher and modular validators for selectively
auto-approving commands that would otherwise require manual permission.

## Included validators

- curl requests restricted to loopback
- read-only GitHub API access scoped to one repository
- restricted milestone state updates
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
