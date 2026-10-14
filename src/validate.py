"""Phase 2 gate: reconcile every extracted number against NERC's own published totals.

Errors block the pipeline. Warnings are known properties of the source that must be
mentioned in the write-up. A value that fails is resolved against the PDF, never patched in code.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import pandas as pd

from .clean import build_observations, consolidate
from .periods import DISCOS

R = 0.005  # NERC prints naira billions to 2 decimals, so each value can be off by 0.005


@dataclass(frozen=True)
class Issue:
    level: str  # "error" | "warn"
    check: str
    where: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.check} @ {self.where}: {self.detail}"


def _pct_tol(num: float, den: float) -> float:
    """Rounding-aware tolerance (percentage points) for 100*num/den from 2-decimal inputs."""
    return 100 * (R / den + R * num / den**2) + 0.006


def validate_observations(obs: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    for (rep, period), g in obs.groupby(["reported_in", "period"]):
        where = f"{period} (from {rep})"
        d = g[~g["is_aggregate"]].set_index("disco")
        a = g[g["is_aggregate"]]
        missing = [x for x in DISCOS if x not in d.index]
        if missing or len(a) != 1:
            issues.append(Issue("error", "coverage", where, f"missing {missing}, aggregate rows={len(a)}"))
            continue
        a = a.iloc[0]
        gap = abs(d["billed_ngn_bn"].sum() - a["billed_ngn_bn"])
        if gap > 0.06:
            issues.append(Issue("error", "aggregate_sum", where,
                                f"billed_ngn_bn: DisCos sum to {d['billed_ngn_bn'].sum():.2f} vs total {a['billed_ngn_bn']:.2f}"))
        # NERC's printed totals for "received" and "collected" do not always equal the sum of the DisCo rows.
        # Small gaps are a documented property of the source (warn); large ones mean a bad extraction (error).
        for col in ("received_ngn_bn", "collected_ngn_bn"):
            gap = abs(d[col].sum() - a[col])
            if gap > 0.06:
                lvl = "error" if gap > 0.0025 * a[col] else "warn"
                issues.append(Issue(lvl, "aggregate_sum", where,
                                    f"{col}: DisCos sum to {d[col].sum():.2f} but NERC's total is {a[col]:.2f} (gap {gap:.2f})"))
        for name, row in list(d.iterrows()) + [("All DisCos", a)]:
            w = f"{where} / {name}"
            be = 100 * row["billed_ngn_bn"] / row["received_ngn_bn"]
            if abs(be - row["billing_eff_pct"]) > _pct_tol(row["billed_ngn_bn"], row["received_ngn_bn"]):
                issues.append(Issue("error", "billing_identity", w, f"billed/received={be:.2f} vs published {row['billing_eff_pct']}"))
            ce = 100 * row["collected_ngn_bn"] / row["collection_billed_ngn_bn"]
            if abs(ce - row["collection_eff_pct"]) > _pct_tol(row["collected_ngn_bn"], row["collection_billed_ngn_bn"]):
                issues.append(Issue("error", "collection_identity", w, f"collected/billed={ce:.2f} vs published {row['collection_eff_pct']}"))
            if abs(row["billed_ngn_bn"] - row["collection_billed_ngn_bn"]) > 0.011:
                issues.append(Issue("error", "billed_matches", w, f"{row['billed_ngn_bn']} vs {row['collection_billed_ngn_bn']}"))
            if pd.notna(row["atcc_loss_pct"]):
                atcc = 100 * (1 - row["billing_eff_pct"] / 100 * row["collection_eff_pct"] / 100)
                if abs(atcc - row["atcc_loss_pct"]) > 0.1:
                    issues.append(Issue("error", "atcc_identity", w, f"1-BE*CE={atcc:.2f} vs published {row['atcc_loss_pct']}"))
    return issues


def validate_final(disco_df: pd.DataFrame) -> list[Issue]:
    issues: list[Issue] = []
    if disco_df.duplicated(["period", "disco"]).any():
        issues.append(Issue("error", "unique_key", "final", "duplicate (period, disco) rows"))
    for period, g in disco_df.groupby("period"):
        if len(g) != len(DISCOS):
            issues.append(Issue("error", "coverage", period, f"{len(g)} DisCo rows, expected {len(DISCOS)}"))
    core = ["received_ngn_bn", "billed_ngn_bn", "collected_ngn_bn", "billing_eff_pct", "collection_eff_pct", "atcc_loss_pct"]
    nulls = disco_df[core].isna().sum()
    for col, n in nulls[nulls > 0].items():
        issues.append(Issue("error", "nulls", "final", f"{n} missing values in {col}"))
    return issues


def main(interim_dir: str = "data/interim") -> int:
    obs = build_observations(interim_dir)
    disco_df, _, _ = consolidate(obs)
    issues = validate_observations(obs) + validate_final(disco_df)
    for i in issues:
        print(i)
    errors = [i for i in issues if i.level == "error"]
    print(f"\n{len(errors)} error(s), {len(issues) - len(errors)} warning(s) across "
          f"{obs.groupby(['reported_in', 'period']).ngroups} report-quarter checks.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
