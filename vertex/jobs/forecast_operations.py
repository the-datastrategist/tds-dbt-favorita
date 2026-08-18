"""Operate immutable forecast drafts and publications from the command line."""

from __future__ import annotations

import argparse
import json

from google.cloud import bigquery

from vertex.utils.bigquery_utils import validate_bq_table_id
from vertex.utils.forecast_delivery import build_publication_event, persist_publication_event
from vertex.utils.forecast_operations import (
    build_manual_publication_records,
    build_override_record,
    build_revision_records,
    build_rollback_records,
    persist_operation_records,
)


def _query(project_id: str, sql: str, parameters: list[bigquery.ScalarQueryParameter]):
    client = bigquery.Client(project=project_id)
    return client.query(
        sql, job_config=bigquery.QueryJobConfig(query_parameters=parameters)
    ).to_dataframe()


def _table(prefix: str, name: str) -> str:
    return validate_bq_table_id(f"{prefix}.{name}")


def _emit_publication_event(
    args: argparse.Namespace,
    rows,
    *,
    event_type: str,
    prior_version: int | None = None,
) -> str:
    contract_names = set(rows["forecast_contract_name"])
    contract_hashes = set(rows["forecast_contract_hash"])
    if len(contract_names) != 1 or len(contract_hashes) != 1:
        raise ValueError("publication event requires one forecast contract and hash")
    event = build_publication_event(
        event_type=event_type,
        forecast_run_id=args.forecast_run_id,
        forecast_contract_name=str(next(iter(contract_names))),
        forecast_contract_hash=str(next(iter(contract_hashes))),
        publication_version=args.version,
        destination=args.destination,
        row_count=len(rows),
        actor=args.actor,
        idempotency_key=args.idempotency_key,
        prior_version=prior_version,
    )
    persist_publication_event(event, table_prefix=args.table_prefix, project_id=args.project_id)
    return str(event["publication_event_id"])


def run(args: argparse.Namespace) -> dict[str, object]:
    common = [bigquery.ScalarQueryParameter("forecast_run_id", "STRING", args.forecast_run_id)]
    outputs_table = _table(args.table_prefix, "forecast_outputs")
    rows = _query(
        args.project_id,
        f"SELECT * FROM `{outputs_table}` WHERE forecast_run_id = @forecast_run_id",
        common,
    )
    if rows.empty:
        raise ValueError("forecast run has no canonical output rows")

    if args.action == "override":
        selected = rows.loc[rows["forecast_output_id"] == args.forecast_output_id]
        if len(selected) != 1:
            raise ValueError("forecast_output_id must identify exactly one row in the run")
        record = build_override_record(
            selected.iloc[0].to_dict(),
            override_value=args.value,
            reason_code=args.reason_code,
            comment=args.comment,
            actor=args.actor,
            idempotency_key=args.idempotency_key,
        )
        override_table = _table(args.table_prefix, "forecast_overrides")
        existing_override = _query(
            args.project_id,
            f"SELECT * FROM `{override_table}` WHERE override_id = @override_id",
            [bigquery.ScalarQueryParameter("override_id", "STRING", record["override_id"])],
        )
        if not existing_override.empty:
            existing = existing_override.iloc[0]
            if (
                float(existing["override_value"]) != float(record["override_value"])
                or existing["reason_code"] != record["reason_code"]
                or existing["comment"] != record["comment"]
                or existing["overridden_by"] != record["overridden_by"]
            ):
                raise ValueError("override retry conflicts with the persisted logical record")
            return {"action": "override", "override_id": record["override_id"], "retry": True}
        persist_operation_records(
            table_prefix=args.table_prefix,
            project_id=args.project_id,
            overrides=[record],
        )
        return {"action": "override", "override_id": record["override_id"]}

    if args.action in {"approve-publish", "revise"}:
        override_table = _table(args.table_prefix, "forecast_overrides")
        overrides = _query(
            args.project_id,
            f"""
            SELECT * EXCEPT(row_number) FROM (
              SELECT *, ROW_NUMBER() OVER (
                PARTITION BY forecast_output_id ORDER BY overridden_at DESC, override_id DESC
              ) AS row_number
              FROM `{override_table}` WHERE forecast_run_id = @forecast_run_id
            ) WHERE row_number = 1
            """,
            common,
        )
        publication_table = _table(args.table_prefix, "forecast_publications")
        existing = _query(
            args.project_id,
            f"""
            SELECT publication_version, idempotency_key
            FROM `{publication_table}`
            WHERE forecast_run_id = @forecast_run_id AND destination = @destination
            """,
            common + [bigquery.ScalarQueryParameter("destination", "STRING", args.destination)],
        )
        same_version = existing.loc[existing["publication_version"] == args.version]
        if not same_version.empty and set(same_version["idempotency_key"]) != {
            args.idempotency_key
        }:
            raise ValueError("publication version already exists with a different idempotency key")
        if not same_version.empty:
            if len(same_version) != len(rows):
                raise ValueError("persisted publication retry is incomplete")
            publication_event_id = _emit_publication_event(
                args,
                rows,
                event_type=(
                    "forecast.revised" if args.action == "revise" else "forecast.published"
                ),
                prior_version=args.prior_version if args.action == "revise" else None,
            )
            return {
                "action": args.action,
                "publication_count": len(same_version),
                "publication_version": args.version,
                "publication_event_id": publication_event_id,
                "retry": True,
            }
        if (
            same_version.empty
            and not existing.empty
            and args.version <= int(existing["publication_version"].max())
        ):
            raise ValueError("publication_version must increase monotonically")
        approvals, publications = build_manual_publication_records(
            rows,
            overrides=overrides,
            actor=args.actor,
            destination=args.destination,
            idempotency_key=args.idempotency_key,
            publication_version=args.version,
            reason_code=args.reason_code,
            comment=args.comment,
        )
        revisions = None
        if args.action == "revise":
            prior = _query(
                args.project_id,
                f"""
                SELECT * FROM `{publication_table}`
                WHERE forecast_run_id = @forecast_run_id
                  AND publication_version = @prior_version
                  AND destination = @destination
                """,
                common
                + [
                    bigquery.ScalarQueryParameter("prior_version", "INT64", args.prior_version),
                    bigquery.ScalarQueryParameter("destination", "STRING", args.destination),
                ],
            )
            revisions = build_revision_records(
                prior,
                publications,
                actor=args.actor,
                idempotency_key=args.idempotency_key,
                reason_code=args.reason_code,
                comment=args.comment,
            )
        persist_operation_records(
            table_prefix=args.table_prefix,
            project_id=args.project_id,
            approvals=approvals,
            publications=publications,
            revisions=revisions,
        )
        publication_event_id = _emit_publication_event(
            args,
            rows,
            event_type=("forecast.revised" if args.action == "revise" else "forecast.published"),
            prior_version=args.prior_version if args.action == "revise" else None,
        )
        return {
            "action": args.action,
            "approval_count": len(approvals),
            "publication_count": len(publications),
            "override_count": len(overrides),
            "publication_version": args.version,
            "publication_event_id": publication_event_id,
            "revision_count": len(revisions or []),
        }

    publication_table = _table(args.table_prefix, "forecast_publications")
    all_publications = _query(
        args.project_id,
        f"""
        SELECT publication_version, idempotency_key FROM `{publication_table}`
        WHERE forecast_run_id = @forecast_run_id
        """,
        common,
    )
    existing_rollback = all_publications.loc[
        all_publications["publication_version"] == args.version
    ]
    if not existing_rollback.empty and set(existing_rollback["idempotency_key"]) != {
        args.idempotency_key
    }:
        raise ValueError("rollback version already exists with a different idempotency key")
    if not existing_rollback.empty:
        if len(existing_rollback) != len(rows):
            raise ValueError("persisted rollback retry is incomplete")
        publication_event_id = _emit_publication_event(
            args,
            rows,
            event_type="forecast.rolled_back",
            prior_version=args.prior_version,
        )
        return {
            "action": "rollback",
            "publication_count": len(existing_rollback),
            "publication_version": args.version,
            "publication_event_id": publication_event_id,
            "retry": True,
        }
    if (
        existing_rollback.empty
        and not all_publications.empty
        and args.version <= int(all_publications["publication_version"].max())
    ):
        raise ValueError("rollback version must exceed every existing publication version")
    parameters = common + [
        bigquery.ScalarQueryParameter("prior_version", "INT64", args.prior_version)
    ]
    prior = _query(
        args.project_id,
        f"""
        SELECT * FROM `{publication_table}`
        WHERE forecast_run_id = @forecast_run_id
          AND publication_version = @prior_version
        """,
        parameters,
    )
    if len(prior) != len(rows):
        raise ValueError("rollback source version must contain the complete forecast run")
    approvals, publications, revisions = build_rollback_records(
        prior,
        actor=args.actor,
        idempotency_key=args.idempotency_key,
        reason_code=args.reason_code,
        comment=args.comment,
        new_version=args.version,
    )
    persist_operation_records(
        table_prefix=args.table_prefix,
        project_id=args.project_id,
        approvals=approvals,
        publications=publications,
        revisions=revisions,
    )
    publication_event_id = _emit_publication_event(
        args,
        rows,
        event_type="forecast.rolled_back",
        prior_version=args.prior_version,
    )
    return {
        "action": "rollback",
        "prior_version": args.prior_version,
        "publication_version": args.version,
        "publication_event_id": publication_event_id,
        "revision_count": len(revisions),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("override", "approve-publish", "revise", "rollback"))
    parser.add_argument("--forecast-run-id", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason-code", required=True)
    parser.add_argument("--comment", required=True)
    parser.add_argument("--project-id", default="tds-favorita")
    parser.add_argument("--table-prefix", default="tds-favorita.favorita")
    parser.add_argument("--forecast-output-id")
    parser.add_argument("--value", type=float)
    parser.add_argument("--destination", default="canonical_bigquery")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--prior-version", type=int)
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if args.action == "override" and (not args.forecast_output_id or args.value is None):
        parser.error("override requires --forecast-output-id and --value")
    if args.action in {"revise", "rollback"} and args.prior_version is None:
        parser.error(f"{args.action} requires --prior-version")
    print(json.dumps(run(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
