"""Paths and settings. Everything tunable comes from environment variables or .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

RAW_DIR = ROOT / "data" / "raw"
SAMPLE_DIR = ROOT / "data" / "sample"
DB_PATH = Path(os.getenv("NL2SQL_DB_PATH", str(ROOT / "data" / "warehouse.duckdb")))
MODELS_DIR = ROOT / "warehouse" / "models"
CATALOG_PATH = ROOT / "warehouse" / "catalog.yml"
EVAL_DIR = ROOT / "eval"
WEB_DIR = ROOT / "web"

# Which model service writes the SQL. gemini and groq have free tiers; anthropic is paid.
PROVIDERS = {
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        # gemini-3.8-flash returned 503 "high demand" on the free tier on 2026-10-04; 3.5 answered
        "model": "gemini-3.5-flash",
        "effort": "medium",
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
        "effort": "medium",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "base_url": None,
        "key_env": "ANTHROPIC_API_KEY",
        "model": "claude-opus-5",
        "effort": "high",
    },
}

PROVIDER = os.getenv("NL2SQL_PROVIDER", "groq").strip().lower()
if PROVIDER not in PROVIDERS:
    raise ValueError(f"NL2SQL_PROVIDER must be one of {', '.join(PROVIDERS)}, not {PROVIDER!r}")
MODEL = os.getenv("NL2SQL_MODEL") or PROVIDERS[PROVIDER]["model"]
EFFORT = os.getenv("NL2SQL_EFFORT") or PROVIDERS[PROVIDER]["effort"]

# Second provider tried when the first is overloaded, rate-limited or unreachable. "none" disables it.
# The eval always disables it, so one run measures exactly one model.
_default_fallback = "gemini" if PROVIDER != "gemini" else "groq"
FALLBACK = os.getenv("NL2SQL_FALLBACK", _default_fallback).strip().lower()
if FALLBACK in ("", "none", PROVIDER) or FALLBACK not in PROVIDERS:
    FALLBACK = None

ROW_LIMIT = int(os.getenv("NL2SQL_ROW_LIMIT", "1000"))
QUERY_TIMEOUT_S = float(os.getenv("NL2SQL_QUERY_TIMEOUT_S", "10"))


def api_key(provider: str | None = None) -> str | None:
    return os.getenv(PROVIDERS[provider or PROVIDER]["key_env"]) or None


def fallback_ready() -> bool:
    return FALLBACK is not None and api_key(FALLBACK) is not None
