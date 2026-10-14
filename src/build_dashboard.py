"""Fill dashboard/template.html with the analysis outputs -> docs/index.html (static; works on GitHub Pages)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.replace({np.nan: None}).to_json(orient="records"))


def build(processed: str = "data/processed", template: str = "dashboard/template.html",
          out: str = "docs/index.html", note: str = "") -> Path:
    a = Path(processed) / "analysis"
    leak = pd.read_csv(a / "leakage_by_disco.csv")
    nat = pd.read_csv(a / "national_summary.csv")
    qoq = pd.read_csv(a / "quarter_changes.csv")
    data = {
        "note": note or f"Based on {leak['period'].nunique()} quarter(s) of NERC data ({leak['period'].min()} to {leak['period'].max()}).",
        "disco": _records(leak.rename(columns={
            "received_ngn_bn": "received", "billed_ngn_bn": "billed", "collected_ngn_bn": "collected",
            "billing_eff_pct": "be", "collection_eff_pct": "ce", "atcc_loss_pct": "atcc",
            "unbilled_ngn_bn": "unbilled", "uncollected_ngn_bn": "uncollected", "total_leak_ngn_bn": "leak",
            "primary_leak": "primary"})[["period", "disco", "received", "billed", "collected", "be", "ce", "atcc",
                                         "unbilled", "uncollected", "leak", "unbilled_share", "primary"]]),
        "national": _records(nat.rename(columns={
            "received_ngn_bn": "received", "billed_ngn_bn": "billed", "collected_ngn_bn": "collected",
            "unbilled_ngn_bn": "unbilled", "uncollected_ngn_bn": "uncollected", "billing_eff_pct": "be",
            "collection_eff_pct": "ce", "atcc_loss_pct": "atcc", "received_basis": "basis"})),
        "changes": _records(qoq.rename(columns={"ce_change_pp": "ce_change", "atcc_change_pp": "atcc_change"})),
    }
    html = Path(template).read_text().replace("/*DATA*/", json.dumps(data).replace("</", "<\\/"))
    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html)
    return dest


def main() -> int:
    print(f"wrote {build()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
