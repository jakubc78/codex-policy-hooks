#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Import dispatcher from the same directory.
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from dispatcher import (  # noqa: E402
    Context,
    Decision,
    Result,
    load_config,
    load_validators,
)


@dataclass(frozen=True)
class TestCase:
    name: str
    command: str
    expected: Decision


TEST_CASES = [
    # curl_loopback
    TestCase(
        "curl localhost health",
        "curl -fsS http://localhost:8765/health",
        Decision.ALLOW,
    ),
    TestCase(
        "curl localhost documents",
        'curl -fsS -o /dev/null -w "documents %{http_code}\\n" '
        "http://localhost:8765/documents",
        Decision.ALLOW,
    ),
    TestCase(
        "curl localhost POST",
        'curl -sS -o /dev/null -w "invalid action %{http_code}\\n" '
        '-X POST -H "Content-Type: application/x-www-form-urlencoded" '
        '--data "csrf_token=invalid" '
        "http://localhost:8765/analyze",
        Decision.ALLOW,
    ),
    TestCase(
        "curl external host",
        "curl -fsS https://example.com/",
        Decision.ABSTAIN,
    ),
    TestCase(
        "curl localhost redirect",
        "curl -L http://localhost:8765/",
        Decision.ABSTAIN,
    ),
    TestCase(
        "curl localhost resolve override",
        "curl --resolve localhost:8765:8.8.8.8 "
        "http://localhost:8765/",
        Decision.ABSTAIN,
    ),

    # gh_api_repo_read
    TestCase(
        "gh api read milestone",
        "gh api "
        "repos/jakubc78/qnap-document-router/milestones/5 "
        '--jq "{title,state,open_issues,closed_issues}"',
        Decision.ALLOW,
    ),
    TestCase(
        "gh api read milestones query",
        'gh api "repos/jakubc78/qnap-document-router/'
        'milestones?state=all"',
        Decision.ALLOW,
    ),
    TestCase(
        "gh api outside repository",
        "gh api repos/openai/codex/issues",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api read with field",
        "gh api repos/jakubc78/qnap-document-router/issues "
        "-f state=open",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api read native parent",
        "gh api repos/jakubc78/qnap-document-router/issues/176/parent",
        Decision.ALLOW,
    ),
    TestCase(
        "gh api read story parent",
        "gh api repos/jakubc78/qnap-document-router/issues/130/parent",
        Decision.ALLOW,
    ),
    TestCase(
        "gh api read child database ID",
        "gh api repos/jakubc78/qnap-document-router/issues/180 --jq '.id'",
        Decision.ALLOW,
    ),
    TestCase(
        "gh api read native sub-issues",
        "gh api --method GET repos/jakubc78/qnap-document-router/issues/168/sub_issues --jq '.[].number'",
        Decision.ALLOW,
    ),
    TestCase(
        "gh api read rejects arbitrary issue modification",
        "gh api --method PATCH repos/jakubc78/qnap-document-router/issues/176 "
        "-f state=closed",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api read rejects DELETE",
        "gh api --method DELETE repos/jakubc78/qnap-document-router/issues/176",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api read rejects unknown option",
        "gh api repos/jakubc78/qnap-document-router/issues/176/parent "
        "--header X-Test:value",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api read rejects command chain",
        "gh api repos/jakubc78/qnap-document-router/issues/176/parent; "
        "gh api repos/openai/codex/issues",
        Decision.ABSTAIN,
    ),

    # gh_repo_view
    TestCase(
        "gh repo exact identity read",
        "gh repo view jakubc78/qnap-document-router --json nameWithOwner",
        Decision.ALLOW,
    ),
    TestCase(
        "gh repo wrong repository",
        "gh repo view openai/codex --json nameWithOwner",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh repo extra JSON field",
        "gh repo view jakubc78/qnap-document-router --json nameWithOwner,description",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh repo command substitution",
        "gh repo view jakubc78/qnap-document-router --json "
        "$(printf nameWithOwner)",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh repo chained command",
        "gh repo view jakubc78/qnap-document-router --json nameWithOwner; "
        "echo unsafe",
        Decision.ABSTAIN,
    ),

    # gh_api_subissue_create
    TestCase(
        "gh api native Sub-issue POST",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues/130/sub_issues "
        '-F "sub_issue_id=123456"',
        Decision.ALLOW,
    ),
    TestCase(
        "gh api native Sub-issue POST with jq",
        "gh api --method POST repos/jakubc78/qnap-document-router/issues/189/sub_issues "
        "-F sub_issue_id=6017389449 --jq '.number'",
        Decision.ALLOW,
    ),
    TestCase(
        "gh api native Sub-issue POST equivalent flags",
        "gh api repos/jakubc78/qnap-document-router/issues/168/sub_issues "
        "-X POST --field=sub_issue_id=6005765620 --jq=.number --silent",
        Decision.ALLOW,
    ),
    TestCase(
        "gh api Sub-issue POST outside repository",
        "gh api --method POST repos/openai/codex/issues/130/sub_issues "
        "-F sub_issue_id=123456",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue POST extra field",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues/130/sub_issues "
        "-F sub_issue_id=123456 -F state=closed",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue POST alternate issue edit",
        "gh api --method POST repos/jakubc78/qnap-document-router/issues/130 "
        "-F sub_issue_id=123456",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue DELETE",
        "gh api --method DELETE "
        "repos/jakubc78/qnap-document-router/issues/130/sub_issues "
        "-F sub_issue_id=123456",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue PUT",
        "gh api --method PUT repos/jakubc78/qnap-document-router/issues/168/sub_issues "
        "-F sub_issue_id=123456",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue reparent flag",
        "gh api --method POST repos/jakubc78/qnap-document-router/issues/168/sub_issues "
        "-F sub_issue_id=123456 -F replace_parent=true",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue unexpected jq",
        "gh api --method POST repos/jakubc78/qnap-document-router/issues/168/sub_issues "
        "-F sub_issue_id=123456 --jq '.url'",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue arbitrary POST endpoint",
        "gh api --method POST repos/jakubc78/qnap-document-router/issues/168/comments "
        "-F sub_issue_id=123456",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue command substitution",
        "gh api --method POST repos/jakubc78/qnap-document-router/issues/168/sub_issues "
        "-F sub_issue_id=$(printf 123456)",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue redirection",
        "gh api --method POST repos/jakubc78/qnap-document-router/issues/168/sub_issues "
        "-F sub_issue_id=123456 > output.txt",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue missing parent ID",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues//sub_issues "
        "-F sub_issue_id=123456",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue malformed parent ID",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues/abc/sub_issues "
        "-F sub_issue_id=123456",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue missing child ID",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues/130/sub_issues "
        "-F sub_issue_id=",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue malformed child ID",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues/130/sub_issues "
        "-F sub_issue_id=12x",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue shell substitution",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues/130/sub_issues "
        '-F "sub_issue_id=$CHILD_ID"',
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue chained write",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues/130/sub_issues "
        "-F sub_issue_id=123456; gh api repos/openai/codex/issues",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api Sub-issue piped write",
        "gh api --method POST "
        "repos/jakubc78/qnap-document-router/issues/130/sub_issues "
        "-F sub_issue_id=123456 | cat",
        Decision.ABSTAIN,
    ),

    # gh_api_milestone_write
    TestCase(
        "gh api close milestone",
        "gh api -X PATCH "
        "repos/jakubc78/qnap-document-router/milestones/5 "
        "-f state=closed",
        Decision.ALLOW,
    ),
    TestCase(
        "gh api reopen milestone",
        "gh api --method PATCH "
        "repos/jakubc78/qnap-document-router/milestones/7 "
        "-f state=open",
        Decision.ALLOW,
    ),
    TestCase(
        "gh api modify milestone title",
        "gh api -X PATCH "
        "repos/jakubc78/qnap-document-router/milestones/5 "
        "-f title=hacked",
        Decision.ABSTAIN,
    ),
    TestCase(
        "gh api patch issue",
        "gh api -X PATCH "
        "repos/jakubc78/qnap-document-router/issues/5 "
        "-f state=closed",
        Decision.ABSTAIN,
    ),
]

DISPATCHER_CASES = [
    case
    for case in TEST_CASES
    if case.name
    in {
        "gh api read native parent",
        "gh api read story parent",
        "gh repo exact identity read",
        "gh api native Sub-issue POST",
        "gh api Sub-issue POST extra field",
        "gh api Sub-issue DELETE",
        "gh api Sub-issue shell substitution",
        "gh api Sub-issue chained write",
        "gh api read rejects command chain",
    }
] + [
    TestCase(
        "gh API milestone chain cannot inherit existing write allowance",
        "gh api -X PATCH "
        "repos/jakubc78/qnap-document-router/milestones/5 "
        "-f state=closed ; gh api repos/openai/codex/issues",
        Decision.ABSTAIN,
    )
]


def evaluate_command(
    command: str,
    validators,
    config: dict,
) -> tuple[Decision, list[str]]:
    payload = {
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {
            "command": command,
        },
        "cwd": str(Path.cwd()),
    }

    ctx = Context.from_payload(payload)

    allows: list[str] = []
    denies: list[str] = []

    for validator in validators:
        name = validator.NAME
        validator_config = config.get(name, {})

        if not isinstance(validator_config, dict):
            continue

        if validator_config.get("enabled", True) is False:
            continue

        result = validator.evaluate(ctx, validator_config)

        if not isinstance(result, Result):
            raise TypeError(
                f"{name} returned invalid result type: "
                f"{type(result).__name__}"
            )

        if result.decision == Decision.DENY:
            denies.append(
                f"{name}: {result.reason}"
            )

        elif result.decision == Decision.ALLOW:
            allows.append(
                f"{name}: {result.reason}"
            )

    if denies:
        return Decision.DENY, denies

    if allows:
        return Decision.ALLOW, allows

    return Decision.ABSTAIN, []


def dispatch_command(command: str) -> Decision:
    payload = {
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(Path.cwd()),
    }
    completed = subprocess.run(
        [sys.executable, str(BASE_DIR / "dispatcher.py")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    if not completed.stdout.strip():
        return Decision.ABSTAIN
    response = json.loads(completed.stdout)
    assert response["hookSpecificOutput"]["hookEventName"] == "PermissionRequest"
    return Decision(response["hookSpecificOutput"]["decision"]["behavior"])


def main() -> int:
    config = load_config()
    validators = load_validators()

    if not validators:
        print("ERROR: no validators loaded")
        return 1

    print("Validator regression tests")
    print("==========================")
    print(
        "Loaded: "
        + ", ".join(v.NAME for v in validators)
    )
    print()

    passed = 0
    failed = 0

    for test in TEST_CASES:
        try:
            actual, reasons = evaluate_command(
                test.command,
                validators,
                config,
            )
        except Exception as exc:
            print(f"FAIL  {test.name}")
            print(f"      exception: {exc}")
            failed += 1
            continue

        if actual == test.expected:
            print(f"PASS  {test.name} [{actual.value}]")
            passed += 1
        else:
            print(f"FAIL  {test.name}")
            print(f"      expected: {test.expected.value}")
            print(f"      actual:   {actual.value}")
            print(f"      command:  {test.command}")
            if reasons:
                print("      reasons:  " + "; ".join(reasons))
            failed += 1

    print()
    print("Actual PermissionRequest dispatcher tests")
    for test in DISPATCHER_CASES:
        try:
            actual = dispatch_command(test.command)
        except Exception as exc:
            print(f"FAIL  {test.name}: dispatcher error: {exc}")
            failed += 1
            continue
        if actual == test.expected:
            print(f"PASS  {test.name} [{actual.value}]")
            passed += 1
        else:
            print(
                f"FAIL  {test.name}: expected {test.expected.value}, "
                f"got {actual.value}"
            )
            failed += 1

    print()
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        print("Result: FAIL")
        return 1

    print("Result: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
