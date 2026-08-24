select hierarchy_name, hierarchy_version, child_node_id
from {{ source('vertex_ml', 'forecast_hierarchy_edges') }}
where effective_to is null
group by hierarchy_name, hierarchy_version, child_node_id
having count(*) != 1
