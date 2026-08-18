/// <reference types="vitest/config" />

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ mode }) => ({
  base: mode === "pages" ? "/tds-dbt-favorita/app/" : "/",
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.tsx",
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    css: true,
    coverage: {
      reporter: ["text", "html"],
    },
  },
}));
