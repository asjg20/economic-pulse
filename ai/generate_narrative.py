"""Turn the lag-analysis results into a short plain-language narrative with Claude.

Only the summarized analysis output is sent to the model - never the underlying
observations - and the exact payload is saved alongside the narrative so every
number in the text can be checked against what the model was given.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from google.cloud import bigquery
from pydantic import BaseModel

load_dotenv()

MODEL = "claude-sonnet-5"
SIGNIFICANCE_THRESHOLD = 0.05
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "narrative.json"

FIELD_NOTES = {
    "cross_correlation": (
        "Pearson correlation between consumer sentiment shifted back by lag_months and the "
        "target's value at that later date. Negative means higher sentiment tends to precede "
        "a lower value of the target."
    ),
    "granger_p_value": (
        "p-value from a Granger causality test asking whether past sentiment improves a "
        "forecast of the target beyond what the target's own past already provides. Lower "
        "means stronger evidence."
    ),
    "strongest_lag_flag": (
        "marks the lag with the largest absolute cross-correlation for that target, which is "
        "not necessarily the lag with the strongest statistical significance."
    ),
}

SYSTEM_PROMPT = f"""You are writing the explanatory card for a public dashboard that tests whether U.S. consumer sentiment leads the real economy.

You will be given a DATA block containing the complete results of a lead-lag analysis - cross-correlation and Granger causality tests of consumer sentiment against unemployment and GDP at four lags - plus the latest reading of each indicator. That block is the only information you may use.

Rules:
- Every number you state must appear in the DATA block. Do not compute new figures, re-round them, or estimate.
- Use no outside knowledge about the economy, current events, or what these indicators have been doing lately.
- Do not forecast, and do not give investment or policy advice.
- A Granger p-value below {SIGNIFICANCE_THRESHOLD} counts as evidence that past sentiment improves the forecast; at or above {SIGNIFICANCE_THRESHOLD} the test does not support that claim. Say which applies.
- Correlation strength and Granger significance can disagree with each other. Where they do, say so plainly instead of smoothing it over.
- Write for someone who has never taken a statistics class. Any technical term gets a short plain-language gloss.
- Be honest when the evidence is weak or mixed - that is a useful finding, not a failure.

The narrative field should be roughly 150 words of flowing prose: no bullet points, no headings, no preamble. The headline field is one short sentence under 12 words stating the main finding."""


class Narrative(BaseModel):
    headline: str
    narrative: str


def fetch_lag_results(client: bigquery.Client, project_id: str, dataset: str) -> list[dict]:
    query = f"""
        select
            target_indicator,
            lag_months,
            round(cross_correlation, 3) as cross_correlation,
            round(granger_p_value, 4) as granger_p_value,
            strongest_lag_flag
        from `{project_id}.{dataset}.fct_sentiment_lag_analysis`
        order by target_indicator, lag_months
    """
    return client.query(query).to_dataframe().to_dict(orient="records")


def fetch_latest_readings(client: bigquery.Client, project_id: str, dataset: str) -> list[dict]:
    query = f"""
        select
            series_id,
            indicator_name,
            date,
            value,
            round(value_yoy_change, 2) as value_yoy_change
        from `{project_id}.{dataset}.fct_economic_indicators`
        qualify row_number() over (partition by series_id order by date desc) = 1
        order by series_id
    """
    df = client.query(query).to_dataframe()
    df["date"] = df["date"].astype(str)
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


def build_summary(lag_results: list[dict], latest_readings: list[dict]) -> dict:
    return {
        "question": (
            "Does U.S. consumer sentiment (UMCSENT) lead unemployment (UNRATE) and GDP, "
            "or does it only move alongside them?"
        ),
        "predictor": "UMCSENT - University of Michigan Consumer Sentiment index",
        "significance_threshold": SIGNIFICANCE_THRESHOLD,
        "field_notes": FIELD_NOTES,
        "lag_results": lag_results,
        "latest_readings": latest_readings,
    }


def generate_narrative(summary: dict) -> Narrative:
    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"DATA:\n{json.dumps(summary, indent=2)}",
            }
        ],
        output_format=Narrative,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to write the narrative: {response.stop_details}")
    return response.parsed_output


def main() -> None:
    project_id = os.environ["GCP_PROJECT_ID"]
    dataset = os.environ.get("BQ_MARTS_DATASET", "marts")

    bq = bigquery.Client(project=project_id)
    summary = build_summary(
        fetch_lag_results(bq, project_id, dataset),
        fetch_latest_readings(bq, project_id, dataset),
    )

    narrative = generate_narrative(summary)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "headline": narrative.headline,
        "narrative": narrative.narrative,
        "word_count": len(narrative.narrative.split()),
        # Saved so any figure in the narrative can be checked against what the model was sent.
        "inputs": summary,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"{narrative.headline}\n")
    print(narrative.narrative)
    print(f"\n({payload['word_count']} words) → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
