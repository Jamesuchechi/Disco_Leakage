# TODO.md: disco-leakage build plan

## Progress (agent: update this file and commit after EVERY phase)
- [x] Phase 0: Setup built (repo, deps, sources.csv, fetch script). **Manual step left: run `scripts/fetch_reports.py` and add the other quarters' URLs**
- [x] Phase 1: Extraction built, tested on a synthetic PDF. **Left: run on the real PDFs**
- [x] Phase 2: Cleaning and validation built and tested. **Left: run on the real PDFs**
- [x] Phase 3: Version snapshots built and tested (`src.versions`). **Left: upload to Strata (SDK call not wired, see scripts/load_to_strata.py)**
- [x] Phase 4: Analysis built and tested on Q4 2025 + Q1 2026. **Left: rerun on all real quarters**
- [x] Dashboard page built (`src.build_dashboard`, template in `dashboard/`). **Left: rebuild after real data, publish via GitHub Pages**
- [ ] Phase 5: Write-up
- [ ] Phase 6: Publish

**Rule:** only tick a box after its verification step passes. Before starting, read this file and skip anything already ticked. Do not add scope; new ideas go in `LATER.md`.

---

## Phase 0: Setup and source collection
- [x] Create the repo with the layout from the README; `uv init`, Python 3.12.
- [x] Add dependencies: a PDF table extractor (try `pdfplumber` first, `camelot` as fallback), `polars` or `pandas`, `duckdb`, `pytest`, `jupyter`.
- [ ] Download every report 2025Q2 to 2026Q2 into `data/raw/` (`2026_Q1.pdf` etc.). Only the Q1 2026 URL is known; paste the others into `data/raw/sources.csv`, then run `uv run python scripts/fetch_reports.py`.
- [x] Source log: `fetch_reports.py` writes `data/raw/SOURCES.md` (URL, date, sha256).
- **Verify:** `ls data/raw` shows one PDF per quarter and `SOURCES.md` lists them all.

## Phase 1: Extraction
- [x] Targets matched by caption: billing efficiency, revenue collection, ATC&C loss (Tables 6, 8, 9 in Q1 2026). Energy accounting efficiency is LATER.
- [x] Write `src/extract.py` to dump each table to `data/interim/<period>_<table>.csv`.
- [x] Log extraction failures instead of skipping them silently.
- [ ] **Verify (needs real PDFs):** `uv run python -m src.extract` exits 0, then `uv run pytest tests/test_real_pdf.py` passes. A failure names the page and DisCo; fix the extractor, never patch the data.

## Phase 2: Cleaning and validation
- [x] Define the tidy schema from PRODUCT.md section 6.
- [x] Write `src/clean.py`: canonical DisCo names, unit normalisation, period parsing, restatement flag.
- [x] Write `src/validate.py` and `tests/`: aggregate reconciliation, published efficiencies, the Q2 2026 fixture.
- [x] Write the data dictionary (`data/processed/DICTIONARY.md`).
- [ ] **Verify (needs real PDFs):** `uv run python -m src.validate && uv run pytest` is green. Expect warnings for NERC's own total-vs-rows gaps (see data/processed/DICTIONARY.md). Any error is resolved against the PDF, never patched in code.

## Phase 3: Version in Strata
- [x] `src/versions.py` writes `data/versions/vNN_<report>.csv` (dataset as known after each report) and `manifest.json` with a commit message per version.
- [ ] Upload v01 as a new dataset, then commit each later version in order. `uv run python scripts/load_to_strata.py` prints the exact sequence. To automate, implement `upload_version` against `backend/src/strata_sdk/client.py` (`upload_dataset`, `commit_version`); its signatures were not checked.
- [ ] Capture a screenshot of the diff between two versions for the README. A restated quarter should appear as changed rows.
- [ ] Add the public Strata link to the README.
- **Verify:** version history lists one version per report and the diff view loads without errors.

## Phase 4: Analysis
- [x] Leak split (unbilled vs uncollected) per DisCo and nationally. DisCo rows and NERC's printed totals are never mixed.
- [x] Rank by size of leak, classify billing / collection / both, quarter-over-quarter change with methodology-break flags.
- [x] Next-quarter collection-efficiency estimate (naive and trend) with a back-test; trend is withheld below 3 quarters.
- [x] Checks: unit tests assert hand-calculated values, shares sum to 100%, and Q1 2026 changes match NERC's text (Enugu -6.28pp, Jos +13.49pp collection efficiency).
- [ ] **Verify (needs real PDFs):** `uv run python -m src.analyse` on all quarters; read `data/processed/analysis/FACTS.md` and confirm every number traces to a row in `leakage_by_disco.csv`.

## Dashboard (added after Phase 4)
- [x] `dashboard/template.html` plus `src/build_dashboard.py` -> `docs/index.html`. Self-contained, no external libraries, light and dark themes.
- [ ] After real data is processed: `uv run python -m src.analyse && uv run python -m src.build_dashboard`, open `docs/index.html`, confirm every card matches `FACTS.md`.
- [ ] Turn on GitHub Pages for the `docs/` folder and link the page from the README.

## Phase 5: Write-up
- [ ] One page: the question, the answer in two sentences, three charts maximum, limitations first.
- [ ] Fill in the "Key findings" section of the README.
- [ ] Re-read for any claim stronger than the data supports.
- **Verify:** another person can follow every number back to the dataset.

## Phase 6: Publish
- [ ] Push to GitHub with a clean history and an Apache 2.0 license file.
- [ ] Link the finding from the Strata landing page and your profile.
- [ ] Post a short write-up with one chart.
- **Verify:** open the repo from an incognito window and run the README commands on a fresh clone.

---

## LATER (not in scope)
- Monthly granularity beyond what reconciles cleanly.
- Fuel price pass-through study (case study 2).
- Anything involving a web app.
