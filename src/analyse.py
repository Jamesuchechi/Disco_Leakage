"""Phase 4: where does the money leak, and who is improving?

Definitions follow PRODUCT.md. DisCo-level analysis uses the DisCo rows; national analysis uses
NERC's printed totals. The two are never mixed in one ratio.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .periods import prev_period

BILLING_SHARE = 0.60     # unbilled share of total leak at or above this -> "billing"
COLLECTION_SHARE = 0.40  # at or below this -> "collection"; in between -> "both"


def add_leakage(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["unbilled_ngn_bn"] = d["received_ngn_bn"] - d["billed_ngn_bn"]
    d["uncollected_ngn_bn"] = d["billed_ngn_bn"] - d["collected_ngn_bn"]
    d["total_leak_ngn_bn"] = d["received_ngn_bn"] - d["collected_ngn_bn"]
    d["recovery_pct"] = 100 * d["collected_ngn_bn"] / d["received_ngn_bn"]
    share = d["unbilled_ngn_bn"] / d["total_leak_ngn_bn"].where(d["total_leak_ngn_bn"] > 0)
    d["unbilled_share"] = share
    d["primary_leak"] = np.select([share >= BILLING_SHARE, share <= COLLECTION_SHARE],
                                  ["billing", "collection"], default="both")
    d.loc[share.isna(), "primary_leak"] = "n/a"
    return d


def national_summary(agg: pd.DataFrame) -> pd.DataFrame:
    """From NERC's printed totals (not the DisCo rows)."""
    d = add_leakage(agg)
    return d[["period", "received_ngn_bn", "billed_ngn_bn", "collected_ngn_bn", "unbilled_ngn_bn",
              "uncollected_ngn_bn", "total_leak_ngn_bn", "unbilled_share", "recovery_pct",
              "billing_eff_pct", "collection_eff_pct", "atcc_loss_pct", "received_basis"]]


def add_shares(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["share_of_disco_leak_pct"] = 100 * d["total_leak_ngn_bn"] / d.groupby("period")["total_leak_ngn_bn"].transform("sum")
    d["rank_total_leak"] = d.groupby("period")["total_leak_ngn_bn"].rank(ascending=False, method="min").astype(int)
    return d


def quarter_changes(d: pd.DataFrame) -> pd.DataFrame:
    """Quarter-over-quarter changes, with an honest flag for methodology breaks."""
    d = d.sort_values(["disco", "period"]).copy()
    g = d.groupby("disco")
    for col in ("period", "billing_eff_pct", "collection_eff_pct", "atcc_loss_pct", "billing_method", "received_basis"):
        d[f"prev_{col}"] = g[col].shift(1)
    d = d[d["prev_period"].notna()].copy()
    d["consecutive"] = [prev_period(p) == q for p, q in zip(d["period"], d["prev_period"])]
    d["ce_change_pp"] = d["collection_eff_pct"] - d["prev_collection_eff_pct"]
    d["be_change_pp"] = d["billing_eff_pct"] - d["prev_billing_eff_pct"]
    d["atcc_change_pp"] = d["atcc_loss_pct"] - d["prev_atcc_loss_pct"]
    # Collected and billed are real money, so CE is comparable across the VAT break. BE and ATC&C are not.
    d["be_comparable"] = d["consecutive"] & (d["billing_method"] == d["prev_billing_method"]) & (d["received_basis"] == d["prev_received_basis"])
    d.loc[~d["be_comparable"], ["be_change_pp", "atcc_change_pp"]] = np.nan
    d.loc[~d["consecutive"], "ce_change_pp"] = np.nan
    keep = ["period", "prev_period", "disco", "ce_change_pp", "be_change_pp", "atcc_change_pp", "be_comparable", "consecutive"]
    return d[keep].sort_values(["period", "disco"]).reset_index(drop=True)


def _next_quarter(series: np.ndarray) -> tuple[float, float]:
    """(naive, trend) forecast of the next value. Trend = last + mean of up to the last 3 changes."""
    naive = float(series[-1])
    if len(series) < 3:
        return naive, float("nan")
    step = float(np.mean(np.diff(series)[-3:]))
    return naive, float(np.clip(naive + step, 0, 100))


def projection(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Next-quarter collection efficiency per DisCo, plus an honest back-test. Indicative only."""
    rows, errs_naive, errs_trend = [], [], []
    d = d[d["billing_method"] == "commercial"]
    for disco, g in d.sort_values("period").groupby("disco"):
        s = g["collection_eff_pct"].to_numpy(float)
        naive, trend = _next_quarter(s)
        rows.append({"disco": disco, "last_period": g["period"].iloc[-1], "quarters_used": len(s),
                     "ce_last_pct": s[-1], "ce_next_naive_pct": naive, "ce_next_trend_pct": trend})
        for i in range(3, len(s)):  # back-test: predict s[i] from s[:i]
            n, t = _next_quarter(s[:i])
            errs_naive.append(abs(n - s[i]))
            errs_trend.append(abs(t - s[i]))
    bt = {"n_predictions": len(errs_naive),
          "mae_naive_pp": float(np.mean(errs_naive)) if errs_naive else float("nan"),
          "mae_trend_pp": float(np.mean(errs_trend)) if errs_trend else float("nan")}
    return pd.DataFrame(rows), bt


def facts_markdown(leak: pd.DataFrame, nat: pd.DataFrame, bt: dict) -> str:
    latest = leak["period"].max()
    cur = leak[leak["period"] == latest].sort_values("total_leak_ngn_bn", ascending=False)
    n = nat[nat["period"] == latest].iloc[0]
    out = [f"# Facts sheet: {latest}\n",
           "Generated by `src/analyse.py`. Numbers only; interpretation belongs in the write-up.\n",
           f"**National (NERC printed totals):** received N{n.received_ngn_bn:.2f}bn, billed N{n.billed_ngn_bn:.2f}bn, "
           f"collected N{n.collected_ngn_bn:.2f}bn. Unbilled N{n.unbilled_ngn_bn:.2f}bn ({100 * n.unbilled_share:.0f}% of the leak), "
           f"uncollected N{n.uncollected_ngn_bn:.2f}bn. ATC&C {n.atcc_loss_pct:.2f}%.\n",
           "| DisCo | Leak (N bn) | Share of DisCo leak | Unbilled share | Primary leak | CE % | BE % |",
           "|---|---:|---:|---:|---|---:|---:|"]
    for r in cur.itertuples():
        out.append(f"| {r.disco} | {r.total_leak_ngn_bn:.2f} | {r.share_of_disco_leak_pct:.1f}% | {100 * r.unbilled_share:.0f}% | "
                   f"{r.primary_leak} | {r.collection_eff_pct:.2f} | {r.billing_eff_pct:.2f} |")
    out.append(f"\nQuarters in dataset: {leak['period'].nunique()}. Projection back-test: {bt['n_predictions']} prediction(s); "
               f"naive MAE {bt['mae_naive_pp']:.2f}pp, trend MAE {bt['mae_trend_pp']:.2f}pp (NaN means too little history).")
    return "\n".join(out) + "\n"


def main(processed: str = "data/processed") -> int:
    p = Path(processed)
    disco = pd.read_csv(p / "disco_quarterly.csv")
    agg = pd.read_csv(p / "aggregate_quarterly.csv")
    leak = add_shares(add_leakage(disco))
    nat = national_summary(agg)
    qoq = quarter_changes(leak)
    proj, bt = projection(leak)
    out = p / "analysis"
    out.mkdir(exist_ok=True)
    leak.to_csv(out / "leakage_by_disco.csv", index=False)
    nat.to_csv(out / "national_summary.csv", index=False)
    qoq.to_csv(out / "quarter_changes.csv", index=False)
    proj.to_csv(out / "projection_next_quarter.csv", index=False)
    (out / "FACTS.md").write_text(facts_markdown(leak, nat, bt))
    print((out / "FACTS.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
