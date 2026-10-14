"""Unified ingestion engine for DisCo electricity data.

Supports:
- PDF (NERC quarterly report PDFs via pdfplumber extraction)
- CSV (tidy DisCo tables, interim tables, or custom tabular formats)
- Excel .xlsx / .xls (multi-sheet or single-sheet workbooks)
- Parquet (.parquet files)

Cleans, validates, reconciles, and computes leakage analytics.
"""
from __future__ import annotations

import io
import json
import logging
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .analyse import (
    BILLING_SHARE,
    COLLECTION_SHARE,
    add_leakage,
    add_shares,
    national_summary,
    quarter_changes,
)
from .clean import consolidate
from .extract import ExtractionError, extract_report
from .periods import (
    AGGREGATE,
    BILLING_COMMERCIAL_FROM,
    DISCOS,
    VAT_BASIS_FROM,
    canonical_disco,
    period_from_filename,
    prev_period,
    quarter_end,
)
from .validate import validate_observations

log = logging.getLogger("ingest")

COLUMN_SYNONYMS = {
    "disco": ["disco", "company", "distribution company", "name", "disco_name", "utility"],
    "period": ["period", "quarter", "qtr", "reported_period", "year_quarter"],
    "received_ngn_bn": [
        "received_ngn_bn", "received", "energy_received", "energy received",
        "energy received (n bn)", "received (ngn bn)", "received_ngn", "cur_received",
        "energy_received_ngn_bn", "cost of energy received", "received n bn"
    ],
    "billed_ngn_bn": [
        "billed_ngn_bn", "billed", "energy_billed", "energy billed",
        "energy billed (n bn)", "billed (ngn bn)", "billed_ngn", "cur_billed",
        "energy_billed_ngn_bn", "total billing", "billed n bn"
    ],
    "collected_ngn_bn": [
        "collected_ngn_bn", "collected", "revenue_collected", "collections",
        "revenue collected", "collected (n bn)", "collected (ngn bn)", "collected_ngn",
        "cur_collected", "total revenue collected", "collected n bn"
    ],
    "billing_eff_pct": [
        "billing_eff_pct", "be", "billing_efficiency", "billing efficiency",
        "billing_eff", "billing eff %", "billing efficiency (%)", "cur_be"
    ],
    "collection_eff_pct": [
        "collection_eff_pct", "ce", "collection_efficiency", "collection efficiency",
        "collection_eff", "collection eff %", "collection efficiency (%)", "cur_ce"
    ],
    "atcc_loss_pct": [
        "atcc_loss_pct", "atcc", "atcc_loss", "atc&c", "atc&c loss",
        "atcc loss %", "atc&c loss (%)", "atc&c loss %", "cur_atcc"
    ],
}


@dataclass
class ValidationIssue:
    level: str  # "error", "warning", "info"
    check: str
    where: str
    detail: str


@dataclass
class IngestResult:
    status: str  # "success", "partial", "error"
    filename: str
    format: str
    periods: list[str]
    discos_found: list[str]
    missing_discos: list[str]
    issues: list[dict[str, str]]
    disco_data: list[dict[str, Any]]
    national_data: list[dict[str, Any]]
    changes_data: list[dict[str, Any]]
    kpis: dict[str, Any]
    summary_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PRESERVED_COLUMNS = {
    "received_basis", "billing_method", "quarter_end", "atcc_target_pct",
    "reported_in", "restated", "source_page", "unbilled_ngn_bn",
    "uncollected_ngn_bn", "total_leak_ngn_bn", "unbilled_share",
    "recovery_pct", "primary_leak", "share_of_disco_leak_pct", "rank_total_leak"
}


def _normalize_col(name: str) -> str:
    raw = str(name).strip().lower()
    if raw in PRESERVED_COLUMNS:
        return raw
    cleaned = re.sub(r"[\s_/\-]+", " ", raw)
    for canonical, syns in COLUMN_SYNONYMS.items():
        if raw == canonical or cleaned == canonical:
            return canonical
        for s in syns:
            s_clean = re.sub(r"[\s_/\-]+", " ", s)
            if cleaned == s_clean or raw == s:
                return canonical
    return raw


def _clean_num(val: Any) -> float | None:
    if pd.isna(val) or val is None or val == "" or val in {"-", "--", "—", "N/A", "nan"}:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def _df_from_bytes(content: bytes, filename: str) -> pd.DataFrame | dict[str, pd.DataFrame]:
    ext = Path(filename).suffix.lower()
    bio = io.BytesIO(content)
    if ext == ".csv":
        return pd.read_csv(bio)
    if ext in {".xlsx", ".xls"}:
        excel_file = pd.ExcelFile(bio)
        if len(excel_file.sheet_names) > 1:
            sheets = {s: pd.read_excel(excel_file, s) for s in excel_file.sheet_names}
            # check if sheets match extraction names
            keys = {s.lower(): s for s in sheets}
            if "billing" in keys and "collection" in keys:
                return sheets
            return sheets[excel_file.sheet_names[0]]
        return pd.read_excel(excel_file)
    if ext == ".parquet":
        return pd.read_parquet(bio)
    raise ValueError(f"Unsupported file format: {ext}")


def ingest_pdf(content: bytes, filename: str) -> IngestResult:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / filename
        tmp_path.write_bytes(content)
        try:
            period = period_from_filename(filename)
        except ValueError:
            period = "2026Q1"

        try:
            frames = extract_report(tmp_path, Path(tmp_dir))
        except ExtractionError as e:
            return IngestResult(
                status="error",
                filename=filename,
                format="PDF",
                periods=[],
                discos_found=[],
                missing_discos=DISCOS,
                issues=[asdict(ValidationIssue("error", "extraction", filename, str(e)))],
                disco_data=[],
                national_data=[],
                changes_data=[],
                kpis={},
                summary_note=f"Extraction failed: {e}",
            )

        from .clean import _side
        b, c, a = frames["billing"], frames["collection"], frames["atcc"]
        obs_cur = _side(b, c, a, "cur", period, period)
        obs_prev = _side(b, c, a, "prev", prev_period(period), period)
        obs = pd.concat([obs_cur, obs_prev], ignore_index=True)

        disco_df, agg_df, restatements = consolidate(obs)
        raw_issues = validate_observations(obs)
        issues = [
            asdict(ValidationIssue(iss.level, iss.check, iss.where, iss.detail))
            for iss in raw_issues
        ]

        # Calculate leakage analytics
        disco_leak = add_leakage(disco_df)
        disco_leak = add_shares(disco_leak)
        nat = national_summary(agg_df)
        changes = quarter_changes(disco_leak)

        return _build_result(filename, "PDF", disco_leak, nat, changes, issues)


def ingest_tabular(df: pd.DataFrame, filename: str) -> IngestResult:
    # Rename columns to standard names
    col_map = {col: _normalize_col(col) for col in df.columns}
    work_df = df.rename(columns=col_map).copy()

    # Try to detect period
    try:
        default_period = period_from_filename(filename)
    except ValueError:
        default_period = "2026Q1"

    if "period" not in work_df.columns:
        work_df["period"] = default_period

    # Canonicalize DisCo names
    if "disco" not in work_df.columns:
        return IngestResult(
            status="error",
            filename=filename,
            format=Path(filename).suffix.upper().lstrip("."),
            periods=[],
            discos_found=[],
            missing_discos=DISCOS,
            issues=[asdict(ValidationIssue("error", "schema", filename, "No 'disco' or 'company' column identified."))],
            disco_data=[],
            national_data=[],
            changes_data=[],
            kpis={},
            summary_note="Failed to identify DisCo column in uploaded file.",
        )

    work_df["disco_clean"] = work_df["disco"].astype(str).map(canonical_disco)
    work_df = work_df[work_df["disco_clean"].notna()].copy()
    work_df["disco"] = work_df["disco_clean"]
    work_df.drop(columns=["disco_clean"], inplace=True)

    # Clean numeric fields
    num_fields = ["received_ngn_bn", "billed_ngn_bn", "collected_ngn_bn",
                  "billing_eff_pct", "collection_eff_pct", "atcc_loss_pct"]
    for f in num_fields:
        if f in work_df.columns:
            work_df[f] = work_df[f].map(_clean_num)
        else:
            work_df[f] = np.nan

    # Compute derived efficiency if missing
    if work_df["billing_eff_pct"].isna().all() and work_df["received_ngn_bn"].notna().any():
        work_df["billing_eff_pct"] = (100 * work_df["billed_ngn_bn"] / work_df["received_ngn_bn"]).round(2)
    if work_df["collection_eff_pct"].isna().all() and work_df["billed_ngn_bn"].notna().any():
        work_df["collection_eff_pct"] = (100 * work_df["collected_ngn_bn"] / work_df["billed_ngn_bn"]).round(2)
    if work_df["atcc_loss_pct"].isna().all() and work_df["billing_eff_pct"].notna().any():
        work_df["atcc_loss_pct"] = (100 * (1 - work_df["billing_eff_pct"] / 100 * work_df["collection_eff_pct"] / 100)).round(2)

    # Separate aggregate row if present
    is_agg = work_df["disco"] == AGGREGATE
    disco_rows = work_df[~is_agg].copy()
    agg_rows = work_df[is_agg].copy()

    issues: list[dict[str, str]] = []
    periods = sorted(disco_rows["period"].dropna().unique().tolist())

    if not periods:
        periods = [default_period]
        disco_rows["period"] = default_period

    # If no aggregate row provided, build aggregate from DisCo sums
    agg_frames = []
    for p in periods:
        p_d = disco_rows[disco_rows["period"] == p]
        found = p_d["disco"].tolist()
        missing = [d for d in DISCOS if d not in found]
        if missing:
            issues.append(asdict(ValidationIssue("warning", "coverage", p, f"Missing {len(missing)} DisCos: {', '.join(missing)}")))
        else:
            issues.append(asdict(ValidationIssue("info", "coverage", p, "All 11 DisCos detected.")))

        p_agg = agg_rows[agg_rows["period"] == p] if not agg_rows.empty else pd.DataFrame()
        if p_agg.empty:
            # sum DisCos
            rec = p_d["received_ngn_bn"].sum()
            bill = p_d["billed_ngn_bn"].sum()
            coll = p_d["collected_ngn_bn"].sum()
            be = (100 * bill / rec).round(2) if rec > 0 else np.nan
            ce = (100 * coll / bill).round(2) if bill > 0 else np.nan
            atcc = (100 * (1 - be / 100 * ce / 100)).round(2) if pd.notna(be) and pd.notna(ce) else np.nan
            agg_frames.append(pd.DataFrame([{
                "period": p, "received_ngn_bn": rec, "billed_ngn_bn": bill, "collected_ngn_bn": coll,
                "billing_eff_pct": be, "collection_eff_pct": ce, "atcc_loss_pct": atcc,
                "received_basis": "vat_adjusted" if p >= VAT_BASIS_FROM else "pre_vat"
            }]))
        else:
            row = p_agg.iloc[0]
            # check gap
            d_sum_bill = p_d["billed_ngn_bn"].sum()
            if abs(d_sum_bill - row["billed_ngn_bn"]) > 0.1:
                issues.append(asdict(ValidationIssue("warning", "reconciliation", p,
                                                     f"DisCos billed sum ({d_sum_bill:.2f}) differs from aggregate ({row['billed_ngn_bn']:.2f})")))
            agg_frames.append(pd.DataFrame([{
                "period": p, "received_ngn_bn": row["received_ngn_bn"], "billed_ngn_bn": row["billed_ngn_bn"],
                "collected_ngn_bn": row["collected_ngn_bn"], "billing_eff_pct": row["billing_eff_pct"],
                "collection_eff_pct": row["collection_eff_pct"], "atcc_loss_pct": row["atcc_loss_pct"],
                "received_basis": "vat_adjusted" if p >= VAT_BASIS_FROM else "pre_vat"
            }]))

    full_agg = pd.concat(agg_frames, ignore_index=True) if agg_frames else pd.DataFrame()

    # Calculate leakage and rankings
    disco_rows["received_basis"] = np.where(disco_rows["period"] >= VAT_BASIS_FROM, "vat_adjusted", "pre_vat")
    disco_rows["billing_method"] = np.where(disco_rows["period"] >= BILLING_COMMERCIAL_FROM, "commercial", "energy_based")
    disco_leak = add_leakage(disco_rows)
    disco_leak = add_shares(disco_leak)
    nat = national_summary(full_agg) if not full_agg.empty else pd.DataFrame()
    changes = quarter_changes(disco_leak) if len(periods) > 1 else pd.DataFrame()

    ext = Path(filename).suffix.upper().lstrip(".")
    return _build_result(filename, ext, disco_leak, nat, changes, issues)


def _build_result(filename: str, file_fmt: str, disco_df: pd.DataFrame,
                  nat_df: pd.DataFrame, changes_df: pd.DataFrame,
                  issues: list[dict[str, str]]) -> IngestResult:
    periods = sorted(disco_df["period"].dropna().unique().tolist())
    latest_period = periods[-1] if periods else ""
    discos_found = sorted(disco_df["disco"].dropna().unique().tolist())
    missing_discos = [d for d in DISCOS if d not in discos_found]

    # Clean records for JSON
    disco_records = json.loads(disco_df.replace({np.nan: None}).to_json(orient="records"))
    nat_records = json.loads(nat_df.replace({np.nan: None}).to_json(orient="records")) if not nat_df.empty else []
    changes_records = json.loads(changes_df.replace({np.nan: None}).to_json(orient="records")) if not changes_df.empty else []

    # KPIs for the latest period
    kpis: dict[str, Any] = {}
    if nat_records:
        latest_nat = next((r for r in reversed(nat_records) if r["period"] == latest_period), nat_records[-1])
        kpis = {
            "period": latest_period,
            "received_ngn_bn": latest_nat.get("received_ngn_bn"),
            "billed_ngn_bn": latest_nat.get("billed_ngn_bn"),
            "collected_ngn_bn": latest_nat.get("collected_ngn_bn"),
            "unbilled_ngn_bn": latest_nat.get("unbilled_ngn_bn"),
            "uncollected_ngn_bn": latest_nat.get("uncollected_ngn_bn"),
            "total_leak_ngn_bn": latest_nat.get("total_leak_ngn_bn"),
            "unbilled_share": latest_nat.get("unbilled_share"),
            "recovery_pct": latest_nat.get("recovery_pct"),
            "billing_eff_pct": latest_nat.get("billing_eff_pct"),
            "collection_eff_pct": latest_nat.get("collection_eff_pct"),
            "atcc_loss_pct": latest_nat.get("atcc_loss_pct"),
            "basis": latest_nat.get("received_basis"),
        }

    status = "error" if any(i["level"] == "error" for i in issues) else ("warning" if any(i["level"] == "warning" for i in issues) else "success")
    summary_note = f"Ingested {len(disco_df)} rows across {len(periods)} quarter(s) ({', '.join(periods)})."

    return IngestResult(
        status=status,
        filename=filename,
        format=file_fmt,
        periods=periods,
        discos_found=discos_found,
        missing_discos=missing_discos,
        issues=issues,
        disco_data=disco_records,
        national_data=nat_records,
        changes_data=changes_records,
        kpis=kpis,
        summary_note=summary_note,
    )


def ingest_file(content: bytes, filename: str) -> IngestResult:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return ingest_pdf(content, filename)
    elif ext in {".csv", ".xlsx", ".xls", ".parquet"}:
        parsed = _df_from_bytes(content, filename)
        if isinstance(parsed, dict):
            # multi-sheet excel
            # combine if possible or parse primary
            if "billing" in parsed and "collection" in parsed:
                # let's construct observations
                from .clean import _side
                period = "2026Q1"
                try:
                    period = period_from_filename(filename)
                except ValueError:
                    pass
                b, c = parsed["billing"], parsed["collection"]
                a = parsed.get("atcc", pd.DataFrame())
                obs = _side(b, c, a, "cur", period, period)
                return ingest_tabular(obs, filename)
            # fallback to first sheet
            first_key = list(parsed.keys())[0]
            return ingest_tabular(parsed[first_key], filename)
        else:
            return ingest_tabular(parsed, filename)
    else:
        return IngestResult(
            status="error",
            filename=filename,
            format=ext,
            periods=[],
            discos_found=[],
            missing_discos=DISCOS,
            issues=[{"level": "error", "check": "format", "where": filename, "detail": f"Unsupported file extension: {ext}"}],
            disco_data=[],
            national_data=[],
            changes_data=[],
            kpis={},
            summary_note=f"Unsupported format '{ext}'. Upload a PDF, CSV, Excel (.xlsx/.xls), or Parquet file.",
        )
