import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { OverviewPage } from "./OverviewPage";

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("OverviewPage", () => {
  it("summarizes the governed champion and seven-day evidence", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Platform Overview" }),
    ).toBeVisible();
    expect(screen.getAllByText("Global XGBoost").length).toBeGreaterThan(0);
    expect(screen.getByText("14.6%")).toBeVisible();
    expect(screen.getByText("19.2%")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Champion rationale" }),
    ).toBeVisible();
    expect(
      screen.getByText("Sufficient rolling-origin evidence"),
    ).toBeVisible();
  });
});
