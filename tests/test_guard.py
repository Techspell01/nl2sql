import pytest

from nl2sql.guard import check

SCHEMA = {
    "fct_orders": {"order_id": "VARCHAR", "customer_id": "VARCHAR", "order_status": "VARCHAR",
                   "purchased_at": "TIMESTAMP", "payment_value": "DOUBLE"},
    "dim_customers": {"customer_id": "VARCHAR", "state": "VARCHAR"},
}


@pytest.mark.parametrize("sql, fragment", [
    ("drop table fct_orders", "Only SELECT"),
    ("delete from fct_orders", "Only SELECT"),
    ("update fct_orders set order_status = 'x'", "Only SELECT"),
    ("insert into fct_orders values ('a')", "Only SELECT"),
    ("select 1; drop table fct_orders", "exactly one statement"),
    ("select * from users", "Unknown table"),
    ("select profit from fct_orders", "Unknown column"),
    ("select * from read_csv('C:/secrets.csv')", "Table functions"),
    ("select * from staging.stg_orders", "analytics tables"),
    ("", "Empty"),
    ("selec order_id frm fct_orders", "parse"),
])
def test_rejects(sql, fragment):
    result = check(sql, SCHEMA)
    assert not result.ok
    assert fragment.lower() in result.reason.lower()


@pytest.mark.parametrize("sql", [
    "select count(*) from fct_orders",
    "select c.state, sum(o.payment_value) from fct_orders o join dim_customers c using (customer_id) group by 1",
    "with t as (select order_id from fct_orders) select count(*) from t",
    "select order_id, row_number() over (partition by customer_id order by purchased_at) from fct_orders",
    "select state from dim_customers union select order_status from fct_orders",
])
def test_allows(sql):
    result = check(sql, SCHEMA)
    assert result.ok, result.reason


def test_adds_limit_when_missing():
    result = check("select order_id from fct_orders", SCHEMA, row_limit=50)
    assert result.sql.rstrip().endswith("LIMIT 50")


def test_tightens_large_limit_but_keeps_small_one():
    assert check("select order_id from fct_orders limit 99999", SCHEMA, row_limit=50).sql.endswith("LIMIT 50")
    assert check("select order_id from fct_orders limit 5", SCHEMA, row_limit=50).sql.endswith("LIMIT 5")


def test_reports_tables_used():
    result = check("select * from fct_orders join dim_customers using (customer_id)", SCHEMA)
    assert result.tables == ["dim_customers", "fct_orders"]
