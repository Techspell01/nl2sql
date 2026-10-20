"""Execution-accuracy comparison: does the predicted query return the same answer as the gold query?

Rules, chosen deliberately and worth stating in the report:
- Values are compared, not column names. `count(*)` and `as n_orders` are the same answer.
- Column order does not matter. Each gold column is matched to a predicted column with the same values.
- Extra predicted columns are allowed (a helpful count next to the asked-for name is not wrong).
  Missing columns are not.
- Row order matters only when the question asks for an ordering (`ordered: true`, e.g. "top 5").
- Floats are rounded to 2 decimals; NaN, NaT and NULL are all treated as missing.
"""

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
    mapping, used = [], set()
    for g in gold_cols:
        target = g if ordered else _sort_key(g)
        for j, p in enumerate(pred_cols):
            if j not in used and (p if ordered else _sort_key(p)) == target:
                mapping.append(j)
                used.add(j)
                break
        else:
            return False, "no predicted column matches a gold column's values"

    pred_rows = [tuple(pred_cols[j][r] for j in mapping) for r in range(len(pred))]
    gold_rows = [tuple(col[r] for col in gold_cols) for r in range(len(gold))]
    if ordered:
        return (pred_rows == gold_rows), ("match" if pred_rows == gold_rows else "same values, different row order")
    same = Counter(pred_rows) == Counter(gold_rows)
    return same, ("match" if same else "columns match individually but rows differ")
