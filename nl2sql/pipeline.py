"""Question in, answer out: generate -> guard -> execute. Each stage reports how it ended and how long it took."""

import time
from dataclasses import dataclass, field

import pandas as pd

from nl2sql import config
from nl2sql.catalog import Catalog
from nl2sql.db import QueryTimeout, run_query
from nl2sql.generator import Generation, GenerationError, generate_sql
from nl2sql.guard import GuardResult, check


@dataclass
class Checked:
    guard: GuardResult
    df: pd.DataFrame | None
    error: str | None
    guard_ms: float
    execute_ms: float | None


@dataclass
class Answer:
    question: str
    stage: str                      # answered | cannot_answer | generation_error | blocked | db_error
    generation: Generation | None = None
    guard: GuardResult | None = None
    df: pd.DataFrame | None = None
    error: str | None = None
    timings: dict = field(default_factory=dict)  # generate_s, guard_ms, execute_ms


def execute_checked(sql: str, catalog: Catalog) -> Checked:
    """Guard then run a query. Shared by the assistant, the guard lab and the eval."""
    started = time.perf_counter()
    guard = check(sql, catalog.schema, config.ROW_LIMIT)
    guard_ms = (time.perf_counter() - started) * 1000
    if not guard.ok:
        return Checked(guard, None, guard.reason, guard_ms, None)
    started = time.perf_counter()
    try:
        df, error = run_query(guard.sql), None
    except QueryTimeout as e:
        df, error = None, str(e)
    except Exception as e:  # the database's own message is the useful thing to show
        df, error = None, f"{type(e).__name__}: {str(e).splitlines()[0]}"
    return Checked(guard, df, error, guard_ms, (time.perf_counter() - started) * 1000)


def answer(question: str, catalog: Catalog, allow_fallback: bool = True) -> Answer:
    result = Answer(question=question, stage="generation_error")
    try:
        result.generation = generate_sql(question, catalog.prompt_text, allow_fallback=allow_fallback)
    except GenerationError as e:
        result.error = str(e)
        return result

    gen = result.generation
    result.timings["generate_s"] = gen.latency_s
    if gen.cannot_answer:
        result.stage, result.error = "cannot_answer", gen.cannot_answer
        return result
    if not gen.sql:
        result.error = "The model did not return a SQL query."
        return result

    checked = execute_checked(gen.sql, catalog)
    result.guard, result.df, result.error = checked.guard, checked.df, checked.error
    result.timings.update(guard_ms=checked.guard_ms, execute_ms=checked.execute_ms)
    if not checked.guard.ok:
        result.stage = "blocked"
    elif checked.error:
        result.stage = "db_error"
    else:
        result.stage = "answered"
    return result
