import { BarChart } from "echarts/charts";
import {
  AriaComponent,
  GridComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactEChartsCore from "echarts-for-react/esm/core";
import type { LeaderboardRow } from "../../types/leaderboard";

echarts.use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  GridComponent,
  TooltipComponent,
]);

interface LeaderboardChartProps {
  rows: LeaderboardRow[];
}

export const LeaderboardChart = ({ rows }: LeaderboardChartProps) => {
  const chartRows = rows.filter(
    ({ evidenceStatus }) => evidenceStatus === "sufficient",
  );
  const best = chartRows[0];
  const summary = best
    ? `${best.modelName} has the lowest WAPE at ${best.wape.toFixed(1)} percent.`
    : "No models have sufficient evidence for comparison.";

  const option = {
    animationDuration: 250,
    aria: {
      enabled: true,
      description: summary,
    },
    grid: { left: 18, right: 22, top: 16, bottom: 28, containLabel: true },
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: number) => `${value.toFixed(1)}% WAPE`,
    },
    xAxis: {
      type: "value",
      name: "WAPE (%)",
      nameLocation: "middle",
      nameGap: 24,
      axisLabel: { color: "#5F625C" },
      splitLine: { lineStyle: { color: "#EDEDED" } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: chartRows.map(({ modelName }) => modelName),
      axisLabel: { color: "#20211F", width: 112, overflow: "truncate" },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    series: [
      {
        type: "bar",
        data: chartRows.map(({ wape, lifecycleStatus }) => ({
          value: wape,
          itemStyle: {
            color: lifecycleStatus === "champion" ? "#E2F86C" : "#6A6A6A",
            borderColor:
              lifecycleStatus === "champion" ? "#7A863A" : "transparent",
            borderWidth: lifecycleStatus === "champion" ? 1 : 0,
            borderRadius: [0, 4, 4, 0],
          },
        })),
        barMaxWidth: 26,
        label: {
          show: true,
          position: "right",
          formatter: ({ value }: { value: number }) => `${value.toFixed(1)}%`,
          color: "#20211F",
          fontFamily: "Space Grotesk",
        },
      },
    ],
  };

  return (
    <>
      <div className="chart-wrap" role="img" aria-label={summary}>
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          style={{ height: "100%" }}
        />
      </div>
      <p className="visually-hidden">
        {summary} Full values are available in the adjacent table.
      </p>
    </>
  );
};
