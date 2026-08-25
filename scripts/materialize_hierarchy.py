"""Materialize a configured versioned hierarchy from canonical entity identity."""

from __future__ import annotations

import argparse
from pathlib import Path

from google.cloud import bigquery

from vertex.config.hierarchy import HierarchyConfig, load_hierarchy_config
from vertex.utils.bigquery_utils import validate_bq_table_id

DEFAULT_CONFIG = Path("vertex/config/hierarchy.yaml")


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _key_expression(column: str, key: str) -> str:
    return f"JSON_VALUE({column}, '$.{key}')"


def _json_key_expression(column: str, key: str) -> str:
    return f"JSON_QUERY({column}, '$.{key}')"


def _node_id_expression(level: dict[str, object], column: str) -> str:
    name = str(level["name"])
    keys = list(level["keys"])
    if not keys:
        return _literal(f"{name}:all")
    values = ", ".join(_key_expression(column, str(key)) for key in keys)
    return f"CONCAT({_literal(name + ':')}, ARRAY_TO_STRING([{values}], '|'))"


def _node_json_expression(level: dict[str, object], column: str) -> str:
    keys = list(level["keys"])
    if not keys:
        return "JSON '{}'"
    pairs = ", ".join(
        f"{_literal(str(key))}, {_json_key_expression(column, str(key))}" for key in keys
    )
    return f"JSON_OBJECT({pairs})"


def build_materialization_sql(config: HierarchyConfig, *, table_prefix: str) -> str:
    """Build idempotent BigQuery SQL from hierarchy levels and a canonical relation."""
    prefix = validate_bq_table_id(table_prefix)
    source = config.source
    source_table = validate_bq_table_id(f"{prefix}.{source['relation']}")
    identity_column = source["entity_key_json_column"]
    identity_rows = (
        f"SELECT DISTINCT {identity_column} FROM `{source_table}` "
        f"WHERE {identity_column} IS NOT NULL"
    )
    node_selects: list[str] = []
    for position, level in enumerate(config.levels):
        keys = list(level["keys"])
        key_filter = " AND ".join(
            f"{_key_expression(identity_column, str(key))} IS NOT NULL" for key in keys
        )
        select = f"""SELECT hierarchy_name, hierarchy_version,
          {_node_id_expression(level, identity_column)} AS node_id,
          {_literal(str(level['name']))} AS level_name, {position} AS level_position,
          {_node_json_expression(level, identity_column)} AS node_key_json
        FROM canonical_entities"""
        if key_filter:
            select += f" WHERE {key_filter}"
        node_selects.append(select)
    edge_selects = [f"""SELECT hierarchy_name, hierarchy_version,
          {_node_id_expression(parent, identity_column)} AS parent_node_id,
          {_node_id_expression(child, identity_column)} AS child_node_id
        FROM canonical_entities""" for parent, child in zip(config.levels, config.levels[1:])]
    return f"""
    DECLARE hierarchy_name STRING DEFAULT {_literal(config.name)};
    DECLARE hierarchy_version STRING DEFAULT {_literal(config.version)};

    CREATE TEMP TABLE canonical_entities AS
    {identity_rows};

    MERGE `{prefix}.forecast_hierarchy_nodes` AS target
    USING (
      SELECT * FROM ({' UNION ALL '.join(node_selects)})
      QUALIFY ROW_NUMBER() OVER (PARTITION BY node_id ORDER BY level_position) = 1
    ) AS source
    ON target.hierarchy_name = source.hierarchy_name
       AND target.hierarchy_version = source.hierarchy_version
       AND target.node_id = source.node_id
    WHEN NOT MATCHED THEN INSERT (
      hierarchy_name, hierarchy_version, node_id, level_name, level_position,
      node_key_json, effective_from, effective_to, created_at
    ) VALUES (
      source.hierarchy_name, source.hierarchy_version, source.node_id, source.level_name,
      source.level_position, source.node_key_json, DATE {_literal(source['effective_from'])},
      NULL, CURRENT_TIMESTAMP()
    );

    MERGE `{prefix}.forecast_hierarchy_edges` AS target
    USING (
      SELECT * FROM ({' UNION ALL '.join(edge_selects)})
      QUALIFY ROW_NUMBER() OVER (PARTITION BY parent_node_id, child_node_id) = 1
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
      source.child_node_id, NULL, {_literal(config.method)},
      DATE {_literal(source['effective_from'])}, NULL, CURRENT_TIMESTAMP()
    );
    """


def materialize_hierarchy(
    *, config_path: str | Path, table_prefix: str, project_id: str | None = None
) -> HierarchyConfig:
    """Execute hierarchy materialization and return the pinned config."""
    config = load_hierarchy_config(config_path)
    client = bigquery.Client(project=project_id)
    client.query(build_materialization_sql(config, table_prefix=table_prefix)).result()
    return config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--table-prefix", default="tds-favorita.favorita")
    parser.add_argument("--project-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_hierarchy_config(args.config)
    sql = build_materialization_sql(config, table_prefix=args.table_prefix)
    if args.dry_run:
        print(sql)
        return
    materialize_hierarchy(
        config_path=args.config,
        table_prefix=args.table_prefix,
        project_id=args.project_id,
    )
    print(f"Materialized hierarchy {config.name}/{config.version}")


if __name__ == "__main__":
    main()
