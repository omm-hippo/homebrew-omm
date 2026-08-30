#!/usr/bin/env python3
"""Compare Formula resource blocks with Homebrew's PyPI resolver output."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import NamedTuple


RESOURCE_PATTERN = re.compile(
    r'^  resource "(?P<name>[^"]+)" do\n'
    r'    url "(?P<url>https://[^"\n]+)"\n'
    r'    sha256 "(?P<sha256>[0-9a-f]{64})"\n'
    r"  end$",
    re.MULTILINE,
)


class ResourceVerificationError(RuntimeError):
    """Raised when Formula resources differ from Homebrew's resolved set."""


class Resource(NamedTuple):
    url: str
    sha256: str


def parse_resources(contents: str) -> dict[str, Resource]:
    resources: dict[str, Resource] = {}
    for match in RESOURCE_PATTERN.finditer(contents):
        name = match.group("name")
        if name in resources:
            raise ResourceVerificationError(f"duplicate resource: {name}")
        resources[name] = Resource(
            url=match.group("url"), sha256=match.group("sha256")
        )
    if not resources:
        raise ResourceVerificationError("no Python resources found")
    return resources


def verify_resources(formula: str, generated: str) -> None:
    actual = parse_resources(formula)
    expected = parse_resources(generated)
    if actual == expected:
        return

    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = sorted(
        name
        for name in actual.keys() & expected.keys()
        if actual[name] != expected[name]
    )
    details = []
    if missing:
        details.append(f"missing: {', '.join(missing)}")
    if extra:
        details.append(f"extra: {', '.join(extra)}")
    if changed:
        details.append(f"changed URL/SHA-256: {', '.join(changed)}")
    raise ResourceVerificationError("Formula resources do not match PyPI: " + "; ".join(details))


def replace_resources(formula: str, generated: str) -> str:
    actual_matches = list(RESOURCE_PATTERN.finditer(formula))
    if not actual_matches:
        raise ResourceVerificationError("Formula has no Python resources to replace")
    parse_resources(generated)
    start = actual_matches[0].start()
    end = actual_matches[-1].end()
    between = formula[start:end]
    parsed_between = "\n\n".join(match.group(0) for match in actual_matches)
    if between.strip() != parsed_between.strip():
        raise ResourceVerificationError(
            "Formula resource region contains unsupported text"
        )
    return formula[:start] + generated.strip("\n") + formula[end:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--formula", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Replace the Formula resource region before verifying it.",
    )
    args = parser.parse_args()
    formula = args.formula.read_text(encoding="utf-8")
    generated = args.generated.read_text(encoding="utf-8")
    if args.sync:
        formula = replace_resources(formula, generated)
        args.formula.write_text(formula, encoding="utf-8")
    verify_resources(formula, generated)
    print("Formula Python resources match Homebrew's PyPI resolution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
