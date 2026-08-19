import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("error analysis is URL-addressable and accessible", async ({ page }) => {
  await page.goto("/accuracy");
  await expect(
    page.getByRole("heading", { name: "Error Analysis" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/run=demo_experiment_xgb_global_v17/);
  await page.getByLabel("Horizon").selectOption("7");
  await expect(page).toHaveURL(/horizon=7/);
  await expect(
    page.getByRole("heading", { name: "Worst-performing segments" }),
  ).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("public operations view exposes evidence but no mutations", async ({
  page,
}) => {
  await page.goto("/operations");
  await expect(
    page.getByRole("heading", { name: "Publication Control" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/run=demo_run_2026_08_18/);
  await expect(
    page.getByText(/Actions are disabled in this deployment/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create override" }).last(),
  ).toBeDisabled();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
