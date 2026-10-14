# PRODUCT.md: disco-leakage

## 1. The question

Nigeria's DisCos receive electricity valued at hundreds of billions of naira each quarter and recover only part of it as cash. The loss has two distinct causes with different fixes:

- **Unbilled energy**: supplied but never invoiced (losses, theft, metering gaps).
- **Uncollected revenue**: invoiced but never paid.

**Primary question:** which of the two dominates, for which DisCos, and is each DisCo getting better or worse?

## 2. Audience

1. Hiring managers and recruiters reviewing a data science portfolio. They need to see a real question, messy data handled carefully, and a finding stated plainly.
2. Anyone following the Nigerian power sector who wants the regulator's figures in one clean, comparable table.

## 3. Core loop (one sentence)

Extract NERC's DisCo tables, clean and validate them, version them in Strata, and publish a one-page finding about where the money leaks.

## 4. Scope

**In scope**
- Quarterly DisCo data for the available comparable quarters.
- Monthly factsheet data if it can be reconciled to the quarterly figures.
- Per-DisCo and aggregate views of: energy received, billed, collected, ATC&C losses.
- One written finding (one page) plus the supporting notebook.

**Out of scope (do not build)**
- A hosted web app, accounts, or an API. (A single static dashboard page generated from the analysis outputs is in scope.)
- Tariff modelling, generation-side analysis, or subsidy analysis.
- Any forecasting claim beyond an indicative next-quarter estimate.
- Scraping beyond NERC's published reports.

## 5. Metric definitions

All values are in naira (N) billions unless stated. These follow NERC's own formulas in its quarterly report.

| Metric | Definition |
|---|---|
| Energy received (value) | Energy received (kWh) x average allowed tariff. From 2026Q1 the tariff is adjusted for VAT |
| Billed | Value billed to customers |
| Collected | Revenue collected |
| Billing efficiency (BE) | billed / received (naira value) |
| Collection efficiency (CE) | collected / billed |
| ATC&C loss | 1 - (BE x CE). Splits into billing loss (technical + commercial) and collection loss |
| Unbilled loss (derived) | received - billed |
| Uncollected loss (derived) | billed - collected |

**Primary leak (classification):** unbilled share = unbilled / (received - collected). At or above 60% the DisCo leaks mainly at **billing**; at or below 40% mainly at **collection**; otherwise **both**. Thresholds are constants in `src/analyse.py`.

**Comparability rule:** collection efficiency compares across quarters (it uses billed and collected money). Billing efficiency, ATC&C and unbilled loss do not compare across the 2025Q2 and 2026Q1 breaks, so quarter-over-quarter changes for them are left blank there.

**Series breaks (from NERC footnotes):** billing efficiency was computed from energy (GWh) before 2025Q2 and from commercial (naira) values from 2025Q2; from 2026Q1 energy received is VAT-adjusted. Comparisons across either break must be labelled.

## 6. Data requirements

- One row per **DisCo × period** (long format): `period`, `disco`, `received_ngn_bn`, `billed_ngn_bn`, `collected_ngn_bn`, `atcc_loss_pct`, `source_report`, `source_page`.
- 11 DisCos per period (plus an aggregate row kept separately, never mixed into DisCo rows).
- Every value traceable to a report page.

## 7. Validation (non-negotiable)

- Billed totals must equal the sum of DisCo rows within rounding. NERC's own received and collected totals can differ slightly from their rows: a gap over 0.06 is a warning, over 0.25% is an error.
- Identity checks per DisCo: billed/received = published BE; collected/billed = published CE; 1 - BE x CE = published ATC&C (all within rounding).
- Golden fixture: NERC's Q1 2026 report (Tables 6, 8, 9) is transcribed in `tests/golden.py`. Aggregate: received 955.19, billed 756.93, collected 597.56, BE 79.24%, CE 78.95%, ATC&C 37.44%. `tests/test_real_pdf.py` compares the extractor on the real PDF with it.
- Known source inconsistency (warning, not error): 2026Q1 received rows sum to 955.73 against a printed total of 955.19.
- A value that fails reconciliation blocks the pipeline until a human resolves it.

## 8. Deliverables

1. Clean tidy dataset (Parquet and CSV) with a data dictionary.
2. Versioned in Strata, one version per quarter.
3. Reproducible pipeline (`src/`) and tests.
4. One static dashboard page (`docs/index.html`): national split, collection-efficiency trend (national line plus any DisCo), leak by DisCo, sortable detail table, quarter switcher.
5. One-page finding with 3 charts maximum.
6. README with a plain-language summary at the top.

## 9. Success criteria

- A stranger can reproduce the dataset from the raw PDFs with the commands in the README.
- Every number in the finding links to a table in the dataset.
- All validation checks pass.
- The finding states its limitations (short history, restatements) in the first screen.
- Done means published, not perfect.

## 10. Risks

| Risk | Mitigation |
|---|---|
| PDF tables extract badly | Try two extractors; fall back to manual transcription for a single table and document it |
| DisCo names or boundaries change across reports | Maintain a canonical name map and log every alias |
| Reports restate earlier figures | Keep a `restated` flag, log every change in `restatements.csv`, use the latest value |
| A missing row is filled from another table | Each table is cut at the next "Table N:" caption; a missing DisCo fails the run |
| Short history invites overclaiming | State limits up front; no causal claims |
| Scope creep | Section 4 is the contract; additions go to a `LATER.md`, not the plan |
