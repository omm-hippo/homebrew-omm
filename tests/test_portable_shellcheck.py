"""Check the CI download boundary without contacting a release service."""

import hashlib
import io
import os
import subprocess
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_SHA256 = "3c89db4edcab7cf1c27bff178882e0f6f27f7afdf54e859fa041fca10febe4c6"


class PortableShellcheckTests(unittest.TestCase):
    def run_setup(self, *, valid_checksum=True, download_status=0, selection_status=0):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text()
        step = workflow.split("      - name: Prepare portable ShellCheck on Intel macOS\n", 1)[1]
        step = step.split("\n      - name:", 1)[0]
        self.assertIn("if: matrix.os == 'macos-15-intel'", step)
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])

        with tempfile.TemporaryDirectory(prefix="omm shellcheck ") as directory:
            sandbox = Path(directory)
            fixture = sandbox / "fixture.tar.xz"
            executable = b"#!/bin/sh\nprintf 'version: 0.11.0\\n'\n"
            with tarfile.open(fixture, "w:xz") as archive:
                member = tarfile.TarInfo("shellcheck-v0.11.0/shellcheck")
                member.mode = 0o755
                member.size = len(executable)
                archive.addfile(member, io.BytesIO(executable))
            # Substitute the fixture's digest only for the successful download
            # case. The rejected case retains the real pinned release digest.
            if valid_checksum:
                self.assertEqual(script.count(RELEASE_SHA256), 1)
                script = script.replace(RELEASE_SHA256, hashlib.sha256(fixture.read_bytes()).hexdigest())
            curl = sandbox / "curl"
            curl.write_text('''#!/bin/sh
test "$DOWNLOAD_STATUS" = 0 || exit "$DOWNLOAD_STATUS"
while [ "$#" -gt 0 ]; do
  if [ "$1" = --output ]; then
    cp "$FIXTURE" "$2"
    exit 0
  fi
  shift
done
exit 90
''')
            curl.chmod(0o755)
            brew = sandbox / "brew"
            brew.write_text('''#!/bin/sh
test "$1" = ruby || exit 90
exit "$SELECTION_STATUS"
''')
            brew.chmod(0o755)
            path_file = sandbox / "github-path"
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", script],
                capture_output=True, text=True, check=False,
                env={
                    **os.environ,
                    "PATH": f"{sandbox}{os.pathsep}{os.environ['PATH']}",
                    "RUNNER_TEMP": str(sandbox),
                    "GITHUB_PATH": str(path_file),
                    "FIXTURE": str(fixture),
                    "DOWNLOAD_STATUS": str(download_status),
                    "SELECTION_STATUS": str(selection_status),
                },
            )
            extracted = (sandbox / "omm-shellcheck/shellcheck-v0.11.0/shellcheck").exists()
            exported = path_file.read_text() if path_file.exists() else ""
            return result, extracted, exported

    def test_verified_download_is_executed_and_added_to_path(self):
        result, extracted, exported = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(extracted)
        self.assertIn("version: 0.11.0", result.stdout)
        self.assertTrue(exported.endswith("/omm-shellcheck/shellcheck-v0.11.0\n"))

    def test_checksum_mismatch_stops_before_extraction_or_path_export(self):
        result, extracted, exported = self.run_setup(valid_checksum=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse(extracted)
        self.assertEqual(exported, "")

    def test_download_failure_stops_before_extraction_or_path_export(self):
        result, extracted, exported = self.run_setup(download_status=22)
        self.assertEqual(result.returncode, 22)
        self.assertFalse(extracted)
        self.assertEqual(exported, "")

    def test_homebrew_selection_failure_stops_before_path_export(self):
        result, extracted, exported = self.run_setup(selection_status=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(extracted)
        self.assertEqual(exported, "")


if __name__ == "__main__":
    unittest.main()
