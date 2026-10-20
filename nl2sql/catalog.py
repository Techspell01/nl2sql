"""Turns warehouse/catalog.yml plus the live warehouse into the schema text the model reads."""

from dataclasses import dataclass, field

import yaml

from nl2sql import config
from nl2sql.db import connect_readonly

MAX_SAMPLE_VALUES = 15


@dataclass
class Catalog:
    schema: dict[str, dict[str, str]]  # table -> column -> type, as sqlglot expects
    prompt_text: str
    data_start: str
    data_end: str
    drift: list[str] = field(default_factory=list)  # catalog.yml vs warehouse mismatches
    tables: list[dict] = field(default_factory=list)  # structured form of the same content, for the UI
    metrics: dict[str, str] = field(default_factory=dict)
    not_available: list[str] = field(default_factory=list)


def _column_spec(spec) -> tuple[str, bool]:
    if isinstance(spec, dict):
        return spec.get("description", ""), bool(spec.get("sample_values"))
    return spec, False


def _complete_months(con) -> tuple:
    """First and last day of the final unbroken run of months with real order volume.

    A month counts when it has at least 10% of the median monthly order count. Olist, for example,
    trails off to 16 and 4 orders in its last two months; anchoring "last month" there would mislead.
    """
    months = con.execute(
        "select date_trunc('month', order_date)::date as m, count(*) as n from fct_orders group by 1 order by 1"
    ).fetchall()
    counts = sorted(n for _, n in months)
    threshold = 0.1 * counts[len(counts) // 2]
    last = max(m for m, n in months if n >= threshold)
    first = last
    for m, n in reversed(months):
        if m > last:
            continue
        if n < threshold:
            break
        first = m
    end = con.execute("select (?::date + interval 1 month - interval 1 day)::date", [last]).fetchone()[0]
    return first, end


def load_catalog() -> Catalog:
    doc = yaml.safe_load(config.CATALOG_PATH.read_text(encoding="utf-8"))
    con = connect_readonly()
    try:
        rows = con.execute(
            "select table_name, column_name, data_type from information_schema.columns "
            "where table_schema = 'main' and table_name not like '\\_%' escape '\\' "
            "order by table_name, ordinal_position"
        ).fetchall()
        warehouse: dict[str, dict[str, str]] = {}
        for table, column, dtype in rows:
            warehouse.setdefault(table, {})[column] = dtype

        start, end = con.execute("select min(order_date), max(order_date) from fct_orders").fetchone()
        complete_start, complete_end = _complete_months(con)

        drift = []
        lines = [f"Data covers orders placed from {start} to {end}."]
        if (complete_start, complete_end) != (start, end):
            lines.append(
                f"Order volume is only reliable from {complete_start} to {complete_end}; months outside that range "
                "hold a handful of stray records.")
        month_name = complete_end.strftime("%B %Y")
        lines += [
            f"Relative dates: treat {complete_end} as today, with {month_name} complete. 'Last month' means "
            f"{month_name}, 'this year' means {complete_end.year}, 'last year' means {complete_end.year - 1}. "
            "Use this only to resolve relative dates: do not filter other questions to the reliable range "
            "unless the question asks for it.",
            "",
        ]
        schema: dict[str, dict[str, str]] = {}
        tables: list[dict] = []
        for table, tdoc in doc["tables"].items():
            if table not in warehouse:
                drift.append(f"table {table} is in catalog.yml but not in the warehouse")
                continue
            schema[table] = warehouse[table]
            row_count = con.execute(f"select count(*) from {table}").fetchone()[0]
            entry = {"name": table, "description": tdoc["description"], "rows": row_count, "columns": []}
            tables.append(entry)
            lines.append(f"TABLE {table} -- {tdoc['description']}")
            for column, spec in tdoc["columns"].items():
                if column not in warehouse[table]:
                    drift.append(f"column {table}.{column} is in catalog.yml but not in the warehouse")
                    continue
                description, wants_samples = _column_spec(spec)
                line = f"  {column} {warehouse[table][column]} -- {description}"
                samples = []
                if wants_samples:
                    values = con.execute(
                        f'select "{column}" from {table} where "{column}" is not null '
                        f'group by 1 order by count(*) desc limit {MAX_SAMPLE_VALUES}'
                    ).fetchall()
                    samples = [v[0] for v in values]
                    line += " Values: " + ", ".join(repr(v) for v in samples)
                lines.append(line)
                entry["columns"].append({"name": column, "type": warehouse[table][column],
                                         "description": description, "sample_values": samples})
            for column in warehouse[table]:
                if column not in tdoc["columns"]:
                    drift.append(f"column {table}.{column} has no description in catalog.yml")
            lines.append("")
    finally:
        con.close()

    lines.append("METRICS (use these exact definitions when a question names one)")
    lines += [f"  {name}: {definition}" for name, definition in doc.get("metrics", {}).items()]
    lines.append("")
    lines.append("NOT AVAILABLE in this warehouse")
    lines += [f"  - {item}" for item in doc.get("not_available", [])]

    return Catalog(schema=schema, prompt_text="\n".join(lines), data_start=str(start), data_end=str(end),
                   drift=drift, tables=tables, metrics=doc.get("metrics", {}),
                   not_available=doc.get("not_available", []))
