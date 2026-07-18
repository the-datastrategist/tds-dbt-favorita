select *
from {{ ref('stg_forecast_outputs') }}
where target_date != date_add(date(forecast_origin), interval horizon day)
