"""Read-only access to the warehouse. Nothing in the app can open it for writing."""

import threading

import duckdb
import pandas as pd

from nl2sql import config


class QueryTimeout(Exception):
    pass


def connect_readonly() -> duckdb.DuckDBPyConnection:
    if not config.DB_PATH.exists():
        raise FileNotFoundError(
            f"No warehouse at {config.DB_PATH}. Run: python scripts/build_warehouse.py (or --sample)"
        )
    # read_only blocks writes; disabling external access blocks read_csv('C:/...'), httpfs and extensions
    return duckdb.connect(str(config.DB_PATH), read_only=True, config={"enable_external_access": False})


def run_query(sql: str, timeout_s: float = config.QUERY_TIMEOUT_S) -> pd.DataFrame:
    con = connect_readonly()
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        return con.execute(sql).fetchdf()
    except duckdb.InterruptException as e:
        raise QueryTimeout(f"Query exceeded {timeout_s:g}s and was stopped") from e
    finally:
        timer.cancel()
        con.close()
