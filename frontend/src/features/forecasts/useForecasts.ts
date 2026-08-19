import { useQuery } from "@tanstack/react-query";
import { createDataSource } from "../../data";
import type { ForecastFilters } from "../../types/forecasts";

const dataSource = createDataSource();

export const useForecastOptions = () =>
  useQuery({
    queryKey: ["forecast-options"],
    queryFn: () => dataSource.getForecastOptions(),
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
