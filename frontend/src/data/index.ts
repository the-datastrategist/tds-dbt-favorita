import type { ForecastLabDataSource } from "./dataSource";
import { ApiDataSource } from "./apiDataSource";
import { FixtureDataSource } from "./fixtureDataSource";

export const createDataSource = (): ForecastLabDataSource => {
  if (import.meta.env.VITE_DATA_MODE === "api") {
    return new ApiDataSource(import.meta.env.VITE_API_BASE_URL ?? "");
  }
  return new FixtureDataSource();
};
