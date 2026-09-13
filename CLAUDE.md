# Economic Pulse

@economic-pulse-project-spec.md

## Current Status

**Phase 1: Foundation** — complete. `extract/fetch_fred.py` pulls all six FRED series and loads them long-format into BigQuery `economic-pulse:raw.raw_fred_observations` (confirmed: 17,090 rows landed).

**Phase 2: Modeling** — complete. dbt project in `dbt/` with a `stg_fred_observations` staging view (typed, deduplicated) and a `fct_economic_indicators` mart (mom/yoy change, rolling 12-period avg) in the `staging`/`marts` BigQuery datasets. `dbt_utils` installed for `accepted_range` tests. Confirmed: `dbt run` builds both models, `dbt test` passes 10/10, `dbt source freshness` passes.

**Phase 3: Analysis** — complete. `analyze/lead_lag_analysis.py` reads `UMCSENT`/`UNRATE`/`GDP` from `fct_economic_indicators`, aligns them to a monthly grid (GDP's quarterly reads are forward-filled to line up with the monthly lag tests — noted in-code as a simplification), and computes cross-correlation + Granger causality (`statsmodels`) at 1/3/6/12-month lags. Writes results to `economic-pulse:marts.fct_sentiment_lag_analysis`, declared as a dbt source in `dbt/models/marts/_sources.yml` with `not_null`/`accepted_values`/`accepted_range` tests and a freshness check. Confirmed: script runs end-to-end (8 rows written), `dbt build` passes 19/19 including the new tests and freshness.

Provisional result (not yet narrated/validated further): strongest UNRATE correlation at the 12-month lag (r ≈ -0.43, Granger p ≈ 0.054 — borderline); strongest GDP correlation at the 1-month lag (r ≈ -0.32, Granger p ≈ 0.61 — not significant), though GDP's 3-month lag is Granger-significant (p ≈ 0.0015) despite a slightly weaker correlation. Worth a closer look before writing the AI narrative in Phase 5.

**Phase 4: Automation** — complete and verified on GitHub's runners. `.github/workflows/pipeline.yml` runs the whole chain on a monthly cron (13:00 UTC on the 10th, after UMCSENT/UNRATE publish) plus `workflow_dispatch`: extract → `dbt run` → test models → analyze → test lag results → `dbt source freshness` → export JSON → commit `docs/data/`. Tests are split around the analyze step deliberately, because the lag-analysis source can't be tested before the script writes it. CI gets its own dbt profile at `.github/dbt/profiles.yml` (env-var driven, selected via `DBT_PROFILES_DIR`) so `~/.dbt/profiles.yml` stays untouched for local runs. Also added `export/export_for_dashboard.py`, which writes `docs/data/indicators.json` (1990+, daily T10Y2Y thinned to month-end, ~502 KB) and `docs/data/lag_analysis.json`.

Confirmed: run [34738425932](https://github.com/asjg20/economic-pulse/actions/runs/34738425932) passed all 13 steps in 1m43s — extract 17,092 rows → 2 models → 10 tests → 8 lag rows → 7 tests → freshness → both JSON files → the runner committed `f283267` back to main on its own. Repo secrets `FRED_API_KEY` and `GCP_SERVICE_ACCOUNT` are set.

Worth remembering: the *first* CI run failed at `pip install`, and caught a real bug local dev had masked — `requirements.txt` pinned `python-dotenv==1.0.1` while `dbt-core` 1.12.4 requires `>=1.2`. The venv already had 1.2.3, so a clean resolve had never run locally. If a pin is ever edited by hand, check it with `pip install --dry-run --ignore-installed -r requirements.txt` rather than trusting that the venv works.

**Phase 5: AI layer** — built, but deliberately left switched off. `ai/generate_narrative.py` sends only the 8 lag-analysis rows plus the latest reading per indicator (~2,700 characters, no raw observations) to `claude-sonnet-5`, and gets back a `headline` + ~150-word `narrative` via a Pydantic structured output. Anti-hallucination is handled in the system prompt: every number must appear in the payload, no outside knowledge, no forecasting, an explicit p-value threshold, and a requirement to call out where correlation strength and Granger significance disagree. The payload carries `field_notes` defining each column so `strongest_lag_flag` can't be misread as "most significant," and `narrative.json` stores the exact inputs next to the output so any figure can be audited.

**Not enabled, by choice:** the Anthropic API needs a prepaid minimum (~$5) while this would use ~2¢/month, which isn't worth it for a project billed as zero-cost. The workflow step carries `if: env.ANTHROPIC_API_KEY != ''`, so it skips cleanly (grey, not red) until a secret exists — adding one turns the feature on with no code change. Everything up to the API boundary is verified; the call itself has never run.

Note: the spec's "zero-cost" claim and its Claude API layer are in tension. The README should either present the AI feature as optional, or drop the zero-cost framing.

Next up: Phase 6, the GitHub Pages dashboard (`docs/index.html`) — indicator charts plus a correlation-by-lag visual, with the narrative card rendering only when `narrative.json` is present.