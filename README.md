# 📊 Economic Pulse: An End-to-End ELT Pipeline Project

**Does consumer confidence lead the economy?** This project tests whether how people *feel* about the economy actually predicts what it does next — using Federal Reserve data, modeled in a cloud warehouse, tested with real statistics, and published as a dashboard that updates itself every month.

**[→ Live dashboard](https://asjg20.github.io/economic-pulse/)** — the plain-language version of the finding, written for a non-technical reader. This README is the technical write-up.

## Objective

Consumer sentiment surveys ask people how they feel about the economy — but does that feeling actually predict what they go on to do? Consumer spending is roughly 70% of U.S. GDP, so if sentiment reliably *leads* unemployment and GDP rather than just reacting to them, it's a genuinely useful early-warning signal: sentiment data comes out faster and cheaper than "hard" economic data.

This project answers that question end to end:
1. Extracted six economic indicators from the FRED API and loaded them into a BigQuery warehouse.
2. Modeled and tested the data with dbt (staging → marts).
3. Tested the actual hypothesis with cross-correlation and Granger causality (`statsmodels`) — not just charted, tested.
4. Orchestrated the whole chain on a monthly schedule with GitHub Actions, so it re-runs itself with no manual step.
5. Published the result as a live, self-updating dashboard on GitHub Pages.

It's also, underneath the economics, an attitude–behavior question: does a self-reported attitude actually predict downstream behavior? That's the same validity question I study in experimental psychology — I'm just asking it of macroeconomic data instead of a lab survey.

## Table of Contents

- [Dataset Used](#dataset-used)
- [Technologies](#technologies)
- [Pipeline Architecture](#pipeline-architecture)
- [Step 1: Extract](#step-1-extract)
- [Step 2: Transform](#step-2-transform)
- [Step 3: Analyze](#step-3-analyze)
- [Step 4: Orchestrate](#step-4-orchestrate)
- [Step 5: Narrate (optional, disabled)](#step-5-narrate-optional-disabled)
- [Step 6: Dashboard](#step-6-dashboard)
- [What It Found](#what-it-found)
- [Honest Notes](#honest-notes)
- [Design Decisions Worth Asking About](#design-decisions-worth-asking-about)
- [Running It Yourself](#running-it-yourself)

## Dataset Used

Six series from [FRED (Federal Reserve Economic Data)](https://fred.stlouisfed.org), free with an instant API key:

| Series | Role | Frequency |
|---|---|---|
| `UMCSENT` | Predictor — consumer sentiment | Monthly |
| `UNRATE` | Target — unemployment | Monthly |
| `GDP` | Target — growth | Quarterly |
| `CPIAUCSL` | Context — inflation | Monthly |
| `FEDFUNDS` | Context — policy rate | Monthly |
| `T10Y2Y` | Context — yield curve | Daily |

## Technologies

- **Language:** Python, SQL
- **Extraction:** Python + `fredapi`
- **Warehouse:** BigQuery (sandbox / free tier)
- **Transformation:** dbt-core + `dbt-bigquery`
- **Analysis:** `statsmodels`, `scipy`
- **Orchestration:** GitHub Actions (monthly cron)
- **Narrative** *(optional, disabled)*: Claude API
- **Dashboard:** Plotly.js on GitHub Pages

## Pipeline Architecture

```mermaid
flowchart LR
    A[FRED API] -->|extract/fetch_fred.py| B[(BigQuery: raw)]
    B -->|dbt staging model| C[(BigQuery: staging)]
    C -->|dbt mart + tests| D[(BigQuery: marts)]
    D -->|cross-correlation + Granger| X[analyze/lead_lag_analysis.py<br/>statsmodels]
    X --> D2[(fct_sentiment_lag_analysis)]
    D2 -.optional.-> E[ai/generate_narrative.py<br/>Claude API]
    D --> F[export/export_for_dashboard.py]
    D2 --> F
    E -.-> F
    F --> G[docs/data/*.json]
    G --> H[GitHub Pages dashboard]
    I[GitHub Actions<br/>monthly cron] -.orchestrates every step.-> A
```

This is an **ELT** pattern, not ETL: raw data lands in the warehouse first, and transformation happens *inside* it with dbt — the pattern that's replaced transform-in-Python-before-load in most modern data stacks.

## Step 1: Extract

[`extract/fetch_fred.py`](extract/fetch_fred.py) pulls all six series from the FRED API and loads them long-format into `raw.raw_fred_observations` in BigQuery — one row per `(series_id, date, value)`, exactly as the API returns it, no cleaning yet.

## Step 2: Transform

The dbt project in [`dbt/`](dbt/) does the cleaning, entirely in SQL, inside the warehouse:

- **`stg_fred_observations`** — a staging view that types and deduplicates the raw rows.
- **`fct_economic_indicators`** — a mart that adds month-over-month change, year-over-year change, and a 12-month rolling average per series.

Both are tested (`not_null`, `accepted_range` via `dbt_utils`, freshness) so a broken or stale run fails loudly instead of silently.

## Step 3: Analyze

This is the actual hypothesis test, implemented in [`analyze/lead_lag_analysis.py`](analyze/lead_lag_analysis.py) — deliberately its own Python stage rather than a dbt model, because cross-correlation and Granger causality aren't expressible in SQL.

**Alignment.** All three series are reindexed onto a common month-start grid. `UMCSENT` and `UNRATE` are natively monthly; `GDP` is quarterly and is forward-filled across each quarter's three months, so a lag expressed in months means the same thing for both targets.

**Cross-correlation.** For each target *y* and lag *k* ∈ {1, 3, 6, 12}, sentiment is shifted forward by *k* months and correlated against *y*:

```
r_k = corr( UMCSENT[t − k], y[t] )
```

A negative `r_k` means high sentiment *k* months ago is associated with a low value of the target now.

**Granger causality.** For the same target and lag, `statsmodels.tsa.stattools.grangercausalitytests` fits two nested models — *y* on its own lags, then *y* on its own lags plus sentiment's — and F-tests whether adding sentiment actually improves the forecast. Column order matters: the frame is passed as `[target, sentiment]`, so the test asks whether sentiment Granger-causes the target, not the reverse.

Results are written to `marts.fct_sentiment_lag_analysis` — a table dbt doesn't build but tracks as a **source**, tested and freshness-checked without owning it.

## Step 4: Orchestrate

One workflow, [`.github/workflows/pipeline.yml`](.github/workflows/pipeline.yml), runs the whole chain monthly at 13:00 UTC on the 10th — after that month's sentiment and jobs numbers are out — and on demand:

1. Extract all six series
2. `dbt run` — build staging + marts
3. Test everything that exists so far
4. Analyze — cross-correlation + Granger at 1/3/6/12-month lags
5. Test the lag-analysis table the previous step just wrote
6. `dbt source freshness`
7. Narrate *(skipped unless an API key is configured)*
8. Export the dashboard JSON
9. Commit the refreshed data back to this repo

Tests are deliberately split around step 4: several checks target a table that doesn't exist until the analysis script writes it, so testing everything up front would fail on a table that hasn't been created yet.

CI runs against its own dbt profile at [`.github/dbt/profiles.yml`](.github/dbt/profiles.yml), driven entirely by environment variables, so the runner never touches the local machine's credential paths.

## Step 5: Narrate (optional, disabled)

[`ai/generate_narrative.py`](ai/generate_narrative.py) is built but switched off. It would send only the 8 lag-analysis rows plus the latest reading per indicator (~2,700 characters, no raw observations) to Claude, and get back a headline + ~150-word narrative via a structured output. The system prompt constrains every stated number to that payload, forbids outside knowledge and forecasting, and requires flagging exactly the kind of correlation/significance disagreement this analysis found.

It's off because the Anthropic API bills against a prepaid minimum that a once-a-month, ~700-token call doesn't justify on a project meant to cost nothing. The workflow step self-skips (`if: env.ANTHROPIC_API_KEY != ''`) until a key exists — turning it on needs no code change.

## Step 6: Dashboard

[`export/export_for_dashboard.py`](export/export_for_dashboard.py) writes the marts and lag-analysis results out as static JSON, and `docs/index.html` — vanilla HTML/CSS/JS with Plotly.js, no build step — reads it at runtime.

**[→ asjg20.github.io/economic-pulse](https://asjg20.github.io/economic-pulse/)**

Design constraints followed deliberately: no dual-axis charts (sentiment and unemployment are separate panels sharing one timeline, never two y-scales on one plot); entity→color is stable page-wide; every charted value is also reachable without hovering.

## What It Found

Sentiment does carry real predictive information about unemployment — but not where you'd first look for it.

| | Strongest correlation | Granger-significant lags |
|---|---|---|
| **Unemployment** | 12 months (r = −0.43) | 1, 3, 6 months (3 of 4) |
| **GDP** | 1 month (r = −0.32) | 3, 6, 12 months (3 of 4) |

The two measures disagree, and that disagreement is the interesting result. For unemployment, the lag with the strongest raw correlation (12 months, r = −0.43) is the one lag that *fails* the significance test (p = 0.054), while the shorter leads that correlate less strongly all pass it. Correlation describes how similarly two series move; Granger causality asks whether knowing the past actually improves a forecast. Those are different questions, and here they give different answers — which is exactly why the project runs both instead of stopping at a correlation.

## Honest Notes

Things a careful reader should know before trusting the numbers:

- **GDP is quarterly, the analysis grid is monthly.** Each quarter's reading is forward-filled across its three months — a standard simplification, but a real one.
- **Granger causality runs on levels, not differenced series.** These series aren't stationary, which the test technically assumes. Differencing them would be more rigorous and would likely change the p-values.
- **Correlation is not causation, and Granger causality isn't either.** It's a claim about predictive information, not mechanism.
- **The dashboard charts start at 1990**, to keep the payload small. The statistics run on each series' complete history, back to the 1940s for some.
- **The AI narrative step is real but unrun** — see [Step 5](#step-5-narrate-optional-disabled).

## Design Decisions Worth Asking About

- **Granger causality over a bare correlation** — correlation alone can't separate "sentiment leads the economy" from "sentiment and the economy move together." The stronger claim is the defensible one, and it's what surfaced the disagreement above.
- **ELT with dbt over ETL-in-Python** — transformations are version-controlled SQL with tests attached, not buried in a script.
- **GitHub Actions instead of Airflow** — Airflow needs hosted infrastructure this project deliberately doesn't have. At one run a month, a scheduled workflow is genuinely the right tool.
- **Two dbt profiles** — CI reads its connection from environment variables via a profile under `.github/dbt/`, so the runner never needs the local machine's credential paths.
- **No dual-axis charts** — plotting sentiment and unemployment on two y-scales would let the chart imply an alignment that isn't in the data.

## Running It Yourself

```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # then fill in your values
```

You'll need a FRED API key and a GCP service account with BigQuery access. Then:

```bash
python extract/fetch_fred.py
cd dbt && dbt deps && dbt run && dbt test && cd ..
python analyze/lead_lag_analysis.py
python export/export_for_dashboard.py
```

To view the dashboard locally, serve `docs/` over HTTP (the page fetches JSON, which `file://` blocks):

```bash
cd docs && python -m http.server 8000
```
