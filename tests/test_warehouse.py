"""Checks that need a built warehouse. Skipped until scripts/build_warehouse.py has run."""

import pytest
import yaml

from nl2sql import config

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="warehouse not built")


@pytest.fixture(scope="module")
def catalog():
    from nl2sql.catalog import load_catalog
    return load_catalog()


def test_catalog_describes_every_column(catalog):
    assert catalog.drift == []


def test_every_gold_query_passes_guard_and_runs(catalog):
    from nl2sql.pipeline import execute_checked
    questions = yaml.safe_load((config.EVAL_DIR / "questions.yaml").read_text(encoding="utf-8"))
    for q in questions:
        if q["gold_sql"]:
            checked = execute_checked(q["gold_sql"], catalog)
            assert checked.error is None, f"{q['id']}: {checked.error}"


def test_warehouse_is_read_only():
    import duckdb
    from nl2sql.db import connect_readonly
    con = connect_readonly()
    with pytest.raises(duckdb.Error):
        con.execute("create table hack as select 1")
    con.close()
