import pytest

from nl2sql.guard import check

SCHEMA = {
    "fct_orders": {"order_id": "VARCHAR", "customer_id": "VARCHAR", "payment_value": "DOUBLE"},
    "dim_customers": {"customer_id": "VARCHAR", "state": "VARCHAR"},
}


def test_cte_name_cannot_hide_a_real_table():
    sql = "select s.order_id from (with stg_orders as (select 1 as x) select x from stg_orders) a, stg_orders s"
    result = check(sql, SCHEMA)
    assert not result.ok and "unknown table" in result.reason.lower()


@pytest.mark.parametrize("sql", [
    "select * into fct_orders from fct_orders",
    "select * into new_table from fct_orders",
    "select * from otherdb.main.fct_orders",
])
def test_into_and_catalog_prefix_rejected(sql):
    assert not check(sql, SCHEMA).ok


@pytest.mark.parametrize("sql", [
    "select 'abc from fct_orders",
    'select "abc from fct_orders',
    "select 1 /* oops",
    "select " + "(" * 3000 + "1" + ")" * 3000,
], ids=["open-string", "open-identifier", "open-comment", "deep-nesting"])
def test_malformed_input_is_rejected_not_raised(sql):
    assert not check(sql, SCHEMA).ok


def test_normal_cte_still_allowed():
    assert check("with t as (select order_id from fct_orders) select count(*) from t", SCHEMA).ok