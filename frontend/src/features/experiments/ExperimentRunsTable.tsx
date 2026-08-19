import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown, ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ExperimentRun } from "../../types/experiments";

interface ExperimentRunsTableProps {
  runs: ExperimentRun[];
  selectedRunIds: string[];
  onToggleRun: (runId: string) => void;
}

const percent = (value: number) => `${value.toFixed(1)}%`;

const forecastPath = (run: ExperimentRun) => {
  if (!run.forecastLink) return null;
  const query = new URLSearchParams({
    run: run.forecastLink.runId,
    entity: run.forecastLink.entityId,
    horizon: "all",
    model: run.forecastLink.modelId,
    exception: run.forecastLink.exceptionState,
  });
  return `/forecasts?${query}`;
};

export const ExperimentRunsTable = ({
  runs,
  selectedRunIds,
  onToggleRun,
}: ExperimentRunsTableProps) => {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "createdAt", desc: true },
  ]);

  const columns = useMemo<Array<ColumnDef<ExperimentRun>>>(
    () => [
      {
        id: "compare",
        header: "Compare",
        enableSorting: false,
        cell: ({ row }) => {
          const run = row.original;
          return (
            <input
              type="checkbox"
              aria-label={`Compare ${run.label}`}
              checked={selectedRunIds.includes(run.id)}
              disabled={!run.comparable}
              onChange={() => onToggleRun(run.id)}
            />
          );
        },
      },
      {
        accessorKey: "label",
        header: "Run",
        cell: ({ row }) => (
          <div className="model-cell">
            <span className="experiment-label">{row.original.label}</span>
            <span className="model-family">{row.original.id}</span>
          </div>
        ),
      },
      {
        accessorKey: "modelName",
        header: "Model",
        cell: ({ row }) => (
          <Link
            className="model-link"
            to={`/models/${row.original.modelId}?horizon=1&segment=demo_all`}
          >
            {row.original.modelName}
          </Link>
        ),
      },
      { accessorKey: "featureVersion", header: "Feature set" },
      {
        id: "horizons",
        accessorFn: (run) => run.horizons.length,
        header: "Horizons",
        cell: ({ row }) =>
          row.original.horizons.length > 0
            ? `1–${row.original.horizons.at(-1)?.horizon}`
            : "—",
      },
      {
        id: "wape",
        accessorFn: (run) => run.summary?.wape ?? Number.POSITIVE_INFINITY,
        header: "WAPE",
        cell: ({ row }) =>
          row.original.summary ? (
            <span className="numeric">
              {percent(row.original.summary.wape)}
            </span>
          ) : (
            "—"
          ),
      },
      {
        id: "delta",
        accessorFn: (run) =>
          run.statisticalEvidence?.deltaWapePp ?? Number.POSITIVE_INFINITY,
        header: "Δ WAPE",
        cell: ({ row }) => {
          const delta = row.original.statisticalEvidence?.deltaWapePp;
          if (delta === undefined) return "—";
          return (
            <span className={delta < 0 ? "positive" : "negative"}>
              {delta > 0 ? "+" : ""}
              {delta.toFixed(1)} pp
            </span>
          );
        },
      },
      {
        accessorKey: "runtimeMinutes",
        header: "Runtime",
        cell: ({ getValue }) => (
          <span className="numeric">{getValue<number>().toFixed(1)} min</span>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ getValue }) => {
          const status = getValue<ExperimentRun["status"]>();
          return (
            <span className={`experiment-status ${status}`}>{status}</span>
          );
        },
      },
      {
        accessorKey: "createdAt",
        header: "Created",
        cell: ({ getValue }) =>
          new Intl.DateTimeFormat("en", {
            month: "short",
            day: "numeric",
            year: "numeric",
          }).format(new Date(getValue<string>())),
      },
      {
        id: "forecast",
        header: "Forecast",
        enableSorting: false,
        cell: ({ row }) => {
          const path = forecastPath(row.original);
          return path ? (
            <Link className="inline-link" to={path}>
              Explore <ExternalLink size={12} aria-hidden="true" />
            </Link>
          ) : (
            <span className="model-family">Not published</span>
          );
        },
      },
    ],
    [onToggleRun, selectedRunIds],
  );

  const table = useReactTable({
    data: runs,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    enableSortingRemoval: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="table-scroll">
      <table className="data-table experiment-table">
        <caption className="visually-hidden">
          Experiment history with model, evidence, status, and creation date
        </caption>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const sorted = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={
                      sorted
                        ? sorted === "asc"
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                  >
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <button
                        className="sort-button"
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        {sorted === "asc" ? (
                          <ArrowUp size={12} aria-hidden="true" />
                        ) : sorted === "desc" ? (
                          <ArrowDown size={12} aria-hidden="true" />
                        ) : (
                          <ChevronsUpDown size={12} aria-hidden="true" />
                        )}
                      </button>
                    ) : (
                      flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
