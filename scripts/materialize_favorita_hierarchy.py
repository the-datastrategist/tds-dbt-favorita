"""Materialize the versioned company-to-store hierarchy used by publication."""

from __future__ import annotations

import argparse

from google.cloud import bigquery

from vertex.utils.bigquery_utils import validate_bq_table_id


def materialize_hierarchy(*, table_prefix: str, project_id: str | None = None) -> None:
    prefix = validate_bq_table_id(table_prefix)
    client = bigquery.Client(project=project_id)
    query = f"""
    DECLARE hierarchy_name STRING DEFAULT 'favorita_demand';
    DECLARE hierarchy_version STRING DEFAULT 'v1';

    MERGE `{prefix}.forecast_hierarchy_nodes` AS target
    USING (
      SELECT hierarchy_name, hierarchy_version, 'company:all' AS node_id,
             'company' AS level_name, 0 AS level_position,
             JSON '{{}}' AS node_key_json
      UNION ALL
      SELECT hierarchy_name, hierarchy_version,
             FORMAT('store:%d', CAST(store_nbr AS INT64)), 'store', 1,
             TO_JSON(STRUCT(CAST(store_nbr AS INT64) AS store_id))
      FROM (SELECT DISTINCT store_nbr FROM `{prefix}.int_sales_store_daily`)
    ) AS source
    ON target.hierarchy_name = source.hierarchy_name
       AND target.hierarchy_version = source.hierarchy_version
       AND target.node_id = source.node_id
    WHEN NOT MATCHED THEN INSERT (
      hierarchy_name, hierarchy_version, node_id, level_name, level_position,
      node_key_json, effective_from, effective_to, created_at
    ) VALUES (
      source.hierarchy_name, source.hierarchy_version, source.node_id, source.level_name,
      source.level_position, source.node_key_json, DATE '2013-01-01', NULL, CURRENT_TIMESTAMP()
    );

    MERGE `{prefix}.forecast_hierarchy_edges` AS target
    USING (
      SELECT 'favorita_demand' AS hierarchy_name, 'v1' AS hierarchy_version,
             'company:all' AS parent_node_id,
             FORMAT('store:%d', CAST(store_nbr AS INT64)) AS child_node_id
      FROM (SELECT DISTINCT store_nbr FROM `{prefix}.int_sales_store_daily`)
    ) AS source
    ON target.hierarchy_name = source.hierarchy_name
       AND target.hierarchy_version = source.hierarchy_version
       AND target.parent_node_id = source.parent_node_id
       AND target.child_node_id = source.child_node_id
    WHEN NOT MATCHED THEN INSERT (
      hierarchy_name, hierarchy_version, parent_node_id, child_node_id,
      allocation_weight, weight_source, effective_from, effective_to, created_at
    ) VALUES (
      source.hierarchy_name, source.hierarchy_version, source.parent_node_id,
      source.child_node_id, NULL, 'bottom_up', DATE '2013-01-01', NULL, CURRENT_TIMESTAMP()
    );
    """
    client.query(query).result()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table-prefix", default="tds-favorita.favorita")
    parser.add_argument("--project-id")
    args = parser.parse_args()
    materialize_hierarchy(table_prefix=args.table_prefix, project_id=args.project_id)
    print("Materialized hierarchy favorita_demand/v1")


if __name__ == "__main__":
    main()
