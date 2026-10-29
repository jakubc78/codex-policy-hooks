"""Synthetic repository tests for the worktree policy and dispatcher."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dispatcher
from validators.git_worktree_safe import evaluate


class GitWorktreeSafeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.space = Path(self.directory.name)
        self.project = self.space / "project"
        self.project.mkdir()
        self.worktrees = self.space / "worktrees"
        self.worktrees.mkdir(mode=0o700)
        self._git(self.project, "init", "-q", "-b", "main")
        self._git(self.project, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                  "commit", "-q", "--allow-empty", "-m", "initial")
        self._git(self.project, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.config = {
            "enabled": True,
            "project_root": str(self.project),
            "worktree_roots": [str(self.worktrees)],
            "allow_tmp_worktrees": False,
            "tmp_name_prefix": "qdr-",
            "allowed_branch_prefixes": ["codex/", "fix/", "feat/"],
            "allowed_base_refs": ["origin/main"],
        }
        self.good = f"git worktree add -b fix/199-codex-runner-exceptions {self.worktrees / 'issue199'} origin/main"

    def _git(self, cwd, *args):
        subprocess.run(["/usr/bin/git", "-C", str(cwd), *args], check=True,
                       capture_output=True, text=True)

    def _context(self, command, cwd=None):
        return dispatcher.Context.from_payload({
            "hook_event_name": "PermissionRequest",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(cwd or self.project),
        })

    def decision(self, command, *, config=None, cwd=None):
        return evaluate(self._context(command, cwd), self.config if config is None else config).decision

    def dispatch(self, command, *, config=None, cwd=None):
        payload = self._context(command, cwd).payload
        output = io.StringIO()
        policy = {"git_worktree_safe": self.config if config is None else config}
        with patch.object(dispatcher, "load_config", return_value=policy), \
             patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             redirect_stdout(output):
            self.assertEqual(dispatcher.main(), 0)
        if not output.getvalue():
            return dispatcher.Decision.ABSTAIN
        result = json.loads(output.getvalue())["hookSpecificOutput"]
        self.assertEqual(result["hookEventName"], "PermissionRequest")
        return dispatcher.Decision(result["decision"]["behavior"])

    def test_allowed_commands_and_dispatcher(self):
        nested = self.project / "src"
        nested.mkdir()
        for prefix in ("codex", "fix", "feat"):
            command = f"git worktree add -b {prefix}/issue199 {self.worktrees / prefix} origin/main"
            with self.subTest(prefix=prefix):
                self.assertEqual(self.decision(command, cwd=nested), dispatcher.Decision.ALLOW)
                self.assertEqual(self.dispatch(command, cwd=nested), dispatcher.Decision.ALLOW)
        self.assertFalse((self.worktrees / "fix").exists())
        self.assertFalse((self.project / ".git/refs/heads/fix/issue199").exists())

    def test_tmp_compatibility_is_separate_opt_in(self):
        command = f"git worktree add -b fix/199-codex-runner-exceptions /tmp/qdr-{self.space.name} origin/main"
        self.assertEqual(self.decision(command), dispatcher.Decision.ABSTAIN)
        config = {**self.config, "allow_tmp_worktrees": True}
        self.assertEqual(self.dispatch(command, config=config), dispatcher.Decision.ALLOW)
        for destination in ("/tmp/other-issue199", "/tmp/qdr-../escape", "/tmp/qdr-bad/name",
                            "/tmp/qdr-", "/tmp/qdr-issue199/child"):
            with self.subTest(destination=destination):
                candidate = f"git worktree add -b fix/x {destination} origin/main"
                self.assertEqual(self.decision(candidate, config=config), dispatcher.Decision.ABSTAIN)

    def test_invalid_commands_abstain(self):
        commands = [
            self.good + " extra", self.good + " --force", self.good + " ; echo unsafe",
            self.good + " && echo unsafe", self.good + " | cat", self.good + " > out",
            self.good + " $(echo unsafe)", self.good + " $DEST", self.good + "\necho unsafe",
            self.good.replace("add -b", "add -B"),
            self.good.replace("add -b", "add --force -b"),
            self.good.replace("add -b", "add --detach -b"),
            self.good.replace("add -b", "add --orphan -b"),
            self.good.replace("add -b", "add --lock -b"),
            self.good.replace("add -b", "add --reason test -b"),
            self.good.replace("fix/199-codex-runner-exceptions", "-bad"),
            self.good.replace("fix/199-codex-runner-exceptions", "fix/bad..name"),
            self.good.replace("fix/199-codex-runner-exceptions", "fix/bad name"),
            self.good.replace("fix/199-codex-runner-exceptions", "other/new"),
            self.good.replace("origin/main", "HEAD~1"),
            self.good.replace("origin/main", "origin/other"),
            self.good.replace("origin/main", "v1.0"),
            self.good.replace("git worktree", "git -c core.hooksPath=/tmp worktree"),
            self.good.replace("git worktree", "/usr/bin/git worktree"),
            "git worktree remove /tmp/example", "git worktree prune",
            "git worktree move a b", "git worktree repair", "git branch -D fix/x",
            "git worktree add -b fix/x 'unterminated",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.dispatch(command), dispatcher.Decision.ABSTAIN)

    def test_repository_and_branch_state(self):
        self._git(self.project, "branch", "fix/199-codex-runner-exceptions")
        self.assertEqual(self.decision(self.good), dispatcher.Decision.ABSTAIN)
        self._git(self.project, "branch", "-D", "fix/199-codex-runner-exceptions")
        linked = self.space / "linked"
        self._git(self.project, "worktree", "add", "-q", "-b", "fix/used", str(linked), "origin/main")
        used = self.good.replace("fix/199-codex-runner-exceptions", "fix/used")
        self.assertEqual(self.decision(used), dispatcher.Decision.ABSTAIN)
        self.assertEqual(self.decision(self.good, cwd=linked), dispatcher.Decision.ABSTAIN)
        nested = self.project / "nested"
        nested.mkdir()
        self._git(nested, "init", "-q")
        self.assertEqual(self.dispatch(self.good, cwd=nested), dispatcher.Decision.ABSTAIN)
        other = self.space / "other"
        other.mkdir()
        self._git(other, "init", "-q")
        self.assertEqual(self.decision(self.good, cwd=other), dispatcher.Decision.ABSTAIN)
        self._git(self.project, "update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(self.decision(self.good), dispatcher.Decision.ABSTAIN)

    def test_symbolic_base_reference_abstains(self):
        self._git(self.project, "symbolic-ref", "refs/remotes/origin/alias", "refs/remotes/origin/main")
        config = {**self.config, "allowed_base_refs": ["origin/alias"]}
        command = self.good.replace("origin/main", "origin/alias")
        self.assertEqual(self.decision(command, config=config), dispatcher.Decision.ABSTAIN)

    def test_destinations_and_unsafe_parent(self):
        for destination in ("relative", str(self.project / "inside"),
                            str(self.space / "outside"), str(self.worktrees / "nested/child")):
            command = f"git worktree add -b fix/new {destination} origin/main"
            with self.subTest(destination=destination):
                self.assertEqual(self.decision(command), dispatcher.Decision.ABSTAIN)
        occupied = self.worktrees / "occupied"
        occupied.touch()
        self.assertEqual(self.decision(f"git worktree add -b fix/new {occupied} origin/main"),
                         dispatcher.Decision.ABSTAIN)
        symlink = self.worktrees / "link"
        symlink.symlink_to(self.space / "outside")
        self.assertEqual(self.decision(f"git worktree add -b fix/new {symlink} origin/main"),
                         dispatcher.Decision.ABSTAIN)
        self.worktrees.chmod(0o777)
        self.assertEqual(self.decision(self.good), dispatcher.Decision.ABSTAIN)

    def test_missing_disabled_and_malformed_configuration(self):
        bad_configs = [
            {}, {**self.config, "enabled": False},
            {**self.config, "project_root": "relative"},
            {**self.config, "project_root": str(self.space)},
            {**self.config, "worktree_roots": "wrong"},
            {**self.config, "worktree_roots": ["relative"]},
            {**self.config, "allow_tmp_worktrees": "yes"},
            {**self.config, "tmp_name_prefix": "other-"},
            {**self.config, "allowed_branch_prefixes": ["-"]},
            {**self.config, "allowed_base_refs": ["HEAD~1"]},
        ]
        for config in bad_configs:
            with self.subTest(config=config):
                self.assertEqual(self.dispatch(self.good, config=config), dispatcher.Decision.ABSTAIN)


if __name__ == "__main__":
    unittest.main()
