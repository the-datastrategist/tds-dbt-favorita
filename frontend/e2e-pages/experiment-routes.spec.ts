import { expect, test } from "@playwright/test";

const runQuery =
  "runs=demo_experiment_xgb_global_v17,demo_experiment_xgb_global_v16&metric=coverage";

test("Pages serves and refreshes experiment routes beneath the repository subpath", async ({
  page,
}) => {
  await page.goto(`#/experiments/compare?${runQuery}`);
  await expect(
    page.getByRole("heading", { name: "Compare Experiments" }),
  ).toBeVisible();
  await expect(page.getByLabel("Metric")).toHaveValue("coverage");

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Compare Experiments" }),
  ).toBeVisible();
  await expect(page).toHaveURL(
    /\/tds-dbt-favorita\/app\/#\/experiments\/compare/,
  );

  await page.getByRole("link", { name: "Back to experiment runs" }).click();
  await expect(
    page.getByRole("heading", { name: "Experiment Runs" }),
  ).toBeVisible();
});
