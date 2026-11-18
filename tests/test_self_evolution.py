import pytest

from evolution.self_evolution import EvolutionError, validate_patch


def test_evolution_accepts_small_patch_with_test_in_allowed_paths():
    patch = (
        "--- a/core/example.py\n+++ b/core/example.py\n@@ -1 +1 @@\n-old\n+new\n"
        "--- a/tests/test_example.py\n+++ b/tests/test_example.py\n@@ -1 +1 @@\n-old\n+new\n"
    )
    assert validate_patch(patch) == ["core/example.py", "tests/test_example.py"]


@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml",
    "requirements.txt",
    "README.md",
    "docs/index.html",
    "evolution/self_evolution.py",
    "../outside.py",
])
def test_evolution_rejects_sensitive_or_outside_paths(path):
    patch = f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n"
    with pytest.raises(EvolutionError):
        validate_patch(patch)


def test_evolution_rejects_large_patches_and_too_many_files():
    with pytest.raises(EvolutionError, match="80 KB"):
        validate_patch("--- a/core/a.py\n+++ b/core/a.py\n" + ("x" * 81_000))
    patch = "".join(f"--- a/core/{i}.py\n+++ b/core/{i}.py\n" for i in range(9))
    with pytest.raises(EvolutionError, match="maximum 8"):
        validate_patch(patch)
