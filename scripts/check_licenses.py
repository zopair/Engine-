"""Fail closed when an installed package has an unapproved license."""

from __future__ import annotations

import re
import sys
from importlib.metadata import distributions

ALLOWED = {"MIT", "Apache-2.0", "BSD-3-Clause"}
# These are bootstrap tools preinstalled by the GitHub Python toolchain, not project dependencies.
BOOTSTRAP_TOOLS = {"pip", "setuptools", "wheel"}


def _spdx_atom(value: str) -> str | None:
    atom = value.strip().strip("()").lower()
    if atom in {"mit", "mit license"}:
        return "MIT"
    if atom in {"apache-2.0", "apache 2.0", "apache software license"}:
        return "Apache-2.0"
    if atom in {"bsd-3-clause", "bsd 3-clause", "bsd 3 clause", "bsd license"}:
        return "BSD-3-Clause"
    return None


def expression_is_approved(expression: str) -> bool:
    """Accept an allowed SPDX choice; every AND-combined obligation must be allowed."""
    expression = re.sub(r"\s+", " ", (expression or "").strip())
    if not expression:
        return False
    alternatives = re.split(r"\s+OR\s+", expression, flags=re.IGNORECASE)
    for alternative in alternatives:
        obligations = re.split(r"\s+AND\s+", alternative, flags=re.IGNORECASE)
        if obligations and all(_spdx_atom(item) in ALLOWED for item in obligations):
            return True
    return False


def license_for(distribution) -> str:
    metadata = distribution.metadata
    expression = metadata.get("License-Expression", "")
    if expression:
        return expression
    license_text = metadata.get("License", "")
    if license_text and license_text.lower() not in {"unknown", "see license"}:
        return license_text
    classifiers = metadata.get_all("Classifier", [])
    for classifier in classifiers:
        prefix = "License :: OSI Approved :: "
        if classifier.startswith(prefix):
            return classifier[len(prefix):]
    return ""


def main() -> int:
    rejected = []
    checked = 0
    for distribution in distributions():
        name = distribution.metadata.get("Name", "unknown")
        if name.lower() in BOOTSTRAP_TOOLS:
            continue
        license_name = license_for(distribution)
        checked += 1
        if not expression_is_approved(license_name):
            rejected.append((name, license_name or "UNKNOWN"))

    if rejected:
        print("Unapproved or unverified licenses:")
        for name, license_name in sorted(rejected):
            print(f"- {name}: {license_name}")
        return 1
    print(f"License allowlist passed for {checked} installed distributions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
