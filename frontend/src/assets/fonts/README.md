# Self-hosted ForecastLab fonts

ForecastLab self-hosts the brand typefaces so the public demo makes no third-party font request.
Import `fonts.css` once from the frontend entry point.

| Family | Included files | UI use | License |
|---|---|---|---|
| Space Grotesk | Latin WOFF2, variable weight 300-700 | Primary interface, headings, metrics, and body text | SIL Open Font License 1.1 |
| Poppins | Latin WOFF2, Regular 400 and Bold 700 | Limited branded supporting copy | SIL Open Font License 1.1 |

## Sources

Files were retrieved on 2026-08-18 from the official
[Google Fonts repository](https://github.com/google/fonts) and Google Fonts static asset service:

- `Space Grotesk v22`, Latin variable WOFF2 published by `fonts.gstatic.com`
- `ofl/spacegrotesk/OFL.txt`
- `Poppins v24`, Latin Regular and Bold WOFF2 files published by `fonts.gstatic.com`
- `ofl/poppins/OFL.txt`

Google Fonts documents that family directories contain the served font binaries and their
applicable license. Preserve each adjacent `OFL.txt` whenever the font files are redistributed.
The included subsets cover the English-language public demo and Latin-script UI text; unsupported
scripts intentionally fall back to the system font stack declared in `fonts.css`.

## Integrity

| File | SHA-256 |
|---|---|
| `SpaceGrotesk-Latin-Variable.woff2` | `a0d054c4af557de20afd6ca59f47ab353bcaec49c63ff04b6c9d39d0f8910557` |
| `space-grotesk/OFL.txt` | `18a4de52385f6b988782639d5d0cc1326e5a8c2de9a7f01d7b20d9aedcc60943` |
| `Poppins-Latin-Regular.woff2` | `3dc5d0c52428fe1696264907a1054ebbaac07f8cbe45832c105f819c2ae397c0` |
| `Poppins-Latin-Bold.woff2` | `197a3cbd7290c242c5c765268cdd69a9a39867fdc80cd13071f243a81c56fb76` |
| `poppins/OFL.txt` | `8503c30a4d7e09c4c09015fee42f829f18acbe6330755e9930ba50ea44eaa157` |

Do not replace or transform a font without updating its source record, license, checksum, and
visual-regression baseline.
