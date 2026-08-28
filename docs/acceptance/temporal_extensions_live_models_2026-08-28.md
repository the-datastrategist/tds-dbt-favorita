# Temporal migration and extension-dispatch acceptance — 2026-08-28

The temporal migration and model-provider dispatch paths were accepted against the live
`tds-favorita` Vertex AI environment after [PR #71](https://github.com/the-datastrategist/tds-dbt-favorita/pull/71), with two follow-up feature-availability guards merged in
[PR #72](https://github.com/the-datastrategist/tds-dbt-favorita/pull/72) and
[PR #73](https://github.com/the-datastrategist/tds-dbt-favorita/pull/73).

## Automated temporal acceptance

The focused acceptance suite exercised `execute_forecast_pipeline` end to end for both `week`
and `month` contracts, including canonical target timestamps, blocking gates, and persistence
planning. The focused temporal, backfill, backtest-contract, extension, time-series, Prophet,
and forecast-pipeline suite passed locally: **75 passed**. Configuration validation also
completed for all seven shipped model configurations.

This is full automated weekly/monthly pipeline acceptance. The Favorita demonstration source is
daily, so this record deliberately does not claim a live weekly or monthly source deployment.

## Live model-family acceptance

Every distinct migrated model provider completed a Vertex Custom Job successfully. All jobs were
pinned to immutable Artifact Registry digests; no mutable image tag is used for acceptance.

| Provider / configuration | Vertex Custom Job | Start → end (UTC) | Immutable image digest |
|---|---|---|---|
| Direct XGBoost / `favorita_store_h1_7_direct_xgboost` | `496754001899945984` | 14:37:35 → 14:41:38 | `sha256:276e63205bd15ae14e92b404c7b63b9b19289ce99af7fbc2b1ded686a9c37a28` |
| XGBoost / `favorita_store_n1d_xgboost` | `6087972939280416768` | 14:55:46 → 14:58:17 | `sha256:eda018e9630bc733e802437ac9345c5005ac25ecfcd2b123d34fd2ccedc21d68` |
| Random forest / `favorita_store_n1d_rf` | `7619196812586385408` | 14:55:27 → 15:15:08 | `sha256:eda018e9630bc733e802437ac9345c5005ac25ecfcd2b123d34fd2ccedc21d68` |
| Prophet / `favorita_store_n1d_prophet` | `4100337391238119424` | 14:23:30 → 14:26:02 | `sha256:c87aaf15b8a976b367dc739e47a8723f889d836bbef74c07d77ef80debd89deb` |
| ARIMA / `favorita_store_n1d_arima` | `2810056097996472320` | 14:24:48 → 14:28:20 | `sha256:c87aaf15b8a976b367dc739e47a8723f889d836bbef74c07d77ef80debd89deb` |
| SARIMA / `favorita_store_n1d_sarima` | `8734541407802359808` | 14:23:44 → 14:32:17 | `sha256:c87aaf15b8a976b367dc739e47a8723f889d836bbef74c07d77ef80debd89deb` |

The jobs prove that configured model providers resolve through the production dispatcher and
execute their migrated, frequency-aware training paths. The direct model covers explicit
multi-horizon behavior; the other five cover the standard tabular and time-series families.

## Leakage controls proved during live acceptance

Live validation exposed two canonical-adapter labels that must not be model inputs:

- auxiliary `target_horizon_*` labels; and
- realized `sales_*_n<period>d` demand aggregates.

The two guards were centralized in feature-matrix preparation, given regression coverage, and
validated by the final successful XGBoost and random-forest jobs. The feature-availability
registry continues to reject any observed-after-period feature that escapes those structural
guards.

## Conclusion

Temporal future frames, seasonal defaults, validation purges, rolling-origin backtests, and
backfills use configured periods. Model providers are dispatched through the production
extension boundary with provider lineage. The daily Favorita model families are live accepted.
The remaining non-daily work is a future live source implementation, not a gap in the automated
weekly/monthly contract coverage.
