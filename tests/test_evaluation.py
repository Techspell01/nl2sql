import numpy as np
import pandas as pd

from nl2sql.evaluation import results_match


def df(**cols):
    return pd.DataFrame(cols)


def test_ignores_column_names():
    assert results_match(df(n=[5]), df(count_star=[5]))[0]


def test_ignores_column_order():
    assert results_match(df(total=[10, 20], state=["SP", "RJ"]), df(state=["SP", "RJ"], total=[10, 20]))[0]


def test_allows_extra_predicted_column_but_not_missing_one():
    assert results_match(df(state=["SP"], n=[3]), df(state=["SP"]))[0]
    assert not results_match(df(state=["SP"]), df(state=["SP"], n=[3]))[0]


def test_row_order_only_matters_when_ordered():
    pred, gold = df(s=["RJ", "SP"]), df(s=["SP", "RJ"])
    assert results_match(pred, gold, ordered=False)[0]
    assert not results_match(pred, gold, ordered=True)[0]


def test_rounds_floats_and_matches_int_to_float():
    assert results_match(df(x=[4.08641]), df(x=[4.0864]))[0]
    assert results_match(df(x=[3]), df(x=[3.0]))[0]
    assert not results_match(df(x=[0.09]), df(x=[9.0]))[0]  # fraction vs percentage is a real difference


def test_nulls_compare_equal():
    assert results_match(df(x=[None, 1.0]), df(x=[np.nan, 1.0]))[0]


def test_row_count_mismatch():
    ok, reason = results_match(df(x=[1, 2]), df(x=[1]))
    assert not ok and "row count" in reason


def test_rows_must_align_not_just_columns():
    pred = df(state=["SP", "RJ"], n=[1, 2])
    gold = df(state=["SP", "RJ"], n=[2, 1])
    assert not results_match(pred, gold)[0]
