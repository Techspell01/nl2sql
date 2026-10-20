# Argus

*Named after the hundred-eyed guardian of Greek myth who never slept: it watches every query before it touches the data.*

A natural-language-to-SQL analytics assistant over the Olist Brazilian e-commerce dataset.
Ask a business question in English; the system writes a DuckDB query, **validates it before it
touches the data**, runs it read-only, and shows the answer as a chart, a figure or a table, with
the SQL alongside.

```
question -> SQL generation (LLM, reads the catalog) -> guard (sqlglot) -> read-only execution -> answer
                                                          |
                                     blocked: not a single SELECT, unknown table or column,
                                     table function, outside the analytics schema
```

## Status: phase 1

| Built | Planned (see the roadmap) |
| --- | --- |
| DuckDB warehouse: 8 staging models, 5-table star schema | Schema retrieval (top-k tables) |
| Catalog with column descriptions, live sample values, metric definitions | Similarity-selected few-shot examples |
| Generator with three swappable providers (Gemini, Groq, Claude) | Ambiguity gate that asks back |
| SQL guard: single SELECT, known tables and columns, LIMIT, no table functions | Self-repair loop on errors |
| Read-only, no-external-access connection with a query timeout | 200-question eval set; ablation table |
| Refusal for questions outside the schema | Logging, caching, deployment |
| Eval harness with execution-accuracy comparator; 22 seed questions | |
| FastAPI backend and a web app; 40 tests | |

## Setup (Windows, once)

```powershell
cd C:\Users\harin\finalproject\nl2sql
.venv\Scripts\activate
pip install -r requirements.txt      # already done
copy .env.example .env
```

**Two free API keys, in `.env` (never in `.env.example`, which is meant to be shared).**

- Groq, the primary: https://console.groq.com/keys -> `GROQ_API_KEY=...`
- Gemini, the automatic backup: https://aistudio.google.com/apikey -> `GEMINI_API_KEY=...`

Neither needs a card. With both set, a question that hits a busy or rate-limited Groq is retried on
Gemini automatically, and the answer card says so. Free-tier inputs may be used by the providers to
improve their products; that is fine here because Olist is public data.

**Data.** Download Olist from https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce (free
Kaggle account), unzip it, and put the CSV files directly in `data\raw\`.

## Run

Double-click **`start.bat`**. It builds the warehouse on first run, starts the server and opens
http://127.0.0.1:8000. Stop it with Ctrl+C in its window. Or by hand:

```powershell
python scripts\build_warehouse.py                  # builds data\warehouse.duckdb from data\raw\
uvicorn nl2sql.api:app --port 8000                 # then open http://127.0.0.1:8000
```

The app has four pages:

- **Ask**: type a question. Each answer shows the pipeline steps with their real timings, the
  result as a chart, headline figure or table, the exact SQL that ran, and a CSV download.
- **Guard lab**: try to sneak a harmful query past the guard. Works without an API key.
- **Schema**: everything the model is told about the data.
- **Evaluation**: accuracy by question type from saved eval runs. Works without an API key.

## Test

```powershell
pytest                                    # 40 tests; free, no API key, no internet
python eval\run_eval.py --gold-only       # every gold query runs and passes the guard; free
python eval\run_eval.py                   # the real evaluation: 22 model calls
```

`pytest` covers the guard, the result comparator, the warehouse, and every API endpoint (with the
model replaced by a stand-in, so nothing is spent). The full eval waits 8 seconds between questions
to stay inside free-tier rate limits, so it takes about three minutes. Each run is saved in
`eval\results\` and appears on the Evaluation page.

No data yet? `python scripts\make_sample_data.py` then `python scripts\build_warehouse.py --sample`
gives you an Olist-shaped warehouse of random numbers. The app shows a "Sample data" warning while
it is in use. Never report numbers from it.

## Free-tier limits

Groq's free `openai/gpt-oss-120b` allows 30 requests and 8,000 tokens per minute, 1,000 requests
and 200,000 tokens a day. A question uses about 1.5k tokens, so a full eval run uses about 30k.
Gemini's free limits are on the AI Studio dashboard. On 2026-10-04 `gemini-3.8-flash` returned
"high demand" errors on the free tier, so the backup uses `gemini-3.5-flash`.

The eval never falls back: one run measures exactly one model, and each record notes which one.

## Layout

```
start.bat                    one-click launcher
nl2sql/
  api.py                     FastAPI: /api/ask, /api/guard, /api/schema, /api/eval/*, serves web/
  catalog.py                 catalog.yml + live warehouse -> what the model reads
  generator.py               the model call (Gemini / Groq / Claude); returns SQL or CANNOT_ANSWER
  guard.py                   validates SQL before execution
  db.py                      read-only connection with a timeout
  pipeline.py                generate -> guard -> execute, with per-stage timings
  evaluation.py              execution-accuracy comparator (rules in its docstring)
  config.py                  providers and settings
web/                         the web app: index.html, styles.css, charts.js, app.js (no build step)
warehouse/
  models/staging/*.sql       raw CSV -> typed, renamed tables
  models/marts/*.sql         the star schema the assistant may query
  catalog.yml                descriptions and metric definitions
eval/
  questions.yaml             gold questions by band
  run_eval.py                runs them; writes eval/results/*.json
scripts/                     build_warehouse.py, make_sample_data.py
tests/                       pytest suite
docs/PHASE1_REVIEW.md        presentation plan and demo script
```

## Design decisions worth defending

- **Validate before executing.** The guard parses every query into a syntax tree; it never
  pattern-matches strings. The connection is also opened read-only with external access disabled,
  so a query that somehow passed the guard still could not write or read files.
- **Execution accuracy, not string match.** Two different queries that return the same answer are
  both right. The comparator's rules are in `nl2sql/evaluation.py`.
- **The model is swappable.** One prompt, three providers. Comparing them on the same eval set is
  a fair experiment, and a free one on Gemini and Groq.
- **The catalog is the feature.** Column descriptions, live sample values and metric definitions are
  what the model reads. Improving them is accuracy work, not documentation.
- **DuckDB, not Postgres, for now.** A single file with no server, so nothing can break on demo day.
  The SQL models are plain SELECTs and move to dbt and Postgres unchanged.
- **No front-end build step.** The web app is plain HTML, CSS and JavaScript with hand-drawn SVG
  charts, served by FastAPI. Nothing loads from the internet, so the interface works offline.
