from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_pypi_dispatch",
    ROOT / ".github" / "scripts" / "validate_pypi_dispatch.py",
)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ValidateDispatchTests(unittest.TestCase):
    def setUp(self):
        self.commit = "1" * 40
        self.tag_object = "2" * 40
        self.environment = {
            "GH_TOKEN": "test-token",
            "REQUESTED_VERSION": "1.2.3",
            "SOURCE_REPOSITORY": "omm-hippo/omm",
            "SOURCE_RUN_ID": "123456789",
            "SOURCE_SHA": self.commit,
            "SOURCE_TAG": "v1.2.3",
        }

    def fetch(self, url, token):
        if "/git/ref/tags/" in url:
            self.assertEqual(token, "test-token")
            return {"object": {"type": "tag", "sha": self.tag_object}}
        if "/git/tags/" in url:
            self.assertEqual(token, "test-token")
            return {
                "verification": {"verified": True, "reason": "valid"},
                "object": {"type": "commit", "sha": self.commit},
            }
        if "pypi.org" in url:
            self.assertIsNone(token)
            return {
                "info": {"version": "1.2.3"},
                "urls": [{"packagetype": "sdist", "yanked": False}],
            }
        self.fail(f"unexpected URL: {url}")

    def test_accepts_matching_signed_tag_and_public_sdist(self):
        self.assertEqual(
            validator.validate_dispatch(self.environment, self.fetch), "1.2.3"
        )

    def test_rejects_a_source_repository_outside_omm(self):
        self.environment["SOURCE_REPOSITORY"] = "attacker/omm"
        with self.assertRaisesRegex(
            validator.DispatchValidationError, "unexpected source repository"
        ):
            validator.validate_dispatch(self.environment, self.fetch)

    def test_rejects_a_tag_that_does_not_match_the_version(self):
        self.environment["SOURCE_TAG"] = "v1.2.4"
        with self.assertRaisesRegex(
            validator.DispatchValidationError, "does not match version"
        ):
            validator.validate_dispatch(self.environment, self.fetch)

    def test_rejects_a_non_numeric_source_run_id(self):
        self.environment["SOURCE_RUN_ID"] = "run-123"
        with self.assertRaisesRegex(
            validator.DispatchValidationError, "source run ID must be numeric"
        ):
            validator.validate_dispatch(self.environment, self.fetch)

    def test_rejects_an_unverified_tag_signature(self):
        def unverified(url, token):
            if "/git/ref/tags/" in url:
                return {"object": {"type": "tag", "sha": self.tag_object}}
            return {"verification": {"verified": False, "reason": "bad_email"}}

        with self.assertRaisesRegex(
            validator.DispatchValidationError, "signature is not verified"
        ):
            validator.validate_dispatch(self.environment, unverified)

    def test_rejects_a_different_tag_commit(self):
        def wrong_commit(url, token):
            if "/git/ref/tags/" in url:
                return {"object": {"type": "tag", "sha": self.tag_object}}
            return {
                "verification": {"verified": True, "reason": "valid"},
                "object": {"type": "commit", "sha": "3" * 40},
            }

        with self.assertRaisesRegex(
            validator.DispatchValidationError, "does not match source SHA"
        ):
            validator.validate_dispatch(self.environment, wrong_commit)

    def test_rejects_a_yanked_or_missing_source_archive(self):
        def no_sdist(url, token):
            if "/git/ref/tags/" in url:
                return {"object": {"type": "tag", "sha": self.tag_object}}
            if "/git/tags/" in url:
                return {
                    "verification": {"verified": True, "reason": "valid"},
                    "object": {"type": "commit", "sha": self.commit},
                }
            return {
                "info": {"version": "1.2.3"},
                "urls": [{"packagetype": "bdist_wheel", "yanked": False}],
            }

        with self.assertRaisesRegex(
            validator.DispatchValidationError, "no non-yanked source archive"
        ):
            validator.validate_dispatch(self.environment, no_sdist)


if __name__ == "__main__":
    unittest.main()
