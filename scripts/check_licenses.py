"""Fail closed when an installed package has an unapproved license."""

from __future__ import annotations

import json
import re
import subprocess
import sys


def normalize(value: str) -> str | None:
    license_text = re.sub(r"\s+", " ", (value or "").strip().lower())
    if "mit" in license_text:
        return "MIT"
    if "apache" in license_text and ("2.0" in license_text or "2" in license_text):
        return "Apache-2.0"
    if "bsd" in license_text and ("3-clause" in license_text or "3 clause" in license_text or "bsd-3" in license_text):
        return "BSD-3-Clause"
    return None


def main() -> int:
    try:
        output = subprocess.check_output(["pip-licenses", "--format=json"], text=True)
        packages = json.loads(output)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"license audit could not run: {exc}", file=sys.stderr)
        return 2

    rejected = []
    for package in packages:
        name = package.get("Name", "unknown")
        license_name = package.get("License", "")
        if normalize(license_name) is None:
            rejected.append((name, license_name or "UNKNOWN"))
    if rejected:
        print("Unapproved or unverified licenses:")
        for name, license_name in rejected:
            print(f"- {name}: {license_name}")
        return 1
    print(f"License allowlist passed for {len(packages)} installed packages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
