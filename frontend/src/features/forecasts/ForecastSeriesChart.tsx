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
import type { ForecastRow } from "../../types/forecasts";

echarts.use([
  AriaComponent,
  CanvasRenderer,
  GridComponent,
  LegendComponent,
  LineChart,
  TooltipComponent,
]);

export const ForecastSeriesChart = ({ rows }: { rows: ForecastRow[] }) => {
  const description =
    "Actual demand, P50 statistical forecast, published forecast, and the P10 to P90 prediction interval by target date.";
  const dates = rows.map(({ targetDate }) => targetDate.slice(5));

  const option = {
    animationDuration: 250,
    aria: { enabled: true, description },
    grid: { left: 24, right: 24, top: 54, bottom: 38, containLabel: true },
    legend: { top: 10, textStyle: { color: "#5F625C" } },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      name: "Target date",
      nameLocation: "middle",
      nameGap: 28,
      data: dates,
    },
    yAxis: {
      type: "value",
      name: "Demand units",
      scale: true,
      splitLine: { lineStyle: { color: "#EDEDED" } },
    },
    series: [
      {
        name: "P10",
        type: "line",
        symbol: "none",
        lineStyle: { opacity: 0 },
        stack: "interval",
        data: rows.map(({ p10 }) => p10),
      },
      {
        name: "P10–P90 interval",
        type: "line",
        symbol: "none",
        lineStyle: { opacity: 0 },
        areaStyle: { color: "rgba(122, 134, 58, 0.22)" },
        stack: "interval",
        data: rows.map(({ p10, p90 }) => p90 - p10),
      },
      {
        name: "Actual",
        type: "line",
        connectNulls: false,
        itemStyle: { color: "#20211F" },
        lineStyle: { width: 3 },
        data: rows.map(({ actual }) => actual),
      },
      {
        name: "P50 statistical",
        type: "line",
        itemStyle: { color: "#7A863A" },
        lineStyle: { width: 2 },
        data: rows.map(({ p50 }) => p50),
      },
      {
        name: "Published",
        type: "line",
        itemStyle: { color: "#3559A8" },
        lineStyle: { width: 2, type: "dashed" },
        data: rows.map(({ publishedForecast }) => publishedForecast),
      },
    ],
  };

  return (
    <div
      className="chart-wrap forecast-chart"
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
