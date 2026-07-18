# dbt lineage and catalog

dbt Docs provides the generated model catalog, column metadata, and interactive lineage graph. It is kept alongside this documentation portal while retaining its own generated interface.

## Published site

[Open dbt Docs](https://the-datastrategist.github.io/tds-dbt-favorita/dbt-docs/)

The published link is available after the GitHub Pages workflow has completed.

## Run locally

Generate and serve dbt Docs at `http://127.0.0.1:8080`:

```bash
make dbt-ui
```

To generate the static files without starting a server:

```bash
make dbt-docs-generate
```
