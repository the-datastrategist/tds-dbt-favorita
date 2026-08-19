import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ForecastExplorerPage } from "./ForecastExplorerPage";

const LocationProbe = () => {
  const location = useLocation();
  return (
    <output data-testid="location">{`${location.pathname}${location.search}`}</output>
  );
};

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/forecasts"]}>
        <Routes>
          <Route path="/forecasts" element={<ForecastExplorerPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("ForecastExplorerPage", () => {
  it("renders canonical forecasts and complete provenance", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Forecast Explorer" }),
    ).toBeVisible();
    expect(screen.getAllByText("Quito Store 01").length).toBeGreaterThan(0);
    expect(screen.getByText("142")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "View provenance" }));
    expect(
      screen.getByRole("heading", { name: "Forecast provenance" }),
    ).toBeVisible();
    expect(screen.getByText("demo_contract_91544443")).toBeVisible();
    expect(screen.getByText("demo_reconciliation_0818")).toBeVisible();
  });

  it("persists horizon and exception filters in the URL", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Forecast Explorer" });
    await user.selectOptions(screen.getByLabelText("Horizon"), "3");
    await user.selectOptions(screen.getByLabelText("Exception state"), "watch");

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("horizon=3");
      expect(screen.getByTestId("location")).toHaveTextContent(
        "exception=watch",
      );
    });
    expect(screen.getByText("2026-08-21")).toBeVisible();
    expect(screen.queryByText("2026-08-20")).not.toBeInTheDocument();
  });
});
