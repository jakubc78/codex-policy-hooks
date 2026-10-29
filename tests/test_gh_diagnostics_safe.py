"""Exercise GitHub diagnostics through the PermissionRequest dispatcher."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dispatcher


REPO = "jakubc78/qnap-document-router"


class GitHubDiagnosticsDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.nested = self.root / "src"
        self.nested.mkdir()
        self.config = {
            "gh_diagnostics_safe": {
                "enabled": True,
                "repository": REPO,
                "project_root": str(self.root),
                "allow_failed_logs": True,
                "allow_full_logs": False,
            }
        }

    def dispatch(self, command, *, config=None, cwd=None):
        payload = {
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(cwd or self.nested),
        }
        output = io.StringIO()
        with patch.object(dispatcher, "load_config", return_value=self.config if config is None else config), \
             patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             redirect_stdout(output):
            self.assertEqual(dispatcher.main(), 0)
        if not output.getvalue():
            return dispatcher.Decision.ABSTAIN
        response = json.loads(output.getvalue())
        self.assertEqual(response["hookSpecificOutput"]["hookEventName"], "PermissionRequest")
        return dispatcher.Decision(response["hookSpecificOutput"]["decision"]["behavior"])

    def test_supported_commands_and_ordering(self):
        commands = [
            f"gh run view 40910865463 --repo {REPO} --log-failed",
            f"gh run view 40910865463 --repo {REPO}",
            f"gh run list --repo {REPO}",
            f"gh pr checks 123 --repo {REPO}",
            f"gh pr view 123 --repo {REPO}",
            f"gh issue view 123 --repo {REPO}",
            f"gh run view --repo {REPO} --log-failed 40910865463",
            f"gh pr view --repo={REPO} 123",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.dispatch(command), dispatcher.Decision.ALLOW)

    def test_bad_commands_abstain(self):
        good = f"gh run view 40910865463 --repo {REPO} --log-failed"
        commands = [
            good.replace(REPO, "someone/other-repo"),
            "gh run view 40910865463 --log-failed",
            f"gh run view --repo {REPO}",
            f"gh run view abc --repo {REPO}",
            f"gh pr checks -1 --repo {REPO}",
            f"gh issue view 0 --repo {REPO}",
            f"gh run view 1 2 --repo {REPO}",
            f"gh run list 123 --repo {REPO}",
            f"gh run list --repo {REPO} --limit 10",
            f"gh pr view 123 --repo {REPO} --json title",
            f"gh issue view 123 --repo {REPO} --jq .title",
            f"gh run view 1 --repo {REPO} --log",
            f"gh run view 1 --repo {REPO} --log-failed --log",
            f"gh run view 1 --repo {REPO} --repo {REPO}",
            f"gh run view 1 --repo https://github.com/{REPO}",
            f"gh run view 1 --repo {REPO} --hostname example.com",
            f"gh run view 1 --repo {REPO} --config x=y",
            f"gh run view 1 --repo {REPO} --token secret",
            good + "; gh run cancel 40910865463",
            good + " && echo unsafe",
            good + " | cat",
            good + " > output.txt",
            good + " $(echo unsafe)",
            good + " `echo unsafe`",
            good + " $TOKEN",
            good + "\necho unsafe",
            f"gh run rerun 1 --repo {REPO}",
            f"gh run cancel 1 --repo {REPO}",
            f"gh workflow run build.yml --repo {REPO}",
            f"gh pr merge 123 --repo {REPO}",
            f"gh issue edit 123 --repo {REPO}",
            f"gh run view 1 --repo '{REPO}",
            "gh run view",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.dispatch(command), dispatcher.Decision.ABSTAIN)

    def test_scope_and_configuration(self):
        command = f"gh run view 40910865463 --repo {REPO} --log-failed"
        cases = [
            ({}, self.nested),
            ({"gh_diagnostics_safe": {}}, self.nested),
            ({"gh_diagnostics_safe": {**self.config["gh_diagnostics_safe"], "enabled": False}}, self.nested),
            ({"gh_diagnostics_safe": {**self.config["gh_diagnostics_safe"], "repository": "bad"}}, self.nested),
            ({"gh_diagnostics_safe": {**self.config["gh_diagnostics_safe"], "project_root": "relative"}}, self.nested),
            ({"gh_diagnostics_safe": {**self.config["gh_diagnostics_safe"], "allow_failed_logs": False}}, self.nested),
            ({"gh_diagnostics_safe": {**self.config["gh_diagnostics_safe"], "allow_failed_logs": "yes"}}, self.nested),
            (self.config, self.root.parent),
        ]
        for config, cwd in cases:
            with self.subTest(config=config, cwd=cwd):
                self.assertEqual(self.dispatch(command, config=config, cwd=cwd), dispatcher.Decision.ABSTAIN)

    def test_full_log_requires_explicit_opt_in(self):
        config = {"gh_diagnostics_safe": {**self.config["gh_diagnostics_safe"], "allow_full_logs": True}}
        self.assertEqual(
            self.dispatch(f"gh run view 1 --repo {REPO} --log", config=config),
            dispatcher.Decision.ALLOW,
        )


if __name__ == "__main__":
    unittest.main()
