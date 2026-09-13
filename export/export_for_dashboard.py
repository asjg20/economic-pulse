"""Export the marts tables to the JSON files the GitHub Pages dashboard reads."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

# Charts cover the modern era only; the lag analysis itself still runs on full history.
START_DATE = "1990-01-01"
# Series published more often than monthly, thinned to their last reading per month.
DAILY_SERIES = ("T10Y2Y",)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"


def fetch_indicators(client: bigquery.Client, project_id: str, dataset: str) -> pd.DataFrame:
    daily_list = ", ".join(f"'{s}'" for s in DAILY_SERIES)
    query = f"""
        select
            date,
            series_id,
            indicator_name,
            value,
            value_mom_change,
            value_yoy_change,
            rolling_12mo_avg
        from `{project_id}.{dataset}.fct_economic_indicators`
        where date >= '{START_DATE}'
        qualify series_id not in ({daily_list})
            or row_number() over (
                partition by series_id, date_trunc(date, month)
                order by date desc
            ) = 1
        order by series_id, date
    """
    return client.query(query).to_dataframe()


def fetch_lag_analysis(client: bigquery.Client, project_id: str, dataset: str) -> pd.DataFrame:
    query = f"""
        select
            target_indicator,
            lag_months,
            cross_correlation,
            granger_p_value,
            strongest_lag_flag,
            computed_at
        from `{project_id}.{dataset}.fct_sentiment_lag_analysis`
        order by target_indicator, lag_months
    """
    return client.query(query).to_dataframe()


def to_records(df: pd.DataFrame) -> list[dict]:
    # NaN is not valid JSON, so nulls have to survive as None rather than float('nan').
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


def build_indicators_payload(df: pd.DataFrame, generated_at: str) -> dict:
    df = df.copy()
    df["date"] = df["date"].astype(str)

    series = [
        {
            "series_id": series_id,
            "indicator_name": indicator_name,
            "observations": to_records(group.drop(columns=["series_id", "indicator_name"])),
        }
        for (series_id, indicator_name), group in df.groupby(
            ["series_id", "indicator_name"], sort=False
        )
    ]
    return {"generated_at": generated_at, "start_date": START_DATE, "series": series}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {path} ({path.stat().st_size / 1024:.0f} KB)")


def main() -> None:
    project_id = os.environ["GCP_PROJECT_ID"]
    dataset = os.environ.get("BQ_MARTS_DATASET", "marts")

    client = bigquery.Client(project=project_id)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    indicators = fetch_indicators(client, project_id, dataset)
    write_json(
        OUTPUT_DIR / "indicators.json",
        build_indicators_payload(indicators, generated_at),
    )

    lag_analysis = fetch_lag_analysis(client, project_id, dataset)
    write_json(
        OUTPUT_DIR / "lag_analysis.json",
        {"generated_at": generated_at, "results": to_records(lag_analysis)},
    )


if __name__ == "__main__":
    main()
