import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HierarchyPage } from "./HierarchyPage";

describe("HierarchyPage", () => {
  it("renders hierarchy navigation, reconciled values, and coherence gates", async () => {
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <HierarchyPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", {
        name: "Hierarchy & Reconciliation",
      }),
    ).toBeVisible();
    expect(screen.getByText("Store 01")).toBeVisible();
    expect(screen.getByText("Coherent child totals")).toBeVisible();
    expect(screen.getByText("demo_reconciliation_2026_08_18")).toBeVisible();
  });
});
