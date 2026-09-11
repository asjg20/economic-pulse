"""Cross-correlation and Granger causality of consumer sentiment vs. UNRATE/GDP.

Reads `marts.fct_economic_indicators`, tests whether UMCSENT leads each target
at lags of 1/3/6/12 months, and writes the results to
`marts.fct_sentiment_lag_analysis`.
"""

import os
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery
from statsmodels.tsa.stattools import grangercausalitytests

load_dotenv()

PREDICTOR = "UMCSENT"
TARGETS = ["UNRATE", "GDP"]
LAG_MONTHS = [1, 3, 6, 12]

RESULT_SCHEMA = [
    bigquery.SchemaField("target_indicator", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("lag_months", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("cross_correlation", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("granger_p_value", "FLOAT64", mode="NULLABLE"),
    bigquery.SchemaField("strongest_lag_flag", "BOOL", mode="REQUIRED"),
    bigquery.SchemaField("computed_at", "TIMESTAMP", mode="REQUIRED"),
]


def load_indicators(client: bigquery.Client, project_id: str, marts_dataset: str) -> pd.DataFrame:
    series_list = ", ".join(f"'{s}'" for s in [PREDICTOR, *TARGETS])
    query = f"""
        select date, series_id, value
        from `{project_id}.{marts_dataset}.fct_economic_indicators`
        where series_id in ({series_list})
        order by series_id, date
    """
    df = client.query(query).to_dataframe()
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_monthly_frame(df: pd.DataFrame) -> pd.DataFrame:
    wide = df.pivot(index="date", columns="series_id", values="value").sort_index()
    monthly_index = pd.date_range(wide.index.min(), wide.index.max(), freq="MS")
    wide = wide.reindex(monthly_index)
    # GDP is quarterly; forward-fill each quarter's reading across its months so it
    # lines up with the monthly grid used to test lags against UMCSENT/UNRATE.
    if "GDP" in wide.columns:
        wide["GDP"] = wide["GDP"].ffill()
    return wide


def cross_correlation(sentiment: pd.Series, target: pd.Series, lag: int):
    aligned = pd.concat([sentiment.shift(lag), target], axis=1).dropna()
    if len(aligned) < 3:
        return None
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def granger_p_value(sentiment: pd.Series, target: pd.Series, lag: int):
    # Column order matters: grangercausalitytests checks whether column 2
    # (sentiment) helps predict column 1 (target).
    aligned = pd.concat([target, sentiment], axis=1).dropna()
    if len(aligned) < lag * 3:
        return None
    result = grangercausalitytests(aligned.to_numpy(), maxlag=[lag])
    return float(result[lag][0]["ssr_ftest"][1])


def run_analysis(wide: pd.DataFrame) -> pd.DataFrame:
    sentiment = wide[PREDICTOR]
    rows = []
    for target_name in TARGETS:
        target = wide[target_name]
        target_rows = [
            {
                "target_indicator": target_name,
                "lag_months": lag,
                "cross_correlation": cross_correlation(sentiment, target, lag),
                "granger_p_value": granger_p_value(sentiment, target, lag),
            }
            for lag in LAG_MONTHS
        ]
        strongest_idx = max(
            range(len(target_rows)),
            key=lambda i: abs(target_rows[i]["cross_correlation"] or 0),
        )
        for i, row in enumerate(target_rows):
            row["strongest_lag_flag"] = i == strongest_idx
        rows.extend(target_rows)

    computed_at = datetime.now(timezone.utc)
    for row in rows:
        row["computed_at"] = computed_at
    return pd.DataFrame(rows)


def write_to_bigquery(client: bigquery.Client, df: pd.DataFrame, project_id: str, dataset: str) -> None:
    dataset_ref = bigquery.DatasetReference(project_id, dataset)
    client.create_dataset(dataset_ref, exists_ok=True)

    table_ref = dataset_ref.table("fct_sentiment_lag_analysis")
    job_config = bigquery.LoadJobConfig(
        schema=RESULT_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()

    table = client.get_table(table_ref)
    print(f"Loaded {table.num_rows} rows into {table.full_table_id}")


def main() -> None:
    project_id = os.environ["GCP_PROJECT_ID"]
    marts_dataset = os.environ.get("BQ_MARTS_DATASET", "marts")

    client = bigquery.Client(project=project_id)
    raw = load_indicators(client, project_id, marts_dataset)
    wide = build_monthly_frame(raw)

    results = run_analysis(wide)
    print(results.to_string(index=False))

    write_to_bigquery(client, results, project_id, marts_dataset)


if __name__ == "__main__":
    main()
