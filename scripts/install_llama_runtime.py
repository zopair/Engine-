"""Install the pinned CPU-only llama.cpp GitHub Release binary."""
from __future__ import annotations

import argparse
import hashlib
import os
import posixpath
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

RUNTIME_URL = "https://github.com/ggml-org/llama.cpp/releases/download/b12503/llama-b12503-bin-ubuntu-x64.tar.gz"
RUNTIME_SHA256 = "0d585f8a78ffdfdc4f6303a089aaa1379c15323b33483b6548c85c774a376a9d"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
REDIRECT_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}



def validate_archive_members(members: list[tarfile.TarInfo]) -> list[tarfile.TarInfo]:
    """Reject traversal and special files while permitting confined library symlinks."""
    normalized: dict[str, tarfile.TarInfo] = {}
    symlink_paths: set[str] = set()
    hardlinks: list[tuple[str, str]] = []

    for member in members:
        if "\\" in member.name:
            raise RuntimeError(f"unsafe archive path separator: {member.name!r}")
        raw_path = PurePosixPath(member.name)
        if raw_path.is_absolute() or ".." in raw_path.parts:
            raise RuntimeError(f"unsafe archive member path: {member.name!r}")
        name = posixpath.normpath(member.name)
        if name in {"", "."} or name.startswith("../") or name in normalized:
            raise RuntimeError(f"unsafe or duplicate archive member path: {member.name!r}")
        normalized[name] = member

        if member.issym():
            link = PurePosixPath(member.linkname)
            if link.is_absolute() or "\\" in member.linkname:
                raise RuntimeError(f"unsafe absolute symlink: {member.name!r} -> {member.linkname!r}")
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname))
            if target in {"..", "."} or target.startswith("../") or target.startswith("/"):
                raise RuntimeError(f"symlink escapes extraction root: {member.name!r} -> {member.linkname!r}")
            symlink_paths.add(name)
        elif member.islnk():
            link = PurePosixPath(member.linkname)
            target = posixpath.normpath(member.linkname)
            if link.is_absolute() or "\\" in member.linkname:
                raise RuntimeError(f"unsafe hard link: {member.name!r} -> {member.linkname!r}")
            hardlinks.append((name, target))
        elif not (member.isdir() or member.isfile()):
            raise RuntimeError(f"unsupported special archive member: {member.name!r}")

    for name in normalized:
        for parent in PurePosixPath(name).parents:
            if str(parent) in symlink_paths:
                raise RuntimeError(f"archive member traverses a symlink parent: {name!r}")

    for name, target in hardlinks:
        linked = normalized.get(target)
        if linked is None or not linked.isfile():
            raise RuntimeError(f"hard link target is missing or not a regular file: {name!r} -> {target!r}")

    return members


def install(destination: str | Path) -> Path:
    target = Path(destination).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    cli = next((Path(root) / "llama-cli" for root, _, names in os.walk(target)
                if "llama-cli" in names and os.access(Path(root) / "llama-cli", os.X_OK)), None)
    if cli is None:
        fd, archive_name = tempfile.mkstemp(prefix="llama-runtime-", suffix=".tar.gz")
        os.close(fd)
        archive = Path(archive_name)
        try:
            request = urllib.request.Request(RUNTIME_URL, headers={"User-Agent": "ENGINE-runtime-installer/1.0"})
            digest, total = hashlib.sha256(), 0
            with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
                if urllib.parse.urlsplit(response.geturl()).hostname not in REDIRECT_HOSTS:
                    raise RuntimeError("llama.cpp release redirected to an untrusted host")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise RuntimeError("llama.cpp runtime archive exceeds 100 MiB")
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != RUNTIME_SHA256:
                raise RuntimeError("llama.cpp runtime SHA-256 mismatch")
            with tarfile.open(archive, "r:gz") as bundle:
                members = bundle.getmembers()
                validate_archive_members(members)
                bundle.extractall(target, members=members)
        finally:
            archive.unlink(missing_ok=True)
        cli = next((Path(root) / "llama-cli" for root, _, names in os.walk(target)
                    if "llama-cli" in names), None)
        if cli is None or not cli.is_file():
            raise RuntimeError("pinned archive does not contain llama-cli")
        cli.chmod(cli.stat().st_mode | 0o111)
    library_dirs = sorted({str(Path(root)) for root, _, names in os.walk(target)
                           if any(name.endswith(".so") for name in names)})
    with open(os.environ.get("GITHUB_ENV", os.devnull), "a", encoding="utf-8") as env:
        env.write(f"ENGINE_LLAMA_CLI_PATH={cli}\n")
        if library_dirs:
            env.write("LD_LIBRARY_PATH=" + ":".join(library_dirs) + ":" +
                      os.environ.get("LD_LIBRARY_PATH", "") + "\n")
    return cli


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", default="~/.cache/engine/llama.cpp")
    args = parser.parse_args()
    print(f"Installed checksum-verified CPU llama.cpp CLI: {install(args.destination)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
