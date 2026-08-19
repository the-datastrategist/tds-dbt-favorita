import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { OperationsPage } from "./OperationsPage";

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
};

describe("OperationsPage", () => {
  it("renders read-only operations evidence and keeps public-demo actions disabled", async () => {
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter initialEntries={["/operations"]}>
          <Routes>
            <Route path="/operations" element={<OperationsPage />} />
          </Routes>
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Publication Control" }),
    ).toBeVisible();
    expect(screen.getByText("delivered")).toBeVisible();
    await waitFor(() =>
      expect(screen.getByTestId("location")).toHaveTextContent(
        "run=demo_run_2026_08_18",
      ),
    );
    expect(
      screen.getAllByRole("button", { name: "Create override" }).at(-1),
    ).toBeDisabled();
    expect(
      screen.getByText(/Actions are disabled in this deployment/),
    ).toBeVisible();
  });
});
