import { useQuery } from "@tanstack/react-query";
import { createExperimentDataSource } from "../../data/experimentDataSource";
import type { ExperimentFilters } from "../../types/experiments";

export const useExperimentOptions = () =>
  useQuery({
    queryKey: ["experiment-options"],
    queryFn: () => dataSource.getOptions(),
  });

export const useExperiments = (filters: ExperimentFilters) =>
  useQuery({
    queryKey: ["experiments", filters],
    queryFn: () => dataSource.list(filters),
  });

export const useExperimentComparison = (runIds: string[]) =>
  useQuery({
    queryKey: ["experiment-comparison", runIds],
    queryFn: () => dataSource.compare(runIds),
    enabled: runIds.length >= 2,
  });

const dataSource = createExperimentDataSource();
