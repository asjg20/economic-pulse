"""Pull FRED series and load them as a long-format table into BigQuery `raw`."""

import os
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from fredapi import Fred
from google.cloud import bigquery

load_dotenv()

SERIES_IDS = ["UMCSENT", "UNRATE", "GDP", "CPIAUCSL", "FEDFUNDS", "T10Y2Y"]

TABLE_SCHEMA = [
    bigquery.SchemaField("series_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("value", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
]


def fetch_series(fred: Fred, series_id: str) -> pd.DataFrame:
    series = fred.get_series(series_id)
    loaded_at = datetime.now(timezone.utc)
    return pd.DataFrame(
        {
            "series_id": series_id,
            "date": series.index.date,
            "value": series.values,
            "loaded_at": loaded_at,
        }
    )


def fetch_all(fred: Fred) -> pd.DataFrame:
    frames = [fetch_series(fred, series_id) for series_id in SERIES_IDS]
    return pd.concat(frames, ignore_index=True)


def load_to_bigquery(df: pd.DataFrame, project_id: str, dataset: str) -> None:
    client = bigquery.Client(project=project_id)

    dataset_ref = bigquery.DatasetReference(project_id, dataset)
    client.create_dataset(dataset_ref, exists_ok=True)

    table_ref = dataset_ref.table("raw_fred_observations")
    job_config = bigquery.LoadJobConfig(
        schema=TABLE_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()

    table = client.get_table(table_ref)
    print(f"Loaded {table.num_rows} rows into {table.full_table_id}")


def main() -> None:
    fred_api_key = os.environ["FRED_API_KEY"]
    project_id = os.environ["GCP_PROJECT_ID"]
    dataset = os.environ.get("BQ_DATASET", "raw")

    fred = Fred(api_key=fred_api_key)
    df = fetch_all(fred)
    print(f"Fetched {len(df)} observations across {len(SERIES_IDS)} series")

    load_to_bigquery(df, project_id, dataset)


if __name__ == "__main__":
    main()
