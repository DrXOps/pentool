"""Test that PRO plan features return True (not broken by missing plan_order entry)."""

from pentool.core.features import get_limit, has_feature


def test_pro_plan_has_payloads_pro():
    assert has_feature("payloads_pro", "pro") is True


def test_free_plan_no_payloads_pro():
    assert has_feature("payloads_pro", "free") is False


def test_pro_limit_threads():
    limit = get_limit("scanner_threads", "pro")
    assert limit > 5  # PRO must have more than FREE


def test_enterprise_has_all_features():
    # enterprise must have every feature that pro has
    assert has_feature("payloads_pro", "enterprise") is True
