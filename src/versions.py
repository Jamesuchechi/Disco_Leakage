"""Phase 3: build one dataset snapshot per NERC report, so Strata can diff them.

Version N is the dataset exactly as it would have looked using only reports 1..N. Each new report
therefore adds a quarter and may restate the previous one, which is what the diff view should show.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from .clean import VALUE_TOL, build_observations, consolidate

KEY = ["period", "disco"]


def _changed_rows(prev: pd.DataFrame, cur: pd.DataFrame) -> int:
    m = prev.merge(cur, on=KEY, suffixes=("_p", "_c"))
    changed = pd.Series(False, index=m.index)
    for col, tol in VALUE_TOL.items():
        if f"{col}_p" not in m or f"{col}_c" not in m:
            continue  # columns not kept in the published dataset (e.g. the collection table's copy of billed)
        changed |= (m[f"{col}_p"] - m[f"{col}_c"]).abs() > tol
    return int(changed.sum())


def build_versions(interim_dir: str | Path = "data/interim", out_dir: str | Path = "data/versions") -> list[dict]:
    obs = build_observations(interim_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    prev: pd.DataFrame | None = None
    for n, report in enumerate(sorted(obs["reported_in"].unique()), start=1):
        snapshot, _, _ = consolidate(obs[obs["reported_in"] <= report])
        path = out / f"v{n:02d}_{report}.csv"
        snapshot.to_csv(path, index=False)
        periods = sorted(snapshot["period"].unique())
        added = sorted(set(periods) - set(prev["period"].unique())) if prev is not None else periods
        restated = _changed_rows(prev, snapshot) if prev is not None else 0
        message = f"{report}: add {', '.join(added) if added else 'no new quarters'}"
        if restated:
            message += f"; {restated} DisCo-quarter row(s) restated"
        manifest.append({"version": n, "report": report, "file": path.name, "rows": len(snapshot),
                         "quarters": periods, "added_quarters": added, "restated_rows": restated,
                         "commit_message": message})
        prev = snapshot
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    manifest = build_versions()
    for m in manifest:
        print(f"v{m['version']:02d}  {m['file']:<22} {m['rows']:>3} rows  | {m['commit_message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
