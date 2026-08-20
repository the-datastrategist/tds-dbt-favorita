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
import type { ExperimentMetric, ExperimentRun } from "../../types/experiments";

echarts.use([
  AriaComponent,
  CanvasRenderer,
  GridComponent,
  LegendComponent,
  LineChart,
  TooltipComponent,
]);

const colors = ["#59651f", "#3559a8", "#8a5d00", "#7a3e91", "#247a4a"];

const metricLabel: Record<ExperimentMetric, string> = {
  wape: "WAPE (%)",
  bias: "Bias (units)",
  coverage: "Coverage (%)",
};

const metricValue = (
  value: { wape: number; bias: number; coverage: number | null },
  metric: ExperimentMetric,
) =>
  metric === "coverage"
    ? value.coverage === null
      ? null
      : value.coverage * 100
    : value[metric];

export const ExperimentHorizonChart = ({
  runs,
  metric,
}: {
  runs: ExperimentRun[];
  metric: ExperimentMetric;
}) => {
  const summary = `${metricLabel[metric]} by forecast horizon for ${runs.map(({ label }) => label).join(", ")}.`;
  const option = {
    animationDuration: 250,
    aria: { enabled: true, description: summary },
    color: colors,
    grid: { left: 42, right: 22, top: 48, bottom: 40, containLabel: true },
    legend: {
      top: 4,
      type: "scroll",
      textStyle: { color: "#5f625c", fontFamily: "Space Grotesk" },
    },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      name: "Forecast horizon",
      nameLocation: "middle",
      nameGap: 28,
      data: [1, 2, 3, 4, 5, 6, 7].map((horizon) => `D+${horizon}`),
      axisLine: { lineStyle: { color: "#c9cbc5" } },
    },
    yAxis: {
      type: "value",
      name: metricLabel[metric],
      axisLabel: {
        formatter: metric === "bias" ? "{value}" : "{value}%",
        color: "#5f625c",
      },
      splitLine: { lineStyle: { color: "#ededed" } },
    },
    series: runs.map((run) => ({
      name: run.label,
      type: "line",
      symbolSize: 7,
      data: run.horizons.map((value) => metricValue(value, metric)),
      emphasis: { focus: "series" },
    })),
  };

  return (
    <div className="comparison-chart" role="img" aria-label={summary}>
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        style={{ height: "100%" }}
      />
    </div>
  );
};

export const RollingOriginChart = ({ runs }: { runs: ExperimentRun[] }) => {
  const origins = [
    ...new Set(
      runs.flatMap((run) => run.rollingOrigins.map(({ origin }) => origin)),
    ),
  ].sort();
  const summary = `Rolling-origin WAPE for ${runs.map(({ label }) => label).join(", ")}.`;
  const option = {
    animationDuration: 250,
    aria: { enabled: true, description: summary },
    color: colors,
    grid: { left: 42, right: 22, top: 48, bottom: 44, containLabel: true },
    legend: {
      top: 4,
      type: "scroll",
      textStyle: { color: "#5f625c", fontFamily: "Space Grotesk" },
    },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      name: "Evaluation origin",
      nameLocation: "middle",
      nameGap: 30,
      data: origins,
      axisLabel: { color: "#5f625c" },
      axisLine: { lineStyle: { color: "#c9cbc5" } },
    },
    yAxis: {
      type: "value",
      name: "WAPE (%)",
      axisLabel: { formatter: "{value}%", color: "#5f625c" },
      splitLine: { lineStyle: { color: "#ededed" } },
    },
    series: runs.map((run) => ({
      name: run.label,
      type: "line",
      symbolSize: 7,
      data: origins.map(
        (origin) =>
          run.rollingOrigins.find((row) => row.origin === origin)?.wape ?? null,
      ),
      emphasis: { focus: "series" },
    })),
  };

  return (
    <div className="comparison-chart" role="img" aria-label={summary}>
      <ReactEChartsCore
        echarts={echarts}
        option={option}
        style={{ height: "100%" }}
      />
    </div>
  );
};
