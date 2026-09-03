from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "update_formula_from_pypi",
    ROOT / ".github" / "scripts" / "update_formula_from_pypi.py",
)
assert SPEC is not None and SPEC.loader is not None
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UpdateFormulaFromPyPITests(unittest.TestCase):
    def release(self, version="1.2.3", *, yanked=False):
        return {
            "info": {"version": version},
            "urls": [
                {
                    "packagetype": "sdist",
                    "filename": f"omm_model-{version}.tar.gz",
                    "yanked": yanked,
                    "url": (
                        "https://files.pythonhosted.org/packages/aa/bb/"
                        f"omm_model-{version}.tar.gz"
                    ),
                    "digests": {"sha256": "a" * 64},
                }
            ],
        }

    def formula(self, version="1.2.2"):
        return f'''class Omm < Formula
  url "https://files.pythonhosted.org/packages/old/omm_model-{version}.tar.gz"
  sha256 "{'b' * 64}"

  resource "click" do
    url "https://files.pythonhosted.org/packages/click-8.4.2.tar.gz"
    sha256 "{'c' * 64}"
  end
end
'''

    def test_selects_the_exact_non_yanked_source_archive(self):
        self.assertEqual(
            updater.select_source_archive(self.release(), "1.2.3"),
            (
                "https://files.pythonhosted.org/packages/aa/bb/omm_model-1.2.3.tar.gz",
                "a" * 64,
            ),
        )

    def test_rejects_a_yanked_source_archive(self):
        with self.assertRaisesRegex(
            updater.FormulaUpdateError, "exactly one non-yanked"
        ):
            updater.select_source_archive(self.release(yanked=True), "1.2.3")

    def test_rejects_mismatched_release_metadata(self):
        release = self.release()
        release["info"]["version"] = "9.9.9"
        with self.assertRaisesRegex(
            updater.FormulaUpdateError, "different package version"
        ):
            updater.select_source_archive(release, "1.2.3")

    def test_rejects_urls_that_cannot_be_safely_written_as_ruby(self):
        urls = [
            'https://files.pythonhosted.org/packages/"/omm_model-1.2.3.tar.gz',
            "https://files.pythonhosted.org/packages/\n/omm_model-1.2.3.tar.gz",
            r"https://files.pythonhosted.org/packages/\n/omm_model-1.2.3.tar.gz",
            "https://files.pythonhosted.org/packages/#{code}/omm_model-1.2.3.tar.gz",
            "https://user@files.pythonhosted.org/packages/omm_model-1.2.3.tar.gz",
            "https://files.pythonhosted.org:443/packages/omm_model-1.2.3.tar.gz",
            "https://files.pythonhosted.org/packages/omm_model-1.2.3.tar.gz?download=1",
        ]
        for url in urls:
            with self.subTest(url=url):
                release = self.release()
                release["urls"][0]["url"] = url
                with self.assertRaises(updater.FormulaUpdateError):
                    updater.select_source_archive(release, "1.2.3")
                with self.assertRaises(updater.FormulaUpdateError):
                    updater.update_formula_source(self.formula(), "1.2.3", url, "a" * 64)

    def test_updates_only_the_top_level_source_block(self):
        updated = updater.update_formula_source(
            self.formula(),
            "1.2.3",
            "https://files.pythonhosted.org/packages/new/omm_model-1.2.3.tar.gz",
            "d" * 64,
        )
        self.assertIn("omm_model-1.2.3.tar.gz", updated)
        self.assertIn(f'  sha256 "{"d" * 64}"', updated)
        self.assertIn("click-8.4.2.tar.gz", updated)

    def test_refuses_a_formula_downgrade(self):
        with self.assertRaisesRegex(updater.FormulaUpdateError, "refusing to downgrade"):
            updater.update_formula_source(
                self.formula("2.0.0"),
                "1.2.3",
                "https://files.pythonhosted.org/packages/new/omm_model-1.2.3.tar.gz",
                "d" * 64,
            )


if __name__ == "__main__":
    unittest.main()
