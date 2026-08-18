import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => cleanup());

vi.mock("echarts-for-react/esm/core", () => ({
  default: ({ option }: { option: { aria?: { description?: string } } }) => (
    <div data-testid="leaderboard-chart">{option.aria?.description}</div>
  ),
}));
