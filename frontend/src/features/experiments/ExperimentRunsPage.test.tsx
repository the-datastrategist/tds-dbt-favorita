import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ExperimentRunsPage } from "./ExperimentRunsPage";

const LocationProbe = () => {
  const location = useLocation();
  return (
    <output data-testid="location">{`${location.pathname}${location.search}`}</output>
  );
};

const renderPage = (entry = "/experiments") => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/experiments" element={<ExperimentRunsPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("ExperimentRunsPage", () => {
  it("filters run history from URL-addressable controls", async () => {
    const user = userEvent.setup();
    renderPage("/experiments?model=demo_model_global_xgboost");

    expect(
      await screen.findByRole("heading", { name: "Experiment Runs" }),
    ).toBeVisible();
    expect(screen.getByText("xgb-global-promo-lag-v17")).toBeVisible();
    expect(
      screen.queryByText("prophet-holiday-priors-v08"),
    ).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Status"), "failed");
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("status=failed");
    });
    expect(await screen.findByText("xgb-promo-lag-ablation-v04")).toBeVisible();
    expect(
      screen.queryByText("xgb-global-promo-lag-v17"),
    ).not.toBeInTheDocument();
  });

  it("persists selected runs and enables comparison after two selections", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Experiment Runs" });

    await user.click(screen.getByLabelText("Compare xgb-global-promo-lag-v17"));
    await user.click(screen.getByLabelText("Compare xgb-global-core-v16"));

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "runs=demo_experiment_xgb_global_v17%2Cdemo_experiment_xgb_global_v16",
      );
    });
    const compareLink = screen.getByRole("link", {
      name: "Compare experiments",
    });
    expect(compareLink).toHaveAttribute(
      "href",
      expect.stringContaining("/experiments/compare"),
    );
  });

  it("sorts run history using accessible column controls", async () => {
    const user = userEvent.setup();
    renderPage("/experiments?status=completed");
    await screen.findByRole("heading", { name: "Experiment Runs" });

    await user.click(screen.getByRole("button", { name: /Runtime/ }));
    await user.click(screen.getByRole("button", { name: /Runtime/ }));
    const rows = screen.getAllByRole("row");
    expect(
      within(rows[1]!).getByText("seasonal-naive-baseline-v03"),
    ).toBeVisible();
  });
});
