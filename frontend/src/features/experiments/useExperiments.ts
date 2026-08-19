import { useQuery } from "@tanstack/react-query";
import { experimentDataSource } from "../../data/experimentDataSource";
import type { ExperimentFilters } from "../../types/experiments";

export const useExperimentOptions = () =>
  useQuery({
    queryKey: ["experiment-options"],
    queryFn: () => experimentDataSource.getOptions(),
  });

export const useExperiments = (filters: ExperimentFilters) =>
  useQuery({
    queryKey: ["experiments", filters],
    queryFn: () => experimentDataSource.list(filters),
  });

export const useExperimentComparison = (runIds: string[]) =>
  useQuery({
    queryKey: ["experiment-comparison", runIds],
    queryFn: () => experimentDataSource.compare(runIds),
    enabled: runIds.length > 0,
  });
