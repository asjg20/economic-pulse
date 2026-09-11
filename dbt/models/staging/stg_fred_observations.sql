with source as (
    select * from {{ source('raw', 'raw_fred_observations') }}
),

renamed as (
    select
        series_id,
        date as observation_date,
        value,
        loaded_at
    from source
    where value is not null
),

deduped as (
    select
        series_id,
        observation_date,
        value,
        loaded_at,
        row_number() over (
            partition by series_id, observation_date
            order by loaded_at desc
        ) as rn
    from renamed
)

select
    series_id,
    observation_date,
    value,
    loaded_at
from deduped
where rn = 1
