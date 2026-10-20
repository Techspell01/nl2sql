"""Validates generated SQL before it reaches the warehouse.

A query passes only if it is a single read-only SELECT over known tables and columns.
A LIMIT is added (or tightened) so no answer can return an unbounded result.
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

from nl2sql import config

DIALECT = "duckdb"

# Statement types that write, change schema, or reach outside the warehouse.
# getattr keeps this working across sqlglot versions that add or rename node types.
_FORBIDDEN = tuple(
    t for t in (getattr(exp, name, None) for name in (
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable", "TruncateTable",
        "Command", "Copy", "Attach", "Detach", "Use", "Set", "Pragma", "Transaction", "Commit", "Rollback",
        "LoadData", "Install", "Export",
    )) if t is not None
)


@dataclass
class GuardResult:
    ok: bool
    sql: str | None = None          # the query to execute, with LIMIT applied
    reason: str | None = None       # why it was rejected
    tables: list[str] = field(default_factory=list)


def _reject(reason: str) -> GuardResult:
    return GuardResult(ok=False, reason=reason)


def check(sql: str, schema: dict[str, dict[str, str]], row_limit: int = config.ROW_LIMIT) -> GuardResult:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        return _reject("Empty query.")

    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except ParseError as e:
        return _reject(f"Could not parse the SQL: {str(e).splitlines()[0]}")
    if len(statements) != 1:
        return _reject(f"Expected exactly one statement, found {len(statements)}.")
    stmt = statements[0]

    if not isinstance(stmt, exp.Query):
        return _reject(f"Only SELECT queries are allowed, not {stmt.key.upper()}.")
    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN):
            return _reject(f"Forbidden operation inside the query: {node.key.upper()}.")

    known = {t.lower() for t in schema}
    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    tables = set()
    for table in stmt.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            # a table function such as read_csv('...') or range(...)
            return _reject(f"Table functions are not allowed: {table.this.sql(DIALECT)}.")
        if table.db and table.db.lower() != "main":
            return _reject(f"Only the analytics tables are queryable, not {table.db}.{table.name}.")
        name = table.name.lower()
        if name in cte_names:
            continue
        if name not in known:
            return _reject(f"Unknown table: {table.name}. Available: {', '.join(sorted(known))}.")
        tables.add(name)

    try:
        qualify(stmt.copy(), schema=schema, dialect=DIALECT, validate_qualify_columns=True)
    except OptimizeError as e:
        message = str(e)
        if "could not be resolved" in message.lower() or "unknown" in message.lower():
            return _reject(f"Unknown column: {message}")
        # qualify cannot model every DuckDB construct; anything else is left to the database to judge

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
