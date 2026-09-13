# Economic Pulse

**Does consumer confidence lead the economy?** An end-to-end analytics pipeline that tests whether how people *feel* about the economy actually predicts what it does next — using Federal Reserve data, modeled in a cloud warehouse, tested with real statistics, and published as a self-updating dashboard.

**[→ Live dashboard](https://asjg20.github.io/economic-pulse/)** — the plain-language version of the finding, written for a non-technical reader. This README is the technical write-up: method, architecture, and caveats.

---

## Why This Project

> Consumer sentiment surveys ask people how they *feel* about the economy — but does that feeling actually predict what they go on to do? Consumer spending makes up roughly 70% of U.S. GDP, so if sentiment reliably *leads* unemployment and GDP rather than just reacting to them, it's a genuinely useful early-warning signal — sentiment data comes out faster and cheaper than "hard" economic data. This project tests that question directly using Federal Reserve data and lead-lag statistical analysis (cross-correlation and Granger causality).
>
> It's also, underneath the economics, an attitude–behavior question: does a self-reported attitude actually predict downstream behavior? That's the same validity question I study in experimental psychology — I'm just asking it of macroeconomic data instead of a lab survey.

## What it found

Sentiment does carry real predictive information about unemployment — but not where you'd first look for it.

| | Strongest correlation | Granger-significant lags |
|---|---|---|
| **Unemployment** | 12 months (r = −0.43) | 1, 3, 6 months (3 of 4) |
| **GDP** | 1 month (r = −0.32) | 3, 6, 12 months (3 of 4) |

The two measures disagree, and that disagreement is the interesting result. For unemployment, the lag with the strongest raw correlation (12 months, r = −0.43) is the one lag that *fails* the significance test (p = 0.054), while the shorter leads that correlate less strongly all pass it. Correlation describes how similarly two series move; Granger causality asks whether knowing the past actually improves a forecast. Those are different questions, and here they give different answers — which is exactly why the project runs both instead of stopping at a correlation.

## Method

Implemented in [`analyze/lead_lag_analysis.py`](analyze/lead_lag_analysis.py).

**Alignment.** All three series are reindexed onto a common month-start grid spanning their full overlap. `UMCSENT` and `UNRATE` are natively monthly. `GDP` is quarterly and is forward-filled across the three months of each quarter, so a lag expressed in months is meaningful for both targets.

**Cross-correlation.** For each target *y* and each lag *k* ∈ {1, 3, 6, 12}, the sentiment series is shifted forward by *k* months and the Pearson correlation is taken over the pairs that survive:

```
r_k = corr( UMCSENT[t − k], y[t] )
```

A negative `r_k` means high sentiment *k* months ago is associated with a low value of the target now. `strongest_lag_flag` marks the lag with the largest |r| per target — a descriptive maximum, not a significance ranking, which is precisely where the two measures part company here.

**Granger causality.** For the same target and lag, `statsmodels.tsa.stattools.grangercausalitytests` fits two nested models — one regressing *y* on its own *k* lags, one adding *k* lags of sentiment — and reports an F-test on the added terms. The reported figure is the `ssr_ftest` p-value. Column order matters: the frame is passed as `[target, sentiment]`, which tests whether sentiment Granger-causes the target rather than the reverse. Each lag is tested individually (`maxlag=[k]`) rather than cumulatively.

**Interpretation.** Cross-correlation measures co-movement at a fixed offset. Granger causality asks a narrower question — whether past sentiment reduces forecast error for *y* beyond *y*'s own history. Neither establishes a causal mechanism; Granger causality is a statement about predictive information only. The two answers diverge in this data, and the divergence is reported rather than smoothed over.

**Sample.** Each test runs on the full overlapping history of the series involved — back to 1948 for `UNRATE`, 1947 for `GDP`, and 1952 (continuous from 1978) for `UMCSENT`. The dashboard's charts are windowed to 1990 onward for payload size; the statistics are not.

## Architecture

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

This is an **ELT** pattern: raw data lands in the warehouse first, and transformation happens inside it with dbt — rather than the older ETL-in-Python style most tutorials still teach.

The statistics live in their own Python stage rather than in dbt, because cross-correlation and Granger causality aren't expressible in SQL. That produces a table dbt didn't build, so dbt tracks it as a **source** and tests it without owning it.

## Data

Six series from [FRED](https://fred.stlouisfed.org), free with an instant API key:

| Series | Role | Frequency |
|---|---|---|
| `UMCSENT` | Predictor — consumer sentiment | Monthly |
| `UNRATE` | Target — unemployment | Monthly |
| `GDP` | Target — growth | Quarterly |
| `CPIAUCSL` | Context — inflation | Monthly |
| `FEDFUNDS` | Context — policy rate | Monthly |
| `T10Y2Y` | Context — yield curve | Daily |

## Stack

| Layer | Tool |
|---|---|
| Extraction | Python + `fredapi` |
| Warehouse | BigQuery (sandbox / free tier) |
| Transformation | dbt-core + `dbt-bigquery` |
| Analysis | `statsmodels`, `scipy` |
| Orchestration | GitHub Actions (monthly cron) |
| Narrative *(optional)* | Claude API |
| Dashboard | Plotly.js on GitHub Pages |

## The pipeline

One workflow, [`.github/workflows/pipeline.yml`](.github/workflows/pipeline.yml), runs monthly at 13:00 UTC on the 10th — after the month's sentiment and jobs numbers are out — and on demand:

1. **Extract** — pull all six series into `raw.raw_fred_observations`
2. **Transform** — `dbt run` builds the staging view and the indicator mart
3. **Test** — every model and source that exists at this point
4. **Analyze** — cross-correlation and Granger causality at 1/3/6/12-month lags
5. **Test again** — the lag-analysis table that step 4 just wrote
6. **Freshness** — fail loudly if any source has gone stale
7. **Narrate** *(skipped unless an API key is configured)*
8. **Export** — write the dashboard JSON
9. **Commit** — push the refreshed data back to this repo

The tests are deliberately split around step 4: seven of the seventeen checks target a table that doesn't exist until the analysis script writes it, so running them all up front would fail on a table that hasn't been created yet. Each table is tested as soon as it exists, and never before.

## Running it yourself

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

## Honest notes

Things a careful reader should know before trusting the numbers:

- **GDP is quarterly, the analysis grid is monthly.** Each quarter's GDP reading is forward-filled across its three months. This treats GDP as known slightly earlier than it is published in reality, which is a standard simplification but a real one.
- **Granger causality runs on levels, not differenced series.** These series are not stationary, which the test technically assumes. Differencing them would be the more rigorous treatment and would likely change the p-values.
- **Correlation here is not causation, and Granger causality isn't either.** It measures whether past values improve a forecast — a claim about predictive information, not mechanism.
- **The AI narrative step is built but switched off.** The Anthropic API bills against a prepaid minimum that a once-a-month, ~700-token call doesn't justify on a project meant to cost nothing. The workflow step self-skips until an `ANTHROPIC_API_KEY` secret exists; adding one enables it with no code change. The design is the point: only the summarized results are sent — never raw observations — the prompt constrains every stated number to that payload, and `narrative.json` stores the exact inputs next to the output so any figure can be audited.
- **The dashboard charts start at 1990**, to keep the payload small. The statistics run on each series' complete history, back to the 1940s for some.

## Design decisions worth asking about

- **Granger causality over a bare correlation** — correlation alone can't separate "sentiment leads the economy" from "sentiment and the economy move together." The stronger claim is the defensible one, and it's what surfaced the disagreement described above.
- **ELT with dbt over ETL-in-Python** — transformations are version-controlled SQL with tests attached, not buried in a script.
- **GitHub Actions instead of Airflow** — Airflow needs hosted infrastructure this project deliberately doesn't have. At one run a month, a scheduled workflow is genuinely the right tool, and naming that tradeoff beats overselling a stack I'm not running.
- **Two dbt profiles** — CI reads its connection from environment variables via a profile under `.github/dbt/`, so the runner never needs the local machine's credential paths.
- **No dual-axis charts** — plotting sentiment and unemployment on two y-scales would let the chart imply an alignment that isn't in the data. They're separate panels sharing one timeline instead.
