# disco-leakage

Where does Nigeria's electricity money leak: energy that is never billed, or billed energy that is never paid for? And which distribution companies (DisCos) are actually improving?

This project turns NERC's quarterly (and monthly) DisCo reports, which are published as PDF tables, into a clean, versioned dataset and a short, evidence-backed analysis.

> Status: Phases 0-4 built (setup, extraction, cleaning and validation, versioning, analysis). Phases 5-6 not started. See [TODO.md](./TODO.md) for the build plan and [PRODUCT.md](./PRODUCT.md) for scope and definitions.

## Core loop

**Question → extract tables from NERC reports → clean and validate → version in Strata → analyse → one-page finding.**

## Key findings

_To be filled in after Phase 4. Each finding must link to the table or chart that supports it._

## Data

| Source | What it gives | Format | Cadence |
|---|---|---|---|
| NERC quarterly reports (nerc.gov.ng) | Energy received, billed, collected, per DisCo, plus ATC&C losses | PDF tables | Quarterly |
| NERC monthly factsheets | Same metrics at monthly granularity | PDF / web | Monthly |

Raw PDFs are stored unmodified in `data/raw/` and never edited. Everything downstream is reproducible from them.

## Method

1. **Extract** tables from each report with a PDF table extractor.
2. **Normalise** DisCo names, units (₦ billion, GWh), and periods into one long-format schema.
3. **Validate** every quarter against published totals (see `tests/`).
4. **Version** each quarter as a commit in Strata so changes are diffable.
5. **Analyse**: split loss into unbilled and uncollected, rank DisCos, track quarter-over-quarter change, add a simple projection.

## Repository layout

```
disco-leakage/
├── data/
│   ├── raw/            # original NERC PDFs (untouched)
│   ├── interim/        # extracted tables, one CSV per report table
│   ├── versions/       # one dataset snapshot per NERC report, for Strata diffs
│   └── processed/      # tidy dataset, DICTIONARY.md, and analysis/ outputs
├── src/
│   ├── extract.py      # PDF -> raw tables
│   ├── clean.py        # raw tables -> tidy schema
│   ├── validate.py     # reconciliation checks
│   ├── versions.py     # dataset as of each report -> data/versions
│   ├── analyse.py      # leak split, rankings, quarter changes, projection
│   ├── build_dashboard.py  # analysis outputs -> docs/index.html
│   ├── ingest.py       # unified ingestion for PDF, CSV, Excel, Parquet
│   ├── app.py          # interactive FastAPI web application & API
│   └── templates/app.html  # modern interactive frontend
├── dashboard/template.html  # static dashboard; src/build_dashboard.py fills it -> docs/index.html
├── notebooks/          # exploration and the final write-up
├── tests/              # validation against published totals & upload tests
├── PRODUCT.md
├── TODO.md
└── README.md
```

## Interactive Web Application

Run the local web app to upload files (`.pdf`, `.csv`, `.xlsx`, `.parquet`), inspect real-time validation checks, explore interactive charts, and export data:

```bash
uv run python -m src.app
```
Then navigate to **http://127.0.0.1:8000** in your browser.

- **Multi-Format Ingestion**: Drag & drop NERC quarterly report PDFs, raw/tidy CSVs, multi-sheet Excel files, or Parquet datasets.
- **Automated Validation**: Instant coverage, reconciliation, and mathematical tolerance checks with status indicators.
- **Live Preview & Visuals**: Executive KPI cards, collection efficiency trend lines (DisCo vs National), stacked leak breakdown (unbilled vs uncollected), and sortable detail table.
- **Export Options**: Download cleaned data as CSV, Parquet, JSON, or standalone static HTML dashboard.

## Batch Pipeline

```bash
uv sync --extra dev
# 1. put each report's URL in data/raw/sources.csv (the Q1 2026 URL is already there), then:
uv run python scripts/fetch_reports.py   # PDFs -> data/raw, hashes -> data/raw/SOURCES.md
uv run python -m src.extract             # PDFs -> data/interim/*.csv (fails loudly on any missing row)
uv run python -m src.clean               # -> data/processed/disco_quarterly.{parquet,csv}
uv run python -m src.validate            # reconciles every number; exit 1 on any error
uv run python -m src.versions            # -> data/versions/v01_*.csv ... + manifest.json
uv run python scripts/load_to_strata.py  # prints the upload/commit sequence for Strata
uv run python -m src.analyse             # -> data/processed/analysis/ (incl. FACTS.md)
uv run python -m src.build_dashboard     # -> docs/index.html (static dashboard; open it, or host on GitHub Pages)
uv run pytest                            # includes golden tests against the real Q1 2026 PDF and ingest suite
```

## Limitations

- Only about five quarters (2025Q2 to 2026Q2) are comparable: NERC changed how billing efficiency is computed in 2025Q2, and from 2026Q1 the naira value of energy received is VAT-adjusted. Both breaks are flagged in the data (`billing_method`, `received_basis`). The analysis is descriptive; any projection is indicative only.
- NERC's printed "All DisCos" totals for received and collected differ slightly from the sum of the DisCo rows. Validation reports this as a warning; see `data/processed/DICTIONARY.md`.
- Figures come from regulator reports. Where a report restates an earlier quarter, the latest published value is used and the restatement is logged.
- Metric definitions follow NERC's own wording; any deviation is documented in [PRODUCT.md](./PRODUCT.md).

## Strata

Dataset and version history: _link to be added after Phase 3._

## License

Code: Apache 2.0. Source data belongs to NERC and is used for analysis with attribution.
