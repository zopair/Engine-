import tarfile

import pytest

from scripts.install_llama_runtime import validate_archive_members


def member(name, kind=tarfile.REGTYPE, linkname=""):
    item = tarfile.TarInfo(name)
    item.type = kind
    item.linkname = linkname
    return item


def test_runtime_archive_allows_relative_symlinks_confined_to_root():
    entries = [
        member("lib/libggml.so", tarfile.SYMTYPE, "libggml.so.1"),
        member("lib/libggml.so.1", tarfile.SYMTYPE, "libggml.so.1.0"),
        member("lib/libggml.so.1.0", tarfile.REGTYPE),
    ]
    assert validate_archive_members(entries) == entries


def test_runtime_archive_rejects_symlink_escape():
    entries = [member("lib/libggml.so", tarfile.SYMTYPE, "../../outside.so")]
    with pytest.raises(RuntimeError, match="escapes extraction root"):
        validate_archive_members(entries)


def test_runtime_archive_rejects_files_nested_under_symlink_parent():
    entries = [
        member("lib", tarfile.SYMTYPE, "actual-lib"),
        member("lib/llama-cli", tarfile.REGTYPE),
    ]
    with pytest.raises(RuntimeError, match="symlink parent"):
        validate_archive_members(entries)


def test_runtime_archive_rejects_special_device_members():
    entries = [member("dev/device", tarfile.CHRTYPE)]
    with pytest.raises(RuntimeError, match="special archive member"):
        validate_archive_members(entries)


def test_runtime_archive_rejects_windows_style_path_separators():
    entries = [member("lib\\..\\outside", tarfile.REGTYPE)]
    with pytest.raises(RuntimeError, match="path separator"):
        validate_archive_members(entries)


def test_runtime_archive_accepts_hard_links_to_internal_regular_files():
    entries = [
        member("lib/libggml.so.1", tarfile.REGTYPE),
        member("lib/libggml.so", tarfile.LNKTYPE, "lib/libggml.so.1"),
    ]
    assert validate_archive_members(entries) == entries


def test_runtime_archive_rejects_hard_links_outside_archive():
    entries = [member("lib/escape", tarfile.LNKTYPE, "../../etc/passwd")]
    with pytest.raises(RuntimeError, match="unsafe hard link"):
        validate_archive_members(entries)


def test_runtime_archive_rejects_hard_links_to_missing_files():
    entries = [member("lib/missing", tarfile.LNKTYPE, "lib/not-present")]
    with pytest.raises(RuntimeError, match="target is missing"):
        validate_archive_members(entries)
