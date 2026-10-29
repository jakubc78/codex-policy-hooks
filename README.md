# codex-policy-hooks

Custom permission-policy framework for OpenAI Codex CLI.

The project provides a dispatcher and modular validators for selectively
auto-approving commands that would otherwise require manual permission.

## Included validators

- curl requests restricted to loopback
- read-only GitHub API access scoped to one repository
- read-only GitHub CLI diagnostics scoped to one repository and project root
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
        +-- validators/gh_diagnostics_safe.py
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

### GitHub diagnostics

Add this section to the active policy `config.json`, using the exact repository
and absolute path of its checked-out project root:

```json
"gh_diagnostics_safe": {
  "enabled": true,
  "repository": "jakubc78/qnap-document-router",
  "project_root": "/home/jakub/projects/qnap-document-router",
  "allow_failed_logs": true,
  "allow_full_logs": false
}
```

The `repository` is a single-entry allowlist. The command must specify it with
`--repo OWNER/REPOSITORY` (or `--repo=OWNER/REPOSITORY`) and run from the
configured root or a directory inside it. Missing, disabled, or invalid
configuration causes `ABSTAIN`. `--log-failed` requires `allow_failed_logs`;
`--log` requires the separate `allow_full_logs` opt-in.

Supported operations are `gh run view` with a positive numeric run ID,
`gh run list`, `gh pr checks` and `gh pr view` with a positive numeric PR
number, and `gh issue view` with a positive numeric issue number. The only
accepted options are `--repo`, `--log-failed`, and `--log` in their stated
contexts. `--json`, `--jq`, and `--limit` are not approved because they add
argument parsing and output behavior that this validator has not scoped.

Examples from the configured project root:

```bash
# Approved when failed logs are enabled
gh run view 40910865463 --repo jakubc78/qnap-document-router --log-failed
gh run view 40910865463 --repo jakubc78/qnap-document-router
gh run list --repo jakubc78/qnap-document-router
gh pr checks 123 --repo jakubc78/qnap-document-router
gh pr view 123 --repo jakubc78/qnap-document-router
gh issue view 123 --repo jakubc78/qnap-document-router

# Not auto-approved; normal Codex approval applies
gh run view 40910865463 --repo someone/other-repo --log-failed
gh run view 40910865463 --log-failed
gh run view abc --repo jakubc78/qnap-document-router
gh run view 40910865463 --repo jakubc78/qnap-document-router | cat
gh run rerun 40910865463 --repo jakubc78/qnap-document-router
gh pr merge 123 --repo jakubc78/qnap-document-router
```

CI logs can contain credentials or other sensitive data even though reading
them does not change GitHub state. Enable log access only where workers may
see that information, and avoid copying logs into unrelated outputs.

Hook approval does not grant network access through the Codex sandbox or
provide GitHub authentication. If a command still prompts, check the active
hook path and policy config, the command's exact arguments, the working
directory, and whether the requested log option is enabled. Run
`python3 dispatcher.py --self-test` to confirm the validator loads. With
`CODEX_POLICY_DEBUG=1`, dispatcher reasons appear on stderr; do not paste
debug output publicly if it contains sensitive command arguments.

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
