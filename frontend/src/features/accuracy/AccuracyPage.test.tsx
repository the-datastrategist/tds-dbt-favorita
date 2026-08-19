import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AccuracyPage } from "./AccuracyPage";

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
};

const renderPage = (entry = "/accuracy") =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/accuracy" element={<AccuracyPage />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("AccuracyPage", () => {
  it("renders error diagnostics and preserves selected evidence in the URL", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Error Analysis" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Worst-performing segments" }),
    ).toBeVisible();
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "run=demo_experiment_xgb_global_v17",
      ),
    );
    await user.selectOptions(screen.getByLabelText("Horizon"), "7");
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent("horizon=7"),
    );
    expect(screen.getAllByText("13.8%").length).toBeGreaterThan(0);
  });
});
