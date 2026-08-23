import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("exposes stable specialist deep links", () => {
    render(
      <MemoryRouter initialEntries={["/overview"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="overview" element={<p>Overview content</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const tools = screen.getByRole("navigation", { name: "Specialist tools" });
    expect(tools).toBeVisible();
    expect(screen.getByRole("link", { name: "dbt lineage" })).toHaveAttribute(
      "href",
      "https://the-datastrategist.github.io/tds-dbt-favorita/dbt-docs/",
    );
    expect(screen.getByRole("link", { name: "Prefect" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(screen.getByRole("link", { name: "MLflow" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(screen.getByRole("link", { name: "Runbook" })).toHaveAttribute(
      "target",
      "_blank",
    );
  });
});
