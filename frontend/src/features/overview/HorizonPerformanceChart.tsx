import { LineChart } from "echarts/charts";
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactEChartsCore from "echarts-for-react/esm/core";
import type { LeaderboardResult } from "../../types/leaderboard";

echarts.use([
  AriaComponent,
  CanvasRenderer,
  GridComponent,
  LegendComponent,
  LineChart,
  TooltipComponent,
]);

export const HorizonPerformanceChart = ({
  results,
}: {
  results: LeaderboardResult[];
}) => {
  const modelIds = [
    "demo_model_global_xgboost",
    "demo_model_prophet",
    "demo_model_seasonal_naive",
  ];
  const modelNames = new Map(
    results[0]?.rows.map((row) => [row.modelId, row.modelName]) ?? [],
  );
  const description =
    "WAPE by forecast horizon for the current champion, strongest challenger, and seasonal baseline.";
  const option = {
    animationDuration: 250,
    aria: { enabled: true, description },
    grid: { left: 20, right: 24, top: 52, bottom: 36, containLabel: true },
    legend: { top: 10, textStyle: { color: "#5F625C" } },
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: number) => `${value.toFixed(1)}% WAPE`,
    },
    xAxis: {
      type: "category",
      name: "Forecast horizon",
      nameLocation: "middle",
      nameGap: 28,
      data: results.map(({ horizon }) => `D+${horizon}`),
    },
    yAxis: {
      type: "value",
      name: "WAPE (%)",
      scale: true,
      splitLine: { lineStyle: { color: "#EDEDED" } },
    },
    series: modelIds.map((modelId, index) => ({
      name: modelNames.get(modelId) ?? modelId,
      type: "line",
      symbolSize: index === 0 ? 8 : 6,
      lineStyle: {
        width: index === 0 ? 3 : 2,
        type: index === 2 ? "dashed" : "solid",
      },
      itemStyle: { color: ["#7A863A", "#6A6A6A", "#A5A59F"][index] },
      data: results.map(
        ({ rows }) => rows.find((row) => row.modelId === modelId)?.wape ?? null,
      ),
    })),
  };

  return (
    <div
      className="chart-wrap overview-chart"
      role="img"
      aria-label={description}
    >
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        style={{ height: "100%" }}
      />
    </div>
  );
};
