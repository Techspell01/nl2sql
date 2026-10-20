# Phase 1 review — Monday 5 October 2026

What a first review checks: the problem is real, the design is sound, and the work has started. You
have more than most: a working baseline with guardrails and a measured number. Present it as phase 1
of a plan, not as a finished product.

## The weekend

### Saturday evening (about 1 hour) — get it running on real data

- [x] Free Groq and Gemini keys in `.env` (done; both tested).
- [ ] Download Olist from Kaggle, unzip the CSVs into `data\raw\`.
- [ ] `python scripts\build_warehouse.py` — check the row counts look like ~99k orders, ~112k items.
- [ ] `python eval\run_eval.py --gold-only` — all 18 answerable gold queries must say `ok`.
- [ ] Double-click `start.bat` and ask two questions. If anything fails, stop and fix it tonight.
- [ ] Run `pytest`: all 40 tests must pass.

### Sunday morning (about 3 hours) — understand every file

You will be asked how it works. Read these in order and be able to explain each in two sentences:

- [ ] `nl2sql/pipeline.py` — the whole flow in 40 lines. Start here.
- [ ] `nl2sql/guard.py` — the five checks, and why parsing beats string matching.
- [ ] `nl2sql/catalog.py` and `warehouse/catalog.yml` — what the model is actually told.
- [ ] `warehouse/models/marts/fct_orders.sql` — how raw tables became the star schema.
- [ ] `nl2sql/evaluation.py` — the comparison rules in its docstring.
- [ ] Run `python eval\run_eval.py` once. Write down the accuracy and the per-band split. This is
      your baseline number. Look at every FAIL and understand why it failed.

### Sunday afternoon (about 3 hours) — slides

- [ ] Build the 12 slides below. Take screenshots from the app for slides 7 to 10.
- [ ] Record a 3-minute screen capture of the demo as a backup (Win + G opens the recorder).

### Sunday evening (about 1.5 hours) — rehearse

- [ ] Run the demo script twice, timed. It should take 5 minutes.
- [ ] Answer the likely questions below out loud, without notes.

### Monday morning

- [ ] 30 minutes before: start the app, ask one question so the first slow call is behind you.
- [ ] Have the backup recording open in another window.

## Slides (12)

1. **Title** — Argus: a guarded AI analyst for business data. Name, guide.
2. **Problem** — Business users wait on analysts for simple questions. Text-to-SQL tools exist, but
   they return confident wrong answers and can run unsafe queries.
3. **Objectives** — Answer questions over a real warehouse; never execute unvalidated SQL; refuse
   what the data cannot answer; measure accuracy honestly.
4. **Literature survey** — Spider (Yu et al., 2018) and BIRD (Li et al., 2023) as benchmarks;
   DIN-SQL (Pourreza and Rafiei, 2023) and DAIL-SQL (Gao et al., 2023) as prompting methods. Read
   each abstract before Monday; you will be asked what one of them did.
5. **Gap** — Benchmark papers measure accuracy; few treat validation and refusal as first-class.
   That is this project's angle.
6. **Dataset** — Olist: ~100k real orders, 9 linked tables. Show the star schema (5 marts).
7. **Architecture** — The diagram from the roadmap doc. Point at the guard.
8. **Phase 1: what is built** — The left column of the README's status table.
9. **Demo** (live, or the recording).
10. **Baseline result** — On the real data with Groq `gpt-oss-120b`: 20/20 answerable questions correct,
    2/2 unanswerable correctly refused, 100% valid SQL, ~1.3 s median. Then tell the story of how you
    got there, because it is the strongest evidence that the evaluation works:
    - q005 first failed on sample data: a three-way tie made "top 5" ambiguous. The bug was in the
      test set, so the question became "top 3".
    - The real data trails off to 16 and 4 orders in Sep and Oct 2018, so relative dates were
      anchored on August 2018. The first wording of that rule leaked: the model dropped 2016 from an
      unrelated question (run `prompt-v1-date-window-leak`, 94%). The full re-run caught it, and
      tightening the rule's scope fixed it (`prompt-v2`, 100%).
    - "Last month" was still ambiguous (July or August?), so it was defined explicitly, and two
      relative-date questions were added so a future change cannot break it silently.
    Say plainly that 100% on 22 seed questions means the set is still too easy. Growing it to 200
    harder questions is the plan, and the number will go down.
11. **Plan** — The 12-week roadmap image. Phase 2 = schema retrieval and few-shot examples.
12. **Tools** — Python, DuckDB, sqlglot, FastAPI, Gemini API (free tier, swappable for Groq or Claude),
    a hand-built web front end, pytest.

## Demo script (5 minutes)

1. **Sidebar** — "This is running on the real Olist data: 5 analytics tables, 2016 to 2018."
2. **Schema page** — "Before writing any SQL, the model reads exactly this: descriptions, live sample
   values, metric definitions, and a list of what the data does *not* contain."
3. **Ask:** *What were the top 5 product categories by revenue?* — open the SQL expander. "Revenue
   here uses our defined metric: it excludes freight and cancelled orders."
4. **Ask:** *What is the late delivery rate?* — "A metric name, answered with the canonical definition."
5. **Ask:** *What is the profit margin for each category?* — it refuses. "There is no cost data.
   A typical text-to-SQL demo would invent a column here. Ours says no."
6. **Guard lab** — run *Drop a table*, then *Read a file off the disk*. "Even if the model were
   tricked into writing this, it never reaches the database. And the connection itself is read-only."
7. **Evaluation page** — "On the real data, all 20 answerable questions pass. Here are the two earlier runs, and what each one taught us."

**If Groq is busy:** nothing to do. The question is retried on Gemini automatically and the card says so.
**If the internet fails:** the Schema, Guard lab and Evaluation pages still work offline. Say so calmly and
show the recording for steps 3 to 5.

## Questions the panel is likely to ask

| Question | Answer in brief |
| --- | --- |
| Why not just use ChatGPT? | It cannot see your schema or definitions, cannot run the query, and cannot be stopped from inventing columns. The value is in the catalog, the guard and the evaluation, not the model. |
| What is new here? Text-to-SQL exists. | Validation before execution and honest refusal, measured with an eval harness, on a modelled real-world warehouse. Most demos skip all three. |
| How do you know it is correct? | Execution accuracy on hand-written gold SQL: run both, compare results. Explain one comparison rule. |
| Why is the eval set only 22? | It is the seed. The plan grows it to 200 by week 8, across seven bands. |
| 100% sounds too good. | It is, for now: 22 seed questions are easy. The earlier runs show the harness does catch real failures; the 200-question set adds ambiguous and harder questions. |
| What if the model writes a harmful query? | Three layers: the guard rejects anything but one SELECT over known tables; the connection is read-only; external file access is disabled. Demo it. |
| Why DuckDB and not MySQL or Postgres? | Analytical columnar engine, zero setup. The SQL ports unchanged. |
| What is your ML contribution? | Retrieval over the catalog and example selection in phase 2, measured as an ablation: each change is one row with its accuracy gain. |
| What does it cost to run? | Nothing: it runs on Gemini's free tier, with Groq as a free fallback. About 3k prompt tokens per question; totals are on the Evaluation page. |
| Why not a local model? | The laptop's 4 GB GPU would make a capable model slow. The provider is one setting, so a local model is a later experiment, not a redesign. |

## Be honest about

- The 20-question number is a baseline on a seed set, not a final result.
- The model is a hosted API, not trained by you. Your contribution is the system around it and the
  measurement. Say that plainly; panels respect it.
