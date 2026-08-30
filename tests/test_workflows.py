from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_verified_dispatch_bumps_source_and_resources_together(self):
        workflow = (ROOT / ".github" / "workflows" / "autobump.yml").read_text()
        dispatch = workflow.split(
            "- name: Prepare the verified PyPI Formula and Python resources", maxsplit=1
        )[1]
        self.assertIn("if: github.event_name == 'repository_dispatch'", dispatch)
        self.assertIn("update_formula_from_pypi.py", dispatch)
        self.assertIn("brew update-python-resources --print-only", dispatch)
        self.assertIn("--ignore-main-package-cooldown", dispatch)
        self.assertIn("--version=\"$version\"", dispatch)
        self.assertIn("--package-name=omm-model", dispatch)
        self.assertIn("verify_python_resources.py", dispatch)
        self.assertIn('test "$changed_paths" = "Formula/omm.rb"', dispatch)
        self.assertIn('git switch -C "$branch" origin/main', dispatch)
        self.assertIn('origin/main..."origin/$branch"', dispatch)
        self.assertIn("differs from the freshly verified Formula", dispatch)

    def test_scheduled_bump_keeps_homebrew_cooldown(self):
        workflow = (ROOT / ".github" / "workflows" / "autobump.yml").read_text()
        bump = workflow.split("- name: Bump formulae", maxsplit=1)[1]
        self.assertIn("if: github.event_name != 'repository_dispatch'", bump)
        self.assertIn("brew bump --no-fork --open-pr", bump)

    def test_pull_requests_re_resolve_python_resources(self):
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text()
        self.assertIn("Verify Formula Python resources match public PyPI metadata", workflow)
        self.assertIn("brew update-python-resources --print-only", workflow)
        self.assertIn("--ignore-main-package-cooldown", workflow)
        self.assertIn("verify_python_resources.py", workflow)


if __name__ == "__main__":
    unittest.main()
