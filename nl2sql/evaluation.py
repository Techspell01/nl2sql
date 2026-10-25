"""Execution-accuracy comparison: does the predicted query return the same answer as the gold query?

Rules, chosen deliberately and worth stating in the report:
- Values are compared, not column names. `count(*)` and `as n_orders` are the same answer.
- Column order does not matter. Each gold column is paired with a predicted column holding the same values;
  every valid pairing is tried, because two columns can hold the same set of values in different alignments.
- Extra predicted columns are allowed (a helpful count next to the asked-for name is not wrong).
  Missing columns are not.
- Row order matters only when the question asks for an ordering (`ordered: true`, e.g. "top 5").
  Give ordered gold queries a tie-breaker so the right answer is unambiguous.
- Floats are rounded to 2 decimals; NaN, NaT and NULL are all treated as missing.
"""

import itertools
import math
from collections import Counter
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd


def _norm(v):
    if v is None or v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating, Decimal)):
        f = float(v)
        return None if math.isnan(f) else round(f, 2) + 0.0  # + 0.0 folds -0.0 into 0.0
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    return str(v)


def _columns(df: pd.DataFrame) -> list[list]:
    return [[_norm(v) for v in df.iloc[:, i].tolist()] for i in range(df.shape[1])]


def _sort_key(values: list) -> list:
    return sorted(values, key=lambda x: (x is None, repr(x)))


def results_match(pred: pd.DataFrame, gold: pd.DataFrame, ordered: bool = False) -> tuple[bool, str]:
    if len(pred) != len(gold):
        return False, f"row count {len(pred)} != gold {len(gold)}"
    if len(gold) == 0:
        return True, "both empty"
    if pred.shape[1] < gold.shape[1]:
        return False, f"{pred.shape[1]} columns, gold needs {gold.shape[1]}"

    gold_cols, pred_cols = _columns(gold), _columns(pred)
    key = (lambda v: v) if ordered else _sort_key
    # every predicted column that could stand in for each gold column (identical values)
    options = [[j for j, p in enumerate(pred_cols) if key(p) == key(g)] for g in gold_cols]
    if any(not o for o in options):
        if ordered and all(any(_sort_key(p) == _sort_key(g) for p in pred_cols) for g in gold_cols):
            return False, "same values, different row order"
        return False, "no predicted column matches a gold column's values"

    gold_rows = [tuple(col[r] for col in gold_cols) for r in range(len(gold))]
    # try each way of pairing gold columns with distinct predicted columns: pairing by values alone is
    # ambiguous when two columns hold the same set of values in a different alignment
    for combo in itertools.product(*options):
        if len(set(combo)) < len(combo):
            continue
        pred_rows = [tuple(pred_cols[j][r] for j in combo) for r in range(len(pred))]
        if (pred_rows == gold_rows) if ordered else (Counter(pred_rows) == Counter(gold_rows)):
            return True, "match"
    return False, ("same values, different row order" if ordered else "columns match individually but rows differ")