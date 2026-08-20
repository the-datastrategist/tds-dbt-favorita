import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { PipelineHealthPage } from "./PipelineHealthPage";

describe("PipelineHealthPage", () => {
  it("renders ordered stages and fail-closed validation gates", async () => {
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <PipelineHealthPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Pipeline Health" }),
    ).toBeVisible();
    expect(screen.getByText("champion scoring")).toBeVisible();
    expect(screen.getByText("output_cardinality")).toBeVisible();
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
  });
});
