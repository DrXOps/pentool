"""Test that PRO plan features return True (not broken by missing plan_order entry)."""
import pytest
from pentool.core.features import has_feature, get_limit


def test_pro_plan_has_payloads_pro():
    assert has_feature("payloads_pro", "pro") is True


def test_free_plan_no_payloads_pro():
    assert has_feature("payloads_pro", "free") is False


def test_pro_limit_threads():
    limit = get_limit("scanner_threads", "pro")
    assert limit > 5  # PRO должен иметь больше чем FREE


def test_plan_order_contains_pro():
    from pentool.core.features import has_feature
    # Косвенная проверка: если "pro" нет в plan_order — has_feature вернёт False
    # вместо True (ValueError в index()), что уже покрыто test_pro_plan_has_payloads_pro.
    # Здесь проверяем план_ордер напрямую.
    import pentool.core.features as feat_mod
    import inspect, ast, textwrap
    src = inspect.getsource(feat_mod.has_feature)
    # Проверяем что строка содержит "pro" в списке — через прямой импорт внутреннего
    # символа (plan_order определён локально внутри функции, поэтому читаем AST)
    tree = ast.parse(textwrap.dedent(src))
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            elts = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if "pro" in elts and "enterprise" in elts:
                found = True
    assert found, '"pro" and "enterprise" must be in plan_order inside has_feature()'


def test_enterprise_has_all_features():
    # enterprise должен иметь все фичи что есть у pro
    assert has_feature("payloads_pro", "enterprise") is True
