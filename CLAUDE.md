# Economic Pulse

@economic-pulse-project-spec.md

## Current Status

**Phase 1: Foundation** — complete. `extract/fetch_fred.py` pulls all six FRED series and loads them long-format into BigQuery `economic-pulse:raw.raw_fred_observations` (confirmed: 17,090 rows landed).

**Phase 2: Modeling** — complete. dbt project in `dbt/` with a `stg_fred_observations` staging view (typed, deduplicated) and a `fct_economic_indicators` mart (mom/yoy change, rolling 12-period avg) in the `staging`/`marts` BigQuery datasets. `dbt_utils` installed for `accepted_range` tests. Confirmed: `dbt run` builds both models, `dbt test` passes 10/10, `dbt source freshness` passes.

**Phase 3: Analysis** — complete. `analyze/lead_lag_analysis.py` reads `UMCSENT`/`UNRATE`/`GDP` from `fct_economic_indicators`, aligns them to a monthly grid (GDP's quarterly reads are forward-filled to line up with the monthly lag tests — noted in-code as a simplification), and computes cross-correlation + Granger causality (`statsmodels`) at 1/3/6/12-month lags. Writes results to `economic-pulse:marts.fct_sentiment_lag_analysis`, declared as a dbt source in `dbt/models/marts/_sources.yml` with `not_null`/`accepted_values`/`accepted_range` tests and a freshness check. Confirmed: script runs end-to-end (8 rows written), `dbt build` passes 19/19 including the new tests and freshness.

Provisional result (not yet narrated/validated further): strongest UNRATE correlation at the 12-month lag (r ≈ -0.43, Granger p ≈ 0.054 — borderline); strongest GDP correlation at the 1-month lag (r ≈ -0.32, Granger p ≈ 0.61 — not significant), though GDP's 3-month lag is Granger-significant (p ≈ 0.0015) despite a slightly weaker correlation. Worth a closer look before writing the AI narrative in Phase 5. Next up: Phase 4, GitHub Actions orchestration (`.github/workflows/pipeline.yml`) wiring extract → dbt → analyze end to end, no AI step yet.