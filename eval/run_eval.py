"""Run the evaluation set and report execution accuracy by band.

    python eval/run_eval.py --gold-only      # check every gold query runs (no API calls, free)
    python eval/run_eval.py                  # full run against the model
    python eval/run_eval.py --ids q001 q006  # a subset
"""

import argparse
import json
import statistics
import time
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nl2sql import config  # noqa: E402
from nl2sql.catalog import load_catalog  # noqa: E402
from nl2sql.db import run_query  # noqa: E402
from nl2sql.evaluation import results_match  # noqa: E402
from nl2sql.pipeline import answer, execute_checked  # noqa: E402

RESULTS_DIR = config.EVAL_DIR / "results"


def load_questions(ids: list[str] | None) -> list[dict]:
    questions = yaml.safe_load((config.EVAL_DIR / "questions.yaml").read_text(encoding="utf-8"))
    return [q for q in questions if not ids or q["id"] in ids]


def check_gold(questions: list[dict], catalog) -> int:
    failures = 0
    for q in questions:
        if q["gold_sql"] is None:
            print(f"  {q['id']}  {'(unanswerable)':>18}")
            continue
        checked = execute_checked(q["gold_sql"], catalog)
        if checked.error:
            failures += 1
            print(f"  {q['id']}  FAIL  {checked.error}")
        else:
            print(f"  {q['id']}  ok  {len(checked.df):>4} rows x {checked.df.shape[1]} cols")
    print(f"\n{len(questions) - failures}/{len(questions)} gold queries pass the guard and execute.")
    return failures


def run(questions: list[dict], catalog, pause_s: float) -> dict:
    records = []
    for i, q in enumerate(questions):
        if i and pause_s:
            time.sleep(pause_s)  # stay inside free-tier requests-per-minute and tokens-per-minute quotas
        result = answer(q["question"], catalog, allow_fallback=False)
        if result.stage == "generation_error" and "API key" in result.error:
            sys.exit(f"Stopping before saving a run: {result.error}")
        gen = result.generation
        record = {
            "id": q["id"], "band": q["band"], "question": q["question"], "stage": result.stage,
            "predicted_sql": gen.sql if gen else None, "error": result.error,
            "answered_by": f"{gen.provider}/{gen.model}" if gen else None,
            "latency_s": round(gen.latency_s, 2) if gen else None,
            "input_tokens": gen.input_tokens if gen else 0, "output_tokens": gen.output_tokens if gen else 0,
        }
        if q["gold_sql"] is None:
            record["correct"] = result.stage == "cannot_answer"
            record["reason"] = "correctly refused" if record["correct"] else f"expected refusal, got {result.stage}"
        elif result.stage != "answered":
            record["correct"], record["reason"] = False, f"{result.stage}: {result.error}"
        else:
            gold = execute_checked(q["gold_sql"], catalog)
            if gold.error:
                record["correct"], record["reason"] = False, f"gold query failed: {gold.error}"
            else:
                record["correct"], record["reason"] = results_match(result.df, gold.df, q.get("ordered", False))
        record["gold_sql"] = q["gold_sql"]
        records.append(record)
        mark = "PASS" if record["correct"] else "FAIL"
        print(f"  {q['id']}  {mark}  {q['band']:<14} {record['reason']}")
    return summarise(records)


def summarise(records: list[dict]) -> dict:
    by_band = defaultdict(list)
    for r in records:
        by_band[r["band"]].append(r["correct"])
    answerable = [r for r in records if r["band"] != "unanswerable"]
    latencies = [r["latency_s"] for r in records if r["latency_s"] is not None]
    return {
        "execution_accuracy": sum(r["correct"] for r in answerable) / max(len(answerable), 1),
        "valid_sql_rate": sum(r["stage"] == "answered" for r in answerable) / max(len(answerable), 1),
        "blocked_by_guard": sum(r["stage"] == "blocked" for r in records),
        "by_band": {band: {"correct": sum(v), "total": len(v)} for band, v in by_band.items()},
        "median_latency_s": statistics.median(latencies) if latencies else None,
        "total_input_tokens": sum(r["input_tokens"] for r in records),
        "total_output_tokens": sum(r["output_tokens"] for r in records),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gold-only", action="store_true", help="only check the gold SQL; no API calls")
    parser.add_argument("--ids", nargs="*", help="run only these question ids")
    parser.add_argument("--label", default="baseline", help="name for this run, e.g. the ablation row")
    parser.add_argument("--pause", type=float, default=None,
                        help="seconds between questions (default: 8 on free tiers, 0 on anthropic)")
    args = parser.parse_args()
    pause_s = args.pause if args.pause is not None else (0 if config.PROVIDER == "anthropic" else 8)

    catalog = load_catalog()
    questions = load_questions(args.ids)
    source = run_query("select source from _build_info").iloc[0, 0]
    if source == "sample":
        print("NOTE: warehouse was built from GENERATED sample data. Do not report these numbers.\n")

    if args.gold_only:
        sys.exit(1 if check_gold(questions, catalog) else 0)

    print(f"Running {len(questions)} questions against {config.PROVIDER}/{config.MODEL} "
          f"(effort {config.EFFORT}, {pause_s:g}s between questions)\n")
    summary = run(questions, catalog, pause_s)
    summary.update(label=args.label, provider=config.PROVIDER, model=config.MODEL, effort=config.EFFORT,
                   data_source=source,
                   run_at=datetime.now().isoformat(timespec="seconds"))

    print(f"\nExecution accuracy  {summary['execution_accuracy']:.0%}   (answerable questions)")
    print(f"Valid SQL rate      {summary['valid_sql_rate']:.0%}")
    print(f"Blocked by guard    {summary['blocked_by_guard']}")
    for band, s in summary["by_band"].items():
        print(f"  {band:<14} {s['correct']}/{s['total']}")
    if summary["median_latency_s"] is not None:
        print(f"Median latency      {summary['median_latency_s']:.1f}s")
    print(f"Tokens              {summary['total_input_tokens']:,} in / {summary['total_output_tokens']:,} out")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{args.label}.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved {out.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
