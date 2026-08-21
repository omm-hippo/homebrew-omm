#!/usr/bin/env python3
"""Validate an OMM release dispatch before Homebrew inspects PyPI."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen


EXPECTED_REPOSITORY = "omm-hippo/omm"
PACKAGE_NAME = "omm-model"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

JsonObject = dict[str, Any]
FetchJson = Callable[[str, Optional[str]], JsonObject]


class DispatchValidationError(RuntimeError):
    """Raised when the dispatch cannot be tied to a verified public release."""


def fetch_json(url: str, token: Optional[str] = None) -> JsonObject:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "omm-homebrew-release-sync",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS hosts
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise DispatchValidationError(f"expected a JSON object from {url}")
    return payload


def required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise DispatchValidationError(f"missing {name}")
    return value


def validate_dispatch(
    environment: Mapping[str, str], fetch: FetchJson = fetch_json
) -> str:
    token = required(environment, "GH_TOKEN")
    version = required(environment, "REQUESTED_VERSION")
    repository = required(environment, "SOURCE_REPOSITORY")
    source_run_id = required(environment, "SOURCE_RUN_ID")
    source_sha = required(environment, "SOURCE_SHA")
    source_tag = required(environment, "SOURCE_TAG")

    if repository != EXPECTED_REPOSITORY:
        raise DispatchValidationError(f"unexpected source repository: {repository}")
    if not source_run_id.isascii() or not source_run_id.isdecimal():
        raise DispatchValidationError("source run ID must be numeric")
    if not VERSION_PATTERN.fullmatch(version):
        raise DispatchValidationError(f"invalid release version: {version}")
    if source_tag != f"v{version}":
        raise DispatchValidationError(
            f"tag {source_tag!r} does not match version {version!r}"
        )
    if not SHA_PATTERN.fullmatch(source_sha):
        raise DispatchValidationError("source SHA must be a lowercase 40-digit SHA")

    encoded_tag = quote(source_tag, safe="")
    ref = fetch(
        f"https://api.github.com/repos/{repository}/git/ref/tags/{encoded_tag}",
        token,
    )
    tag_reference = ref.get("object")
    if not isinstance(tag_reference, dict) or tag_reference.get("type") != "tag":
        raise DispatchValidationError("release ref is not an annotated tag")

    tag_sha = tag_reference.get("sha")
    if not isinstance(tag_sha, str) or not SHA_PATTERN.fullmatch(tag_sha):
        raise DispatchValidationError("release tag object has an invalid SHA")
    tag_object = fetch(
        f"https://api.github.com/repos/{repository}/git/tags/{tag_sha}", token
    )
    verification = tag_object.get("verification")
    if not isinstance(verification, dict) or verification.get("verified") is not True:
        reason = verification.get("reason") if isinstance(verification, dict) else None
        raise DispatchValidationError(f"release tag signature is not verified: {reason}")

    target = tag_object.get("object")
    if not isinstance(target, dict) or target.get("type") != "commit":
        raise DispatchValidationError("release tag does not point directly to a commit")
    if target.get("sha") != source_sha:
        raise DispatchValidationError("release tag commit does not match source SHA")

    release = fetch(
        f"https://pypi.org/pypi/{PACKAGE_NAME}/{quote(version, safe='')}/json", None
    )
    info = release.get("info")
    if not isinstance(info, dict) or info.get("version") != version:
        raise DispatchValidationError("PyPI returned a different package version")
    files = release.get("urls")
    if not isinstance(files, list) or not any(
        isinstance(file, dict)
        and file.get("packagetype") == "sdist"
        and file.get("yanked") is not True
        for file in files
    ):
        raise DispatchValidationError("PyPI release has no non-yanked source archive")

    return version


def main() -> int:
    try:
        version = validate_dispatch(os.environ)
    except (DispatchValidationError, OSError, json.JSONDecodeError) as error:
        print(f"Homebrew release dispatch validation failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated signed OMM v{version} and public PyPI {PACKAGE_NAME} {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
