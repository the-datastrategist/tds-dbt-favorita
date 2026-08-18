import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { LeaderboardRow } from "../../types/leaderboard";

interface LeaderboardTableProps {
  rows: LeaderboardRow[];
  horizon: number;
  segmentId: string;
}

const percent = (value: number) => `${value.toFixed(1)}%`;

export const LeaderboardTable = ({
  rows,
  horizon,
  segmentId,
}: LeaderboardTableProps) => {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "wape", desc: false },
  ]);
  const query = `?horizon=${horizon}&segment=${encodeURIComponent(segmentId)}`;

  const columns = useMemo<Array<ColumnDef<LeaderboardRow>>>(
    () => [
      {
        accessorKey: "rank",
        header: "Rank",
        cell: ({ row }) => row.original.rank ?? "—",
        sortingFn: "alphanumeric",
      },
      {
        accessorKey: "modelName",
        header: "Model",
        cell: ({ row }) => (
          <div className="model-cell">
            <Link
              className="model-link"
              to={`/models/${row.original.modelId}${query}`}
            >
              {row.original.modelName}
            </Link>
            <span className="model-family">{row.original.family}</span>
          </div>
        ),
      },
      {
        accessorKey: "lifecycleStatus",
        header: "Lifecycle",
        cell: ({ getValue }) => {
          const value = getValue<LeaderboardRow["lifecycleStatus"]>();
          return <span className={`status-badge ${value}`}>{value}</span>;
        },
      },
      {
        accessorKey: "wape",
        header: "WAPE",
        cell: ({ getValue }) => (
          <span className="numeric">{percent(getValue<number>())}</span>
        ),
      },
      {
        accessorKey: "bias",
        header: "Bias",
        cell: ({ getValue }) => (
          <span className="numeric">{percent(getValue<number>())}</span>
        ),
      },
      {
        accessorKey: "coverage",
        header: "Coverage",
        cell: ({ getValue }) => (
          <span className="numeric">{percent(getValue<number>() * 100)}</span>
        ),
      },
      {
        accessorKey: "baselineImprovement",
        header: "vs baseline",
        cell: ({ row }) =>
          row.original.evidenceStatus === "insufficient" ? (
            <span className="evidence-badge insufficient">
              Insufficient evidence
            </span>
          ) : (
            <span
              className={
                row.original.baselineImprovement >= 0 ? "positive" : "negative"
              }
            >
              {row.original.baselineImprovement > 0 ? "+" : ""}
              {percent(row.original.baselineImprovement)}
            </span>
          ),
      },
    ],
    [query],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="table-scroll">
      <table className="data-table">
        <caption className="visually-hidden">
          Model performance ranked for horizon {horizon}
        </caption>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
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
                        : "none"
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
