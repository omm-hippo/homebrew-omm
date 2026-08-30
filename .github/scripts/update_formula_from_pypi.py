#!/usr/bin/env python3
"""Update OMM's Formula source archive from a verified PyPI release."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


PACKAGE_NAME = "omm-model"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_PATTERN = re.compile(
    r'^(?P<indent>  )url "(?P<url>https://files\.pythonhosted\.org/[^"\n]+/'
    r'omm_model-(?P<version>[0-9]+\.[0-9]+\.[0-9]+)\.tar\.gz)"\n'
    r'(?P=indent)sha256 "(?P<sha256>[0-9a-f]{64})"$',
    re.MULTILINE,
)


class FormulaUpdateError(RuntimeError):
    """Raised when PyPI metadata or the Formula cannot be updated safely."""


def version_tuple(version: str) -> tuple[int, int, int]:
    if not VERSION_PATTERN.fullmatch(version):
        raise FormulaUpdateError(f"invalid release version: {version}")
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def fetch_release(version: str) -> dict[str, Any]:
    url = f"https://pypi.org/pypi/{PACKAGE_NAME}/{quote(version, safe='')}/json"
    request = Request(url, headers={"User-Agent": "omm-homebrew-release-sync"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS host
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise FormulaUpdateError("PyPI returned a non-object response")
    return payload


def select_source_archive(
    release: dict[str, Any], version: str
) -> tuple[str, str]:
    version_tuple(version)
    info = release.get("info")
    if not isinstance(info, dict) or info.get("version") != version:
        raise FormulaUpdateError("PyPI returned a different package version")

    expected_filename = f"omm_model-{version}.tar.gz"
    files = release.get("urls")
    if not isinstance(files, list):
        raise FormulaUpdateError("PyPI release has no file list")

    candidates = [
        file
        for file in files
        if isinstance(file, dict)
        and file.get("packagetype") == "sdist"
        and file.get("filename") == expected_filename
        and file.get("yanked") is not True
    ]
    if len(candidates) != 1:
        raise FormulaUpdateError(
            f"expected exactly one non-yanked {expected_filename}, found {len(candidates)}"
        )

    candidate = candidates[0]
    url = candidate.get("url")
    digests = candidate.get("digests")
    sha256 = digests.get("sha256") if isinstance(digests, dict) else None
    if not isinstance(url, str):
        raise FormulaUpdateError("PyPI source archive has no URL")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
        raise FormulaUpdateError(f"unexpected PyPI source host: {url}")
    if not parsed.path.endswith(f"/{expected_filename}"):
        raise FormulaUpdateError(f"unexpected PyPI source path: {url}")
    if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
        raise FormulaUpdateError("PyPI source archive has an invalid SHA-256")
    return url, sha256


def update_formula_source(
    contents: str, version: str, url: str, sha256: str
) -> str:
    target_version = version_tuple(version)
    if not SHA256_PATTERN.fullmatch(sha256):
        raise FormulaUpdateError("invalid source SHA-256")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
        raise FormulaUpdateError(f"unexpected source host: {url}")
    if not parsed.path.endswith(f"/omm_model-{version}.tar.gz"):
        raise FormulaUpdateError(f"source URL does not match version {version}: {url}")

    matches = list(SOURCE_PATTERN.finditer(contents))
    if len(matches) != 1:
        raise FormulaUpdateError(
            f"expected exactly one top-level OMM source block, found {len(matches)}"
        )
    match = matches[0]
    current_version = match.group("version")
    if target_version < version_tuple(current_version):
        raise FormulaUpdateError(
            f"refusing to downgrade Formula from {current_version} to {version}"
        )

    replacement = f'  url "{url}"\n  sha256 "{sha256}"'
    return contents[: match.start()] + replacement + contents[match.end() :]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formula", type=Path, default=Path("Formula/omm.rb"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    release = fetch_release(args.version)
    url, sha256 = select_source_archive(release, args.version)
    original = args.formula.read_text(encoding="utf-8")
    updated = update_formula_source(original, args.version, url, sha256)
    if updated != original:
        args.formula.write_text(updated, encoding="utf-8")
        print(f"Updated {args.formula} to {PACKAGE_NAME} {args.version}")
    else:
        print(f"{args.formula} already uses {PACKAGE_NAME} {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
