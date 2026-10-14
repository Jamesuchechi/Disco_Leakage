"""Phase 2: interim CSVs -> one tidy DisCo x quarter dataset.

Each NERC report carries two quarters (current and previous). Every value is kept as an
"observation" tagged with the report it came from. The final dataset uses the latest report
that published each quarter, and any change between reports is logged as a restatement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .periods import (
    AGGREGATE, BILLING_COMMERCIAL_FROM, VAT_BASIS_FROM, prev_period, quarter_end,
)

VALUE_TOL = {
    "received_ngn_bn": 0.005, "billed_ngn_bn": 0.005,
    "collection_billed_ngn_bn": 0.005, "collected_ngn_bn": 0.005,
    "billing_eff_pct": 0.01, "collection_eff_pct": 0.01,
    "atcc_loss_pct": 0.01, "atcc_target_pct": 0.01,
}


def _side(b, c, a, side: str, period: str, reported_in: str) -> pd.DataFrame:
    df = b[["disco", f"{side}_received", f"{side}_billed", f"{side}_be"]].rename(columns={
        f"{side}_received": "received_ngn_bn", f"{side}_billed": "billed_ngn_bn",
        f"{side}_be": "billing_eff_pct"})
    df = df.merge(
        c[["disco", f"{side}_billings", f"{side}_collected", f"{side}_ce"]].rename(columns={
            f"{side}_billings": "collection_billed_ngn_bn", f"{side}_collected": "collected_ngn_bn",
            f"{side}_ce": "collection_eff_pct"}),
        on="disco", how="outer")
    if side == "cur":
        atcc = a[["disco", "cur_atcc", "target"]].rename(
            columns={"cur_atcc": "atcc_loss_pct", "target": "atcc_target_pct"})
    else:  # the previous quarter's target is not printed; target = actual + (target - actual) variance
        atcc = a[["disco", "prev_atcc", "prev_variance"]].copy()
        atcc["atcc_target_pct"] = (atcc["prev_atcc"] + atcc["prev_variance"]).round(2)
        atcc = atcc.rename(columns={"prev_atcc": "atcc_loss_pct"})[["disco", "atcc_loss_pct", "atcc_target_pct"]]
    df = df.merge(atcc, on="disco", how="left")
    df.insert(0, "period", period)
    df.insert(0, "reported_in", reported_in)
    df["is_aggregate"] = df["disco"] == AGGREGATE
    return df


def build_observations(interim_dir: str | Path) -> pd.DataFrame:
    interim = Path(interim_dir)
    reports = sorted({p.name.split("_")[0] for p in interim.glob("*_billing.csv")})
    if not reports:
        raise FileNotFoundError(f"no extracted tables in {interim}; run `python -m src.extract` first")
    frames = []
    for rp in reports:
        b, c, a = (pd.read_csv(interim / f"{rp}_{n}.csv") for n in ("billing", "collection", "atcc"))
        frames.append(_side(b, c, a, "cur", rp, rp))
        frames.append(_side(b, c, a, "prev", prev_period(rp), rp))
    return pd.concat(frames, ignore_index=True)


def consolidate(obs: pd.DataFrame):
    """Return (disco_df, aggregate_df, restatements_df)."""
    obs = obs.sort_values(["period", "disco", "reported_in"]).reset_index(drop=True)
    changes, restated = [], set()
    for (period, disco), g in obs.groupby(["period", "disco"]):
        rows = g.to_dict("records")
        for old, new in zip(rows, rows[1:]):
            for field, tol in VALUE_TOL.items():
                o, n = old[field], new[field]
                if pd.notna(o) and pd.notna(n) and abs(o - n) > tol:
                    restated.add((period, disco))
                    changes.append({"period": period, "disco": disco, "field": field,
                                    "old_value": o, "old_reported_in": old["reported_in"],
                                    "new_value": n, "new_reported_in": new["reported_in"]})
    latest = obs.groupby(["period", "disco"], as_index=False).tail(1).copy()
    latest["restated"] = [(p, d) in restated for p, d in zip(latest["period"], latest["disco"])]
    latest["billing_method"] = np.where(latest["period"] >= BILLING_COMMERCIAL_FROM, "commercial", "energy_based")
    latest["received_basis"] = np.where(latest["period"] >= VAT_BASIS_FROM, "vat_adjusted", "pre_vat")
    latest["quarter_end"] = [quarter_end(p) for p in latest["period"]]
    # NERC does not print an aggregate ATC&C row in its DisCo table; derive it from the identity.
    agg = latest["is_aggregate"] & latest["atcc_loss_pct"].isna()
    latest.loc[agg, "atcc_loss_pct"] = (
        100 * (1 - latest.loc[agg, "billing_eff_pct"] / 100 * latest.loc[agg, "collection_eff_pct"] / 100)
    ).round(2)
    latest["atcc_derived"] = agg
    cols = ["period", "quarter_end", "disco", "received_ngn_bn", "billed_ngn_bn", "collected_ngn_bn",
            "billing_eff_pct", "collection_eff_pct", "atcc_loss_pct", "atcc_target_pct",
            "reported_in", "restated", "billing_method", "received_basis"]
    disco_df = latest[~latest["is_aggregate"]][cols].sort_values(["period", "disco"]).reset_index(drop=True)
    agg_df = latest[latest["is_aggregate"]][cols + ["atcc_derived"]].sort_values("period").reset_index(drop=True)
    agg_df = agg_df.drop(columns=["disco"])
    return disco_df, agg_df, pd.DataFrame(changes)


def main(interim_dir: str = "data/interim", out_dir: str = "data/processed") -> int:
    obs = build_observations(interim_dir)
    disco_df, agg_df, restatements = consolidate(obs)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    disco_df.to_parquet(out / "disco_quarterly.parquet", index=False)
    disco_df.to_csv(out / "disco_quarterly.csv", index=False)
    agg_df.to_csv(out / "aggregate_quarterly.csv", index=False)
    restatements.to_csv(out / "restatements.csv", index=False)
    print(f"{len(disco_df)} DisCo rows across {disco_df['period'].nunique()} quarters; "
          f"{len(restatements)} restated values logged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
