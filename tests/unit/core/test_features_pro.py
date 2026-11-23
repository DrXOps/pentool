"""Plan/feature helpers: PRO must unlock what it advertises, FREE must not."""

from __future__ import annotations

from pentool.core.features import (
    FEATURE_AI_ANALYSIS,
    FEATURE_AI_DISCOVERY,
    FEATURE_PAYLOADS_PRO,
    FEATURE_REPORTS_PRO,
    FEATURE_SCANNER_PRO,
    get_feature_status,
    get_limit,
    has_feature,
)


def test_pro_plan_has_payloads_pro():
    assert has_feature(FEATURE_PAYLOADS_PRO, "pro") is True


def test_free_plan_no_payloads_pro():
    assert has_feature(FEATURE_PAYLOADS_PRO, "free") is False


def test_pro_limit_threads():
    assert get_limit("intruder_max_threads", "pro") > get_limit("intruder_max_threads", "free")


def test_enterprise_has_all_features():
    for feature in (FEATURE_SCANNER_PRO, FEATURE_AI_DISCOVERY, FEATURE_AI_ANALYSIS, FEATURE_REPORTS_PRO):
        assert has_feature(feature, "enterprise") is True


def test_feature_status_values():
    assert get_feature_status(FEATURE_SCANNER_PRO) in {"stable", "beta", "alpha"}
    assert get_feature_status("no_such_feature") == "unknown"
