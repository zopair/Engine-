"""Provision GGUF models only from checksum-pinned GitHub Release assets."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

MAX_MODEL_BYTES = 700 * 1024 * 1024
ALLOWED_REDIRECT_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


class ModelProvisionError(RuntimeError):
    pass


def download_model(url: str, expected_sha256: str, destination: str | Path, opener=None) -> Path:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password
            or parsed.fragment or "/releases/download/" not in parsed.path):
        raise ModelProvisionError("Model source must be an HTTPS GitHub Releases asset URL without credentials")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256 or ""):
        raise ModelProvisionError("A pinned 64-character SHA-256 is mandatory")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ModelProvisionError("Model destination must not be a symbolic link")
    if target.is_file():
        existing_digest = hashlib.sha256()
        with target.open("rb") as existing:
            for chunk in iter(lambda: existing.read(1024 * 1024), b""):
                existing_digest.update(chunk)
        if existing_digest.hexdigest().lower() == expected_sha256.lower():
            return target
    request = urllib.request.Request(url, headers={"User-Agent": "ENGINE-model-provisioner/1.0"})
    opener = opener or urllib.request.urlopen
    fd, temporary = tempfile.mkstemp(prefix=".model-", suffix=".part", dir=target.parent)
    digest = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, "wb") as output:
            with opener(request, timeout=60) as response:
                final_host = urllib.parse.urlsplit(response.geturl()).hostname
                if final_host not in ALLOWED_REDIRECT_HOSTS:
                    raise ModelProvisionError("GitHub release redirected to an untrusted host")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_MODEL_BYTES:
                        raise ModelProvisionError("Model asset exceeds the 700 MiB safety limit")
                    digest.update(chunk)
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest().lower() != expected_sha256.lower():
            raise ModelProvisionError("Model asset SHA-256 does not match the pinned digest")
        os.replace(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("ENGINE_MODEL_RELEASE_URL", ""))
    parser.add_argument("--sha256", default=os.getenv("ENGINE_MODEL_SHA256", ""))
    parser.add_argument("--output", default=os.getenv("ENGINE_MODEL_PATH", "~/.cache/engine/models/model.gguf"))
    args = parser.parse_args()
    if not args.url:
        raise SystemExit("No model configured: set a reviewed GitHub Release URL and ENGINE_MODEL_SHA256")
    print(f"Verified GGUF model installed at {download_model(args.url, args.sha256, Path(args.output).expanduser())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
