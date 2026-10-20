"""HTTP API and web app server.  Run with:  uvicorn nl2sql.api:app --port 8000"""

import json
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nl2sql import config
from nl2sql.catalog import Catalog, load_catalog
from nl2sql.db import run_query
from nl2sql.pipeline import answer, execute_checked

EXAMPLES = [
    "What were the top 5 product categories by revenue?",
    "How many orders were placed in each month of 2017?",
    "What is the late delivery rate?",
    "Which 5 customer states have the slowest average delivery?",
    "What is the profit margin for each category?",
]

GUARD_PRESETS = [
    {"label": "A normal query", "kind": "safe",
     "sql": "select order_status, count(*) as orders\nfrom fct_orders\ngroup by order_status\norder by orders desc"},
    {"label": "Drop a table", "kind": "attack", "sql": "drop table fct_orders"},
    {"label": "Delete every order", "kind": "attack", "sql": "delete from fct_orders"},
    {"label": "Hide a second statement", "kind": "attack",
     "sql": "select count(*) from fct_orders; drop table fct_orders"},
    {"label": "Read a file off the disk", "kind": "attack", "sql": "select * from read_csv('C:/Windows/win.ini')"},
    {"label": "Invent a column", "kind": "attack", "sql": "select category, sum(profit) from dim_products group by 1"},
    {"label": "Reach the raw layer", "kind": "attack", "sql": "select * from raw.customers"},
    {"label": "Ask for everything", "kind": "safe", "sql": "select * from fct_order_items"},
]

_state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        _state["catalog"] = load_catalog()
    except FileNotFoundError as e:
        _state["startup_error"] = str(e)
    yield


app = FastAPI(title="Argus", lifespan=lifespan)


def catalog() -> Catalog:
    if "catalog" not in _state:
        raise HTTPException(503, _state.get("startup_error", "Warehouse not loaded"))
    return _state["catalog"]


def _kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    return "text"


def frame_to_json(df: pd.DataFrame | None) -> dict | None:
    if df is None:
        return None
    # to_json handles NaN -> null, numpy scalars and ISO dates in one pass
    split = json.loads(df.to_json(orient="split", date_format="iso", index=False))
    return {
        "columns": [{"name": str(c), "kind": _kind(df[c])} for c in df.columns],
        "rows": split["data"],
        "row_count": len(df),
        "truncated": len(df) >= config.ROW_LIMIT,
    }


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class GuardRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=5000)


@app.get("/api/status")
def status():
    cat = catalog()
    info = run_query("select source, built_at from _build_info").iloc[0]
    orders = next(t["rows"] for t in cat.tables if t["name"] == "fct_orders")
    provider = config.PROVIDERS[config.PROVIDER]
    return {
        "data_source": info["source"], "built_at": str(info["built_at"]),
        "data_start": cat.data_start, "data_end": cat.data_end,
        "orders": orders, "tables": len(cat.tables),
        "provider": config.PROVIDER, "provider_label": provider["label"], "model": config.MODEL,
        "key_configured": bool(config.api_key()), "key_env": provider["key_env"],
        "fallback": config.PROVIDERS[config.FALLBACK]["label"] if config.fallback_ready() else None,
        "row_limit": config.ROW_LIMIT, "catalog_drift": cat.drift,
    }


@app.get("/api/schema")
def schema():
    cat = catalog()
    return {"tables": cat.tables, "metrics": cat.metrics, "not_available": cat.not_available,
            "prompt_text": cat.prompt_text}


@app.get("/api/examples")
def examples():
    return {"questions": EXAMPLES, "guard_presets": GUARD_PRESETS}


@app.post("/api/ask")
def ask(req: AskRequest):
    result = answer(req.question.strip(), catalog())
    gen = result.generation
    return {
        "question": result.question,
        "stage": result.stage,
        "error": result.error,
        "generated_sql": gen.sql if gen else None,
        "executed_sql": result.guard.sql if result.guard and result.guard.ok else None,
        "tables_used": result.guard.tables if result.guard else [],
        "result": frame_to_json(result.df),
        "timings": result.timings,
        "tokens": {"input": gen.input_tokens, "output": gen.output_tokens} if gen else None,
        "model": gen.model if gen else config.MODEL,
        "provider": gen.provider if gen else config.PROVIDER,
        "fallback_from": config.PROVIDERS[gen.fallback_from]["label"] if gen and gen.fallback_from else None,
    }


@app.post("/api/guard")
def guard(req: GuardRequest):
    checked = execute_checked(req.sql, catalog())
    return {
        "allowed": checked.guard.ok,
        "reason": checked.guard.reason,
        "executed_sql": checked.guard.sql,
        "tables_used": checked.guard.tables,
        "error": checked.error if checked.guard.ok else None,
        "result": frame_to_json(checked.df),
        "timings": {"guard_ms": checked.guard_ms, "execute_ms": checked.execute_ms},
    }


@app.get("/api/eval/runs")
def eval_runs():
    runs = sorted((config.EVAL_DIR / "results").glob("*.json"), reverse=True)
    out = []
    for path in runs:
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append({"name": path.stem, "label": data.get("label"), "run_at": data.get("run_at"),
                    "provider": data.get("provider"), "model": data.get("model"),
                    "data_source": data.get("data_source"), "execution_accuracy": data.get("execution_accuracy")})
    return {"runs": out}


@app.get("/api/eval/runs/{name}")
def eval_run(name: str):
    path = (config.EVAL_DIR / "results" / f"{name}.json").resolve()
    if path.parent != (config.EVAL_DIR / "results").resolve() or not path.exists():
        raise HTTPException(404, "No such run")
    return json.loads(path.read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.WEB_DIR / "index.html")
