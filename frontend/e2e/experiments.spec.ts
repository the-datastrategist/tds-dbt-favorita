import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("experiment selection, comparison, and forecast trace work", async ({
  page,
}) => {
  await page.goto("/experiments");
  await expect(
    page.getByRole("heading", { name: "Experiment Runs" }),
  ).toBeVisible();

  await page.getByLabel("Compare xgb-global-promo-lag-v17").click();
  await expect(page).toHaveURL(/runs=demo_experiment_xgb_global_v17/);
  await expect(
    page.getByLabel("Compare xgb-global-promo-lag-v17"),
  ).toBeChecked();
  await page.getByLabel("Compare xgb-global-core-v16").click();
  await expect(page).toHaveURL(/demo_experiment_xgb_global_v16/);
  await expect(page.getByLabel("Compare xgb-global-core-v16")).toBeChecked();
  await page.getByRole("link", { name: "Compare experiments" }).click();

  await expect(
    page.getByRole("heading", { name: "Compare Experiments" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Configuration differences" }),
  ).toBeVisible();
  await expect(page.getByText("[-1.2, -0.3]")).toBeVisible();
  await page.getByLabel("Metric").selectOption("coverage");
  await expect(page).toHaveURL(/metric=coverage/);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);

  await page.goto(
    "/models/demo_model_global_xgboost?horizon=1&segment=demo_all",
  );
  await page.getByRole("link", { name: "View experiments" }).click();
  await expect(page).toHaveURL(/experiments\?model=demo_model_global_xgboost/);
  const exploreLink = page.getByRole("link", { name: "Explore", exact: true });
  await expect(exploreLink).toHaveAttribute(
    "href",
    /forecasts\?run=demo_run_2026_08_18/,
  );
  await exploreLink.click();
  await expect(page).toHaveURL(/forecasts\?run=demo_run_2026_08_18/);
  await expect(
    page.getByRole("heading", { name: "Forecast Explorer" }),
  ).toBeVisible();
});

test("experiment run history is keyboard-sortable and accessible", async ({
  page,
}) => {
  await page.goto("/experiments?status=completed");
  await expect(
    page.getByRole("heading", { name: "Experiment Runs" }),
  ).toBeVisible();
  const runtimeHeader = page.getByRole("columnheader", { name: /Runtime/ });
  await page.getByRole("button", { name: /Runtime/ }).focus();
  await page.keyboard.press("Enter");
  await expect(runtimeHeader).toHaveAttribute("aria-sort", "descending");
  await page.keyboard.press("Enter");
  await expect(runtimeHeader).toHaveAttribute("aria-sort", "ascending");
  await expect(page.locator("tbody tr").first()).toContainText(
    "seasonal-naive-baseline-v03",
  );

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});
