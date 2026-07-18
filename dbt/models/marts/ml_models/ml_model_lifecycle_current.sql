{{ config(materialized='view', tags=['vertex', 'backtest', 'lifecycle']) }}

with direct_events as (
    select
        candidate_id,
        lifecycle_event_id,
        event_type,
        to_state as lifecycle_state,
        reason,
        actor,
        occurred_at,
        1 as event_priority
    from {{ ref('stg_model_lifecycle_events') }}
),
replacement_events as (
    select
        replaces_candidate_id as candidate_id,
        lifecycle_event_id,
        'replaced' as event_type,
        'retired' as lifecycle_state,
        concat('Replaced by candidate ', candidate_id) as reason,
        actor,
        occurred_at,
        2 as event_priority
    from {{ ref('stg_model_lifecycle_events') }}
    where replaces_candidate_id is not null
        and to_state = 'champion'
),
ranked_events as (
    select
        *,
        row_number() over (
            partition by candidate_id
            order by occurred_at desc, event_priority desc, lifecycle_event_id desc
        ) as event_rank
    from (
        select * from direct_events
        union all
        select * from replacement_events
    )
)
select
    candidates.* except (initial_state),
    coalesce(events.lifecycle_state, candidates.initial_state) as lifecycle_state,
    events.lifecycle_event_id as latest_lifecycle_event_id,
    events.event_type as latest_event_type,
    events.reason as latest_event_reason,
    events.actor as latest_event_actor,
    events.occurred_at as latest_event_at
from {{ ref('stg_model_candidates') }} as candidates
left join ranked_events as events
    on candidates.candidate_id = events.candidate_id
    and events.event_rank = 1
