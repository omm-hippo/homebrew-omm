from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_python_resources",
    ROOT / ".github" / "scripts" / "verify_python_resources.py",
)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def block(name: str, version: str, sha: str = "a") -> str:
    normalized = name.replace("_", "-")
    return f'''  resource "{normalized}" do
    url "https://files.pythonhosted.org/packages/{name}-{version}.tar.gz"
    sha256 "{sha * 64}"
  end
'''


class VerifyPythonResourcesTests(unittest.TestCase):
    def test_accepts_matching_resource_sets(self):
        contents = block("click", "8.5.0") + block("filelock", "3.32.4")
        verifier.verify_resources(contents, contents)

    def test_reports_missing_and_stale_resources(self):
        actual = block("click", "8.4.2")
        expected = block("click", "8.5.0") + block("colorama", "0.4.6")
        with self.assertRaisesRegex(
            verifier.ResourceVerificationError,
            "missing: colorama; changed URL/SHA-256: click",
        ):
            verifier.verify_resources(actual, expected)

    def test_rejects_duplicate_resources(self):
        with self.assertRaisesRegex(
            verifier.ResourceVerificationError, "duplicate resource: click"
        ):
            verifier.parse_resources(block("click", "8.5.0") * 2)

    def test_rejects_an_unparsed_resource_in_either_input(self):
        valid = block("click", "8.5.0")
        malformed = block("filelock", "3.32.4").replace('sha256 "', 'sha256 "invalid-')
        for actual, expected in ((valid + malformed, valid), (valid, valid + malformed)):
            with self.subTest(actual=actual, expected=expected):
                with self.assertRaisesRegex(
                    verifier.ResourceVerificationError, "unsupported resource block"
                ):
                    verifier.verify_resources(actual, expected)

    def test_rejects_an_alternative_ruby_resource_syntax(self):
        contents = block("click", "8.5.0") + block("filelock", "3.32.4").replace(
            'resource "filelock"', "resource 'filelock'"
        )
        with self.assertRaisesRegex(
            verifier.ResourceVerificationError, "unsupported resource block"
        ):
            verifier.parse_resources(contents)

    def test_rejects_extra_text_in_generated_output(self):
        valid = block("click", "8.5.0")
        for extra in ('  # RESOURCE-ERROR: unresolved package\n', '  def install\n  end\n'):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(
                    verifier.ResourceVerificationError, "unsupported text"
                ):
                    verifier.replace_resources(valid, valid + extra)

    def test_sync_failure_preserves_the_formula_file(self):
        formula = block("click", "8.4.2")
        generated = block("click", "8.5.0") + '  # RESOURCE-ERROR: unresolved package\n'
        with tempfile.TemporaryDirectory() as directory:
            formula_path = Path(directory) / "omm.rb"
            generated_path = Path(directory) / "resources.rb"
            formula_path.write_text(formula, encoding="utf-8")
            generated_path.write_text(generated, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / ".github/scripts/verify_python_resources.py"),
                 "--sync", "--formula", str(formula_path), "--generated", str(generated_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(formula_path.read_text(encoding="utf-8"), formula)

    def test_replaces_only_the_formula_resource_region(self):
        formula = (
            "class Omm < Formula\n"
            + block("click", "8.4.2")
            + "\n  def install\n    virtualenv_install_with_resources\n  end\nend\n"
        )
        generated = block("click", "8.5.0") + "\n" + block("colorama", "0.4.6")
        updated = verifier.replace_resources(formula, generated)
        self.assertIn("class Omm < Formula", updated)
        self.assertIn("click-8.5.0.tar.gz", updated)
        self.assertIn("colorama-0.4.6.tar.gz", updated)
        self.assertIn("virtualenv_install_with_resources", updated)
        verifier.verify_resources(updated, generated)

    def test_rejects_non_resource_text_inside_the_replaced_region(self):
        formula = block("click", "8.4.2") + "  # unexpected\n" + block("filelock", "3.32.3")
        with self.assertRaisesRegex(
            verifier.ResourceVerificationError, "unsupported text"
        ):
            verifier.replace_resources(formula, block("click", "8.5.0"))


if __name__ == "__main__":
    unittest.main()
