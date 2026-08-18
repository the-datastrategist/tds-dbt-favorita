import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ModelLeaderboardPage } from "./ModelLeaderboardPage";

const LocationProbe = () => {
  const location = useLocation();
  return (
    <output data-testid="location">{`${location.pathname}${location.search}`}</output>
  );
};

const renderPage = (initialEntry = "/models/leaderboard") => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/models/leaderboard"
            element={<ModelLeaderboardPage />}
          />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("ModelLeaderboardPage", () => {
  it("renders the champion and accessible comparison", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Model Leaderboard" }),
    ).toBeVisible();
    expect(screen.getAllByText("Global XGBoost").length).toBeGreaterThan(0);
    expect(screen.getByTestId("leaderboard-chart")).toHaveTextContent("WAPE");
    expect(screen.getByText("Synthetic fixture")).toBeVisible();
  });

  it("stores filter changes in the URL and refreshes the evidence", async () => {
    const user = userEvent.setup();
    renderPage("/models/leaderboard?horizon=2&segment=demo_all");

    const horizon = await screen.findByLabelText("Forecast horizon");
    await user.selectOptions(horizon, "4");
    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("horizon=4");
    });
    await user.selectOptions(
      await screen.findByLabelText("Demand segment"),
      "demo_coastal",
    );

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/models/leaderboard?horizon=4&segment=demo_coastal",
      );
    });
    expect(await screen.findByText("Coastal region, day 4")).toBeVisible();
  });
});
