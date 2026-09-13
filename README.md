# 📊 Economic Pulse: An End-to-End ELT Pipeline Project

**Does consumer confidence lead the economy?**
This project tests whether how people feel about the economy actually predicts what it does next.

[![View Live Dashboard](https://img.shields.io/badge/→_View_Live_Dashboard-2E86AB?style=for-the-badge)](https://asjg20.github.io/economic-pulse/)

CLICK HERE TO VIEW DASHBOARD ! 

## Objective

In this project, I implemented an end-to-end ELT pipeline that consists of several stages:

1. Extracted Data from the FRED API and loaded them into a BigQuery warehouse.
2. Modeled and tested the data with dbt.
3. Tested the actual hypothesis with cross-correlation and Granger causality.
4. Orchestrated the whole chain on a monthly schedule with GitHub Actions, so it re-runs itself with no manual step.
5. Built a Claude API narrative step that translates the statistical result into a plain-language summary (Currently turned off)
6. Published the result as a live, self-updating dashboard on GitHub Pages.

## Table of Contents

- [Dataset Used](#dataset-used)
- [Stack](#stack)
- [Pipeline Architecture](#pipeline-architecture)
- [What It Found](#what-it-found)
- [Honest Notes](#honest-notes)
- [Design Decisions Worth Asking About](#design-decisions-worth-asking-about)

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

## Stack

- **Language:** Python, SQL
- **Extraction:** Python
- **Warehouse:** BigQuery
- **Transformation:** dbt
- **Analysis:** statsmodels, scipy
- **Orchestration:** GitHub Actions (monthly cron)
- **Narrative:** Claude API *(optional, disabled)*
- **Dashboard:** Plotly.js on GitHub Pages

## Pipeline Architecture

![Pipeline architecture diagram](assets/architecture.svg)

This is an **ELT** pattern, not ETL: raw data lands in the warehouse first, and transformation happens *inside* it with dbt — the pattern that's replaced transform-in-Python-before-load in most modern data stacks.

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
- **The AI narrative step is real but unrun.** [`ai/generate_narrative.py`](ai/generate_narrative.py) sends the 8 lag-analysis rows plus the latest reading per indicator to Claude for a plain-language summary. It's switched off because the Anthropic API's prepaid minimum isn't worth it for a once-a-month, ~700-token call on a project meant to cost nothing.
- **One CPI data point is a manual override, not an official figure.** BLS never published a standalone October 2025 CPI report during that year's government shutdown, so FRED returns `null` for that date and always will. `extract/fetch_fred.py` overrides it to 325.0 — a figure sourced from a Google search result, not verified against an official BLS release — so that month-over-month and year-over-year comparisons don't silently misalign around the gap. Every other data point in this project comes straight from FRED with no manual intervention.

## Design Decisions Worth Asking About

- **Granger causality over a bare correlation** — correlation alone can't separate "sentiment leads the economy" from "sentiment and the economy move together." The stronger claim is the defensible one, and it's what surfaced the disagreement above.
- **ELT with dbt over ETL-in-Python** — transformations are version-controlled SQL with tests attached, not buried in a script.
- **GitHub Actions instead of Airflow** — Airflow needs hosted infrastructure this project deliberately doesn't have. At one run a month, a scheduled workflow is genuinely the right tool.
- **Two dbt profiles** — CI reads its connection from environment variables via a profile under `.github/dbt/`, so the runner never needs the local machine's credential paths.
- **No dual-axis charts** — plotting sentiment and unemployment on two y-scales would let the chart imply an alignment that isn't in the data.
