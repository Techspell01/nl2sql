"""HTTP API tests. The model is stubbed, so these run free and offline."""

import pytest
from fastapi.testclient import TestClient

from nl2sql import config, pipeline
from nl2sql.generator import Generation

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="warehouse not built")

STUB_SQL = {
    "revenue by category": "select p.category, sum(i.price) as revenue from fct_order_items i "
                           "join dim_products p using (product_id) group by 1 order by 2 desc limit 5",
    "orders per year": "select year(purchased_at) as year, count(*) as orders from fct_orders group by 1",
    "total orders": "select count(*) as orders from fct_orders",
    "try to drop": "drop table fct_orders",
    "bad column": "select profit from fct_orders",
}


def fake_generate(question, catalog_text, allow_fallback=True):
    if "margin" in question:
        return Generation(None, "There is no cost data.", "", "stub", "stub-model", 10, 5, 0.01)
    return Generation(STUB_SQL[question], None, "", "stub", "stub-model", 10, 5, 0.01)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(pipeline, "generate_sql", fake_generate)
    from nl2sql.api import app
    with TestClient(app) as c:
        yield c


def test_status_and_index(client):
    s = client.get("/api/status").json()
    assert s["tables"] == 5 and s["orders"] > 0 and s["provider"] in config.PROVIDERS
    assert "Argus" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_ask_answered_returns_typed_columns(client):
    r = client.post("/api/ask", json={"question": "revenue by category"}).json()
    assert r["stage"] == "answered"
    assert [c["kind"] for c in r["result"]["columns"]] == ["text", "number"]
    assert len(r["result"]["rows"]) == 5
    assert r["executed_sql"].rstrip().endswith("LIMIT 5")
    assert set(r["tables_used"]) == {"fct_order_items", "dim_products"}
    assert {"generate_s", "guard_ms", "execute_ms"} <= set(r["timings"])


def test_ask_single_value(client):
    r = client.post("/api/ask", json={"question": "total orders"}).json()
    assert r["stage"] == "answered" and r["result"]["row_count"] == 1


@pytest.mark.parametrize("question, stage", [
    ("try to drop", "blocked"),
    ("bad column", "blocked"),
    ("what is the profit margin", "cannot_answer"),
])
def test_ask_other_outcomes(client, question, stage):
    r = client.post("/api/ask", json={"question": question}).json()
    assert r["stage"] == stage
    assert r["result"] is None


def test_ask_validates_input(client):
    assert client.post("/api/ask", json={"question": ""}).status_code == 422


def test_guard_endpoint(client):
    blocked = client.post("/api/guard", json={"sql": "delete from fct_orders"}).json()
    assert blocked["allowed"] is False and "SELECT" in blocked["reason"]
    allowed = client.post("/api/guard", json={"sql": "select * from fct_order_items"}).json()
    assert allowed["allowed"] is True and allowed["executed_sql"].endswith(f"LIMIT {config.ROW_LIMIT}")


def test_schema_and_examples(client):
    sc = client.get("/api/schema").json()
    assert len(sc["tables"]) == 5 and "revenue" in sc["metrics"]
    ex = client.get("/api/examples").json()
    assert ex["questions"] and ex["guard_presets"]


def test_eval_run_path_cannot_escape_results_dir(client):
    assert client.get("/api/eval/runs/..%2F..%2Fquestions").status_code == 404
