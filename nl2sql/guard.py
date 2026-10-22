"""Validates generated SQL before it reaches the warehouse: one read-only SELECT
over known tables and columns, with a LIMIT applied."""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, SqlglotError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from nl2sql import config

DIALECT = "duckdb"

_FORBIDDEN = tuple(
    t for t in (getattr(exp, name, None) for name in (
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable", "TruncateTable",
        "Command", "Copy", "Attach", "Detach", "Use", "Set", "Pragma", "Transaction", "Commit", "Rollback",
        "LoadData", "Install", "Export", "Into",
    )) if t is not None
)


@dataclass
class GuardResult:
    ok: bool
    sql: str | None = None
    reason: str | None = None
    tables: list[str] = field(default_factory=list)


def _reject(reason: str) -> GuardResult:
    return GuardResult(ok=False, reason=reason)


def _first_line(error: Exception) -> str:
    return (str(error).splitlines() or ["invalid SQL"])[0][:120]


def check(sql: str, schema: dict[str, dict[str, str]], row_limit: int = config.ROW_LIMIT) -> GuardResult:
    try:
        return _check(sql, schema, row_limit)
    except (SqlglotError, RecursionError) as e:
        return _reject(f"Could not validate the SQL: {_first_line(e)}")


def _check(sql: str, schema: dict[str, dict[str, str]], row_limit: int) -> GuardResult:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return _reject("Empty query.")

    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except (SqlglotError, RecursionError) as e:
        return _reject(f"Could not parse the SQL: {_first_line(e)}")
    if len(statements) != 1:
        return _reject(f"Expected exactly one statement, found {len(statements)}.")
    stmt = statements[0]

    if not isinstance(stmt, exp.Query):
        return _reject(f"Only SELECT queries are allowed, not {stmt.key.upper()}.")
    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN):
            return _reject(f"Forbidden operation inside the query: {node.key.upper()}.")

    known = {t.lower() for t in schema}
    tables = set()
    for scope in traverse_scope(stmt):
        for source in scope.sources.values():
            if not isinstance(source, exp.Table):
                continue  # a CTE or subquery, checked as its own scope
            if not isinstance(source.this, exp.Identifier):
                return _reject(f"Table functions are not allowed: {source.this.sql(DIALECT)}.")
            if source.catalog or (source.db and source.db.lower() != "main"):
                return _reject(f"Only the analytics tables are queryable, not {source.sql(DIALECT)}.")
            name = source.name.lower()
            if name not in known:
                return _reject(f"Unknown table: {source.name}. Available: {', '.join(sorted(known))}.")
            tables.add(name)

    try:
        qualify(stmt.copy(), schema=schema, dialect=DIALECT, validate_qualify_columns=True)
    except OptimizeError as e:
        message = str(e).lower()
        if "could not be resolved" in message or "unknown" in message:
            return _reject(f"Unknown column: {e}")

    limit = stmt.args.get("limit")
    current = None
    if isinstance(limit, exp.Limit):
        try:
            current = int(limit.expression.name)
        except (TypeError, ValueError):
            current = None
    if current is None or current > row_limit:
        stmt = stmt.limit(row_limit)

    return GuardResult(ok=True, sql=stmt.sql(dialect=DIALECT, pretty=True), tables=sorted(tables))