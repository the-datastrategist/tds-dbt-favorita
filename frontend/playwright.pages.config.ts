import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e-pages",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:4174/tds-dbt-favorita/app/",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "pages-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command:
      "npm run preview -- --host 127.0.0.1 --port 4174 --base /tds-dbt-favorita/app/",
    url: "http://127.0.0.1:4174/tds-dbt-favorita/app/",
    reuseExistingServer: !process.env.CI,
  },
});
