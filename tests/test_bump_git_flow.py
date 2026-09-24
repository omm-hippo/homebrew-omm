"""Exercise workflow shell and real local Git, with no GitHub/PyPI/brew calls."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRANCH = "bump-omm-1.2.3"


class BumpGitFlowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.sandbox = Path(temporary.name)
        self.checkout = self.sandbox / "tap"
        self.origin = self.sandbox / "origin.git"
        self.bin = self.sandbox / "bin"
        self.bin.mkdir()
        self.environment = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "TAP_NAME": "omm-hippo/omm",
            "GITHUB_REPOSITORY": "omm-hippo/homebrew-omm",
            "RUNNER_TEMP": str(self.sandbox),
            "REQUESTED_VERSION": "1.2.3",
            "AUDITED_FORMULA": str(self.sandbox / "audited.rb"),
            "CREATED_PR": str(self.sandbox / "created-pr"),
            "PR_STATE": "NONE",
            "PR_LIST_STATUS": "0",
            "PYPI_RELEASE": json.dumps({
                "info": {"version": "1.2.3"},
                "urls": [{
                    "packagetype": "sdist",
                    "filename": "omm_model-1.2.3.tar.gz",
                    "url": "https://files.pythonhosted.org/packages/new/omm_model-1.2.3.tar.gz",
                    "digests": {"sha256": "a" * 64},
                }],
            }),
        }
        self.git("init", "--bare", str(self.origin), cwd=self.sandbox)
        self.git("init", "--initial-branch=main", str(self.checkout), cwd=self.sandbox)
        shutil.copytree(
            ROOT / ".github", self.checkout / ".github",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        (self.checkout / "Formula").mkdir()
        self.formula = self.checkout / "Formula" / "omm.rb"
        self.formula.write_text((ROOT / "Formula" / "omm.rb").read_text())
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "origin", "main")

        self.stub("brew", '''#!/bin/sh
case "$1" in
  audit) cp Formula/omm.rb "$AUDITED_FORMULA" ;;
  update-python-resources)
    sed -n '/^  resource /,/^  end$/p' Formula/omm.rb ;;
  *) echo "unexpected brew command: $*" >&2; exit 90 ;;
esac
''')
        self.stub("gh", '''#!/bin/sh
case "$1 $2" in
  'pr list')
    if [ "$PR_LIST_STATUS" != 0 ]; then
      echo 'PR lookup failed' >&2
      exit "$PR_LIST_STATUS"
    fi
    if [ "$PR_STATE" = OPEN ]; then echo 1; else echo 0; fi ;;
  'pr view') test "$PR_STATE" != NONE ;;
  'pr create') touch "$CREATED_PR" ;;
  *) echo "unexpected gh command: $*" >&2; exit 90 ;;
esac
''')
        # Run the real updater and resource verifier, replacing only urlopen.
        self.stub("python3", f'''#!{sys.executable}
import io
import os
import runpy
import sys
from unittest.mock import patch
sys.argv = sys.argv[1:]
with patch("urllib.request.urlopen", return_value=io.StringIO(os.environ["PYPI_RELEASE"])):
    runpy.run_path(sys.argv[0], run_name="__main__")
''')

    def git(self, *arguments, cwd=None, check=True):
        return subprocess.run(
            ["git", *arguments], cwd=cwd or self.checkout,
            env=self.environment, capture_output=True, text=True, check=check,
        )

    def stub(self, name, contents):
        executable = self.bin / name
        executable.write_text(contents)
        executable.chmod(0o755)

    def run_step(self, step_name):
        workflow = (ROOT / ".github/workflows/autobump.yml").read_text()
        step = workflow.split(f"      - name: {step_name}\n", 1)[1]
        step = step.split("\n      - name:", 1)[0]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", script], cwd=self.checkout,
            env=self.environment, capture_output=True, text=True, errors="replace", check=False,
        )

    def prepare_fallback(self):
        self.git("switch", "-c", BRANCH)
        self.formula.write_text(self.formula.read_text() + "# committed change\n")
        self.git("add", "Formula/omm.rb")
        self.git("commit", "-m", "bump")

    def test_fallback_pushes_the_exact_audited_formula(self):
        self.prepare_fallback()
        result = self.run_step("Ensure a pull request exists for the bump branch")
        self.assertEqual(result.returncode, 0, result.stderr)
        pushed = self.git("show", f"{BRANCH}:Formula/omm.rb", cwd=self.origin).stdout
        self.assertEqual(pushed, (self.sandbox / "audited.rb").read_text())
        self.assertTrue((self.sandbox / "created-pr").exists())

    def test_fallback_never_pushes_a_commit_different_from_the_dirty_checkout(self):
        self.prepare_fallback()
        self.formula.write_text(self.formula.read_text() + "# uncommitted change\n")
        result = self.run_step("Ensure a pull request exists for the bump branch")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.sandbox / "audited.rb").exists())
        self.assertNotEqual(
            self.git("show-ref", "--verify", f"refs/heads/{BRANCH}",
                     cwd=self.origin, check=False).returncode,
            0,
        )

    def test_dispatch_updates_pushes_and_creates_a_pr_after_a_closed_pr(self):
        self.environment["PR_STATE"] = "CLOSED"
        result = self.run_step("Prepare the verified PyPI Formula and Python resources")
        self.assertEqual(result.returncode, 0, result.stderr)
        pushed = self.git("show", f"{BRANCH}:Formula/omm.rb", cwd=self.origin).stdout
        self.assertIn("omm_model-1.2.3.tar.gz", pushed)
        self.assertEqual(pushed, (self.sandbox / "audited.rb").read_text())
        self.assertTrue((self.sandbox / "created-pr").exists())

    def test_dispatch_does_not_treat_a_failed_pr_query_as_no_pr(self):
        self.environment["PR_LIST_STATUS"] = "1"
        result = self.run_step("Prepare the verified PyPI Formula and Python resources")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PR lookup failed", result.stderr)
        self.assertFalse((self.sandbox / "created-pr").exists())

    def test_dispatch_retry_reuses_the_verified_remote_branch_and_open_pr(self):
        step = "Prepare the verified PyPI Formula and Python resources"
        first = self.run_step(step)
        self.assertEqual(first.returncode, 0, first.stderr)
        original_sha = self.git("rev-parse", BRANCH, cwd=self.origin).stdout
        (self.sandbox / "created-pr").unlink()
        self.environment["PR_STATE"] = "OPEN"
        retry = self.run_step(step)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(self.git("rev-parse", BRANCH, cwd=self.origin).stdout, original_sha)
        self.assertFalse((self.sandbox / "created-pr").exists())


if __name__ == "__main__":
    unittest.main()
