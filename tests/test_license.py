from scripts.check_licenses import expression_is_approved


def test_license_allowlist_accepts_only_permitted_license_options():
    assert expression_is_approved("MIT")
    assert expression_is_approved("Apache-2.0")
    assert expression_is_approved("Apache-2.0 OR BSD-2-Clause")
    assert expression_is_approved("BSD-3-Clause")


def test_license_allowlist_rejects_unapproved_or_unknown_terms():
    assert not expression_is_approved("BSD-2-Clause")
    assert not expression_is_approved("GPL-3.0-only")
    assert not expression_is_approved("")
    assert not expression_is_approved("MIT AND GPL-3.0-only")
