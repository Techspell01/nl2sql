import pandas as pd

from nl2sql.evaluation import results_match

GOLD = pd.DataFrame({"state": ["SP", "RJ", "MG"], "orders": [30, 20, 10]})


def test_alias_and_column_order_do_not_matter():
    assert results_match(pd.DataFrame({"n": [10, 20, 30], "s": ["MG", "RJ", "SP"]}), GOLD)[0]


def test_extra_columns_are_allowed_but_missing_ones_are_not():
    assert results_match(pd.DataFrame({"state": ["SP", "RJ", "MG"], "orders": [30, 20, 10], "x": [1, 2, 3]}), GOLD)[0]
    assert not results_match(pd.DataFrame({"state": ["SP", "RJ", "MG"]}), GOLD)[0]


def test_wrong_value_fails():
    assert not results_match(pd.DataFrame({"state": ["SP", "RJ", "MG"], "orders": [30, 20, 11]}), GOLD)[0]


def test_swapped_columns_with_same_value_sets_still_match():
    gold = pd.DataFrame({"a": [1, 2, 3], "b": [3, 1, 2]})
    assert results_match(pd.DataFrame({"b": [3, 1, 2], "a": [1, 2, 3]}), gold)[0]


def test_wrong_pairing_fails():
    gold = pd.DataFrame({"a": [1, 2, 3], "b": [3, 1, 2]})
    assert not results_match(pd.DataFrame({"a": [1, 2, 3], "b": [1, 2, 3]}), gold)[0]


def test_ordered_mode_checks_row_order():
    right = pd.DataFrame({"s": ["SP", "RJ", "MG"], "n": [30, 20, 10]})
    wrong = pd.DataFrame({"s": ["MG", "RJ", "SP"], "n": [10, 20, 30]})
    assert results_match(right, GOLD, ordered=True)[0]
    ok, reason = results_match(wrong, GOLD, ordered=True)
    assert not ok and "row order" in reason