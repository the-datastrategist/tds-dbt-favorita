/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_MODE?: "fixture" | "api";
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DBT_DOCS_URL?: string;
  readonly VITE_PREFECT_URL?: string;
  readonly VITE_MLFLOW_URL?: string;
  readonly VITE_RUNBOOK_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
