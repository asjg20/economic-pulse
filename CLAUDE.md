# Economic Pulse

@economic-pulse-project-spec.md

## Current Status

**Phase 1: Foundation** — complete. `extract/fetch_fred.py` pulls all six FRED series and loads them long-format into BigQuery `economic-pulse:raw.raw_fred_observations` (confirmed: 17,090 rows landed).

**Phase 2: Modeling** — complete. dbt project in `dbt/` with a `stg_fred_observations` staging view (typed, deduplicated) and a `fct_economic_indicators` mart (mom/yoy change, rolling 12-period avg) in the `staging`/`marts` BigQuery datasets. `dbt_utils` installed for `accepted_range` tests. Confirmed: `dbt run` builds both models, `dbt test` passes 10/10, `dbt source freshness` passes. Next up: Phase 3, `analyze/lead_lag_analysis.py` (cross-correlation + Granger causality).