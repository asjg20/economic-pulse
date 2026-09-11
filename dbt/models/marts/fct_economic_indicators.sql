with stg as (
    select * from {{ ref('stg_fred_observations') }}
),

indicator_names as (
    select
        *,
        case series_id
            when 'UMCSENT' then 'Consumer Sentiment'
            when 'UNRATE' then 'Unemployment Rate'
            when 'GDP' then 'Gross Domestic Product'
            when 'CPIAUCSL' then 'Consumer Price Index'
            when 'FEDFUNDS' then 'Federal Funds Rate'
            when 'T10Y2Y' then '10Y-2Y Treasury Spread'
        end as indicator_name
    from stg
)

-- mom/yoy/rolling window sizes are periods, not calendar months: exact for the
-- monthly series (UMCSENT, UNRATE, CPIAUCSL, FEDFUNDS), but GDP is quarterly
-- and T10Y2Y is daily, so their "mom"/"yoy"/"12mo" columns cover different
-- calendar spans at each series' native cadence.
select
    observation_date as date,
    series_id,
    indicator_name,
    value,
    value - lag(value, 1) over (partition by series_id order by observation_date)
        as value_mom_change,
    value - lag(value, 12) over (partition by series_id order by observation_date)
        as value_yoy_change,
    avg(value) over (
        partition by series_id
        order by observation_date
        rows between 11 preceding and current row
    ) as rolling_12mo_avg
from indicator_names
