import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validators"))
from dispatcher import Context, Decision
from validators.gh_api_subissue_link import evaluate


class SubissueLinkTests(unittest.TestCase):
    def test_scoped_link_and_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {"repository": "jakubc78/qnap-document-router", "project_root": directory}

            def decision(command, cwd=None):
                context = Context.from_payload({
                    "hook_event_name": "PermissionRequest",
                    "tool_input": {"command": command},
                    "cwd": str(cwd or root),
                    "tool_name": "functions.command",
                })
                return evaluate(context, config).decision

            good = "gh api --method POST repos/jakubc78/qnap-document-router/issues/168/sub_issues -F sub_issue_id=123456"
            self.assertEqual(decision(good), Decision.ALLOW)
            self.assertEqual(decision(good + " ; echo unexpected"), Decision.ABSTAIN)
            self.assertEqual(decision(good + " --input /tmp/a"), Decision.ABSTAIN)
            self.assertEqual(decision(good.replace("POST", "DELETE")), Decision.ABSTAIN)
            self.assertEqual(decision(good.replace("sub_issue_id=123456", "sub_issue_id=abc")), Decision.ABSTAIN)
            self.assertEqual(decision(good.replace("qnap-document-router", "other-repo")), Decision.ABSTAIN)
            self.assertEqual(decision(good.replace("/sub_issues", "/comments")), Decision.ABSTAIN)
            self.assertEqual(decision(good, root.parent), Decision.ABSTAIN)


if __name__ == "__main__":
    unittest.main()
