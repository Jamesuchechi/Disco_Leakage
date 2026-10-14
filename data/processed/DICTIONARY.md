# Data dictionary

`disco_quarterly.csv` / `.parquet`: one row per DisCo x quarter (11 DisCos). `aggregate_quarterly.csv`: one row per quarter, NERC's "All DisCos" figures (same columns plus `atcc_derived`, no `disco`).
`restatements.csv`: every value that changed between two NERC reports.

| Column | Unit | Meaning |
|---|---|---|
| `period` | `YYYYQn` | Quarter the figures describe |
| `quarter_end` | date | Last day of the quarter |
| `disco` | text | Canonical DisCo name (aliases like PH or P/Harcourt are mapped to Port Harcourt) |
| `received_ngn_bn` | N billion | Value of energy received, priced at the average allowed tariff (NERC "Energy Received") |
| `billed_ngn_bn` | N billion | Value billed to customers |
| `collected_ngn_bn` | N billion | Revenue collected |
| `billing_eff_pct` | % | NERC's published billing efficiency (billed / received) |
| `collection_eff_pct` | % | NERC's published collection efficiency (collected / billed) |
| `atcc_loss_pct` | % | NERC's published ATC&C loss. For aggregate rows it is derived: 100 x (1 - BE x CE) |
| `atcc_target_pct` | % | MYTO target ATC&C. For the earlier quarter in a report it is derived as actual + variance |
| `reported_in` | `YYYYQn` | The NERC report the value was taken from (the latest report that published this quarter) |
| `restated` | bool | True if any report published a different value for this DisCo-quarter |
| `billing_method` | text | `energy_based` before 2025Q2, `commercial` from 2025Q2 (NERC footnote). Do not compare across the break |
| `received_basis` | text | `pre_vat` before 2026Q1, `vat_adjusted` from 2026Q1 (NERC footnote). Received and billing efficiency shift at this break |

Not stored (derive in analysis): unbilled loss = received - billed; uncollected loss = billed - collected.

## Known properties of the source
- NERC's printed "All DisCos" received and collected totals do not always equal the sum of the 11 rows (e.g. 2026Q1 received: rows sum to 955.73, total printed 955.19; 2025Q4: 970.21 vs 969.19). `src/validate.py` reports these as warnings. Use the DisCo rows for DisCo analysis and NERC's printed totals for aggregate analysis; do not mix them in one ratio.
- Each report also restates the previous quarter. The latest published value wins and the change is logged.

## Analysis outputs (`data/processed/analysis/`)
- `leakage_by_disco.csv`: dataset plus `unbilled_ngn_bn`, `uncollected_ngn_bn`, `total_leak_ngn_bn` (received - collected), `recovery_pct` (collected / received), `unbilled_share`, `primary_leak` (billing / collection / both), `share_of_disco_leak_pct`, `rank_total_leak`. DisCo rows only.
- `national_summary.csv`: the same split from NERC's printed totals.
- `quarter_changes.csv`: change in CE, BE and ATC&C vs the previous quarter. BE and ATC&C changes are blank where a methodology break applies (`be_comparable` = False).
- `projection_next_quarter.csv`: naive (last value) and trend (last + mean of up to 3 recent changes) next-quarter collection efficiency. Trend is blank with fewer than 3 quarters. Indicative only; the back-test MAE is in `FACTS.md`.
- `FACTS.md`: numbers only, for the write-up.
