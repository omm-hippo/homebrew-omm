from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def run_fallback(self, **overrides):
        workflow = (ROOT / ".github" / "workflows" / "autobump.yml").read_text()
        step = workflow.split("- name: Ensure a pull request exists for the bump branch", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            log = sandbox / "commands.log"
            stubs = {
                "git": '''#!/bin/sh
case "$*" in
  'branch --show-current') echo bump-omm-1.2.3 ;;
  'ls-remote --heads origin refs/heads/bump-omm-1.2.3')
    if [ "$HAS_REMOTE" = 1 ]; then echo 'abc refs/heads/bump-omm-1.2.3'; fi ;;
  'fetch origin bump-omm-1.2.3') echo fetch >> "$COMMAND_LOG" ;;
  'switch -C bump-omm-1.2.3 origin/bump-omm-1.2.3') echo switch >> "$COMMAND_LOG" ;;
  'rev-list --count origin/main..HEAD') echo 1 ;;
  'diff --name-only origin/main...HEAD') echo "$CHANGED_FILE" ;;
  'push origin HEAD:refs/heads/bump-omm-1.2.3') echo push >> "$COMMAND_LOG" ;;
  *) echo "unexpected git arguments: $*" >&2; exit 90 ;;
esac
''',
                "brew": '''#!/bin/sh
test "$*" = 'audit --strict omm-hippo/omm/omm' || exit 90
echo audit >> "$COMMAND_LOG"
exit "$AUDIT_STATUS"
''',
                "gh": '''#!/bin/sh
case "$1 $2" in
  'pr view') exit 1 ;;
  'pr create') echo create >> "$COMMAND_LOG" ;;
  *) exit 90 ;;
esac
''',
            }
            for name, contents in stubs.items():
                executable = sandbox / name
                executable.write_text(contents)
                executable.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{sandbox}{os.pathsep}{os.environ['PATH']}",
                "COMMAND_LOG": str(log),
                "HAS_REMOTE": "0",
                "AUDIT_STATUS": "0",
                "CHANGED_FILE": "Formula/omm.rb",
                "TAP_NAME": "omm-hippo/omm",
                "GITHUB_REPOSITORY": "omm-hippo/homebrew-omm",
                **overrides,
            }
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", script],
                env=environment, cwd=sandbox, capture_output=True, text=True,
                check=False,
            )
            commands = log.read_text().splitlines() if log.exists() else []
            return result, commands

    def test_fallback_checks_local_commit_before_push_and_pr(self):
        result, commands = self.run_fallback()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(commands, ["audit", "push", "create"])

    def test_fallback_checks_remote_commit_before_reusing_it(self):
        result, commands = self.run_fallback(HAS_REMOTE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(commands, ["fetch", "switch", "audit", "create"])

    def test_fallback_stops_on_audit_failure(self):
        result, commands = self.run_fallback(AUDIT_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(commands, ["audit"])

    def test_fallback_rejects_unrelated_remote_changes(self):
        result, commands = self.run_fallback(HAS_REMOTE="1", CHANGED_FILE="README.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(commands, ["fetch", "switch"])

    def test_homebrew_receives_the_push_credential_after_replacing_checkout(self):
        workflow = (ROOT / ".github" / "workflows" / "autobump.yml").read_text()
        setup = workflow.split("- name: Set up Homebrew", maxsplit=1)[1].split(
            "- name: Set up git", maxsplit=1
        )[0]
        # setup-homebrew replaces the initial actions/checkout .git directory.
        # Its token input must authenticate the resulting Tap checkout.
        self.assertIn("token: ${{ secrets.GITHUB_TOKEN }}", setup)
        self.assertIn("persist-credentials: false", workflow)

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
        self.assertIn('tap_root="$(brew --repository "$TAP_NAME")"', workflow)
        self.assertIn("brew update-python-resources --print-only", workflow)
        self.assertIn("--ignore-main-package-cooldown", workflow)
        self.assertIn("verify_python_resources.py", workflow)


if __name__ == "__main__":
    unittest.main()
