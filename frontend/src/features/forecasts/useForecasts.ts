import { useQuery } from "@tanstack/react-query";
import { createDataSource } from "../../data";
import type { ForecastFilters } from "../../types/forecasts";

const dataSource = createDataSource();

export const useForecastOptions = (runId?: string) =>
  useQuery({
    queryKey: ["forecast-options", runId],
    queryFn: () => dataSource.getForecastOptions(runId),
  });

export const useForecasts = (filters: ForecastFilters | null) =>
  useQuery({
    queryKey: [
      "forecasts",
      filters?.runId,
      filters?.entityId,
      filters?.horizon,
      filters?.modelId,
      filters?.exceptionState,
    ],
    queryFn: () => {
      if (!filters) throw new Error("Forecast filters are required");
      return dataSource.getForecasts(filters);
    },
    enabled: filters !== null,
  });
