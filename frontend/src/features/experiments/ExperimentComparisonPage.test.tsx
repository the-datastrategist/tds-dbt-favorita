import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ExperimentComparisonPage } from "./ExperimentComparisonPage";

const LocationProbe = () => {
  const location = useLocation();
  return (
    <output data-testid="location">{`${location.pathname}${location.search}`}</output>
  );
};

const defaultEntry =
  "/experiments/compare?runs=demo_experiment_xgb_global_v17,demo_experiment_xgb_global_v16&metric=wape";

const renderPage = (entry = defaultEntry) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/experiments/compare"
            element={<ExperimentComparisonPage />}
          />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("ExperimentComparisonPage", () => {
  it("compares metrics, configuration, rolling origins, and significance", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Compare Experiments" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Summary metrics" }),
    ).toBeVisible();
    expect(screen.getByText("11.8%")).toBeVisible();
    expect(screen.getByText("18.4 min")).toBeVisible();
    expect(screen.getByText("max depth")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Rolling-origin evidence" }),
    ).toBeVisible();
    expect(screen.getByText("[-1.2, -0.3]")).toBeVisible();
    expect(screen.getByText("meaningful")).toBeVisible();
  });

  it("preserves metric and run changes in the URL", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Compare Experiments" });

    await user.selectOptions(screen.getByLabelText("Metric"), "coverage");
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "metric=coverage",
      );
    });

    await user.selectOptions(
      screen.getByLabelText("Add experiment"),
      "demo_experiment_prophet_v08",
    );
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "demo_experiment_prophet_v08",
      );
    });
    expect(
      (await screen.findAllByText("prophet-holiday-priors-v08")).length,
    ).toBeGreaterThan(0);
  });
});
