import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("leaderboard filters and model drilldown work", async ({ page }) => {
  await page.goto("/models/leaderboard");

  await expect(
    page.getByRole("heading", { name: "Model Leaderboard" }),
  ).toBeVisible();
  await expect(page.getByText("Global XGBoost").first()).toBeVisible();

  await page.getByLabel("Forecast horizon").selectOption("4");
  await page.getByLabel("Demand segment").selectOption("demo_coastal");
  await expect(page).toHaveURL(/horizon=4.*segment=demo_coastal/);
  await expect(page.getByText("Coastal region, day 4")).toBeVisible();

  await page.getByRole("link", { name: "Global XGBoost" }).click();
  await expect(
    page.getByRole("heading", { name: "Global XGBoost" }),
  ).toBeVisible();
  await expect(page.getByText("Evaluation context")).toBeVisible();
});

test("leaderboard has no automatically detectable accessibility violations", async ({
  page,
}) => {
  await page.goto("/models/leaderboard");
  await expect(
    page.getByRole("heading", { name: "Model Leaderboard" }),
  ).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("forecast explorer filters rows and exposes provenance", async ({
  page,
}) => {
  await page.goto("/forecasts");
  await expect(
    page.getByRole("heading", { name: "Forecast Explorer" }),
  ).toBeVisible();

  await page.getByLabel("Horizon").selectOption("3");
  await page.getByLabel("Exception state").selectOption("watch");
  await expect(page).toHaveURL(/horizon=3.*exception=watch/);
  await expect(page.getByRole("cell", { name: "2026-08-21" })).toBeVisible();

  await page.getByRole("button", { name: "View provenance" }).click();
  await expect(
    page.getByRole("heading", { name: "Forecast provenance" }),
  ).toBeVisible();
  await expect(page.getByText("demo_publication_20260818_01")).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
