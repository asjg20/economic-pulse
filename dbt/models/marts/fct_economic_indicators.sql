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
),

lagged as (
    select
        *,
        lag(value, 1) over (w) as prior_value,
        lag(observation_date, 1) over (w) as prior_date,
        lag(value, 12) over (w) as year_ago_value,
        lag(observation_date, 12) over (w) as year_ago_date
    from indicator_names
    window w as (partition by series_id order by observation_date)
)

-- mom/yoy/rolling window sizes are periods, not calendar months: exact for the
-- monthly series (UMCSENT, UNRATE, CPIAUCSL, FEDFUNDS), but GDP is quarterly
-- and T10Y2Y is daily, so their "mom"/"yoy"/"12mo" columns cover different
-- calendar spans at each series' native cadence.
--
-- For the monthly series, "N rows back" is only correct if FRED published
-- every month in between. It doesn't always: e.g. FRED has no October 2025
-- CPIAUCSL reading (BLS didn't publish one during that year's government
-- shutdown). Without a check, a missing month would silently turn "12 rows
-- back" into 13 real months back and produce a plausible-looking but wrong
-- change. The date_diff guard below nulls the comparison out instead.
select
    observation_date as date,
    series_id,
    indicator_name,
    value,
    case
        when series_id in ('UMCSENT', 'UNRATE', 'CPIAUCSL', 'FEDFUNDS')
            and date_diff(observation_date, prior_date, month) != 1
            then null
        else value - prior_value
    end as value_mom_change,
    case
        when series_id in ('UMCSENT', 'UNRATE', 'CPIAUCSL', 'FEDFUNDS')
            and date_diff(observation_date, year_ago_date, month) != 12
            then null
        else value - year_ago_value
    end as value_yoy_change,
    avg(value) over (
        partition by series_id
        order by observation_date
        rows between 11 preceding and current row
    ) as rolling_12mo_avg
from lagged
