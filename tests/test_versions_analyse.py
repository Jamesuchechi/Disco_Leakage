import json

import numpy as np
import pandas as pd
import pytest

from src.analyse import (add_leakage, add_shares, national_summary, projection, quarter_changes)
from src.clean import build_observations, consolidate
from src.extract import extract_report
from src.versions import build_versions
from tests.golden import T6, T8, T9
from tests.make_pdf import make_report_pdf


@pytest.fixture()
def interim(tmp_path):
    extract_report(make_report_pdf(tmp_path / "2026_Q1.pdf", T6, T8, T9), tmp_path / "interim")
    return tmp_path / "interim"


@pytest.fixture()
def datasets(interim):
    disco, agg, _ = consolidate(build_observations(interim))
    return add_shares(add_leakage(disco)), agg


def test_leak_split_matches_hand_calculation(datasets):
    leak, _ = datasets
    r = leak[(leak["period"] == "2026Q1") & (leak["disco"] == "Kano")].iloc[0]
    assert r["unbilled_ngn_bn"] == pytest.approx(48.02 - 42.02)      # received - billed
    assert r["uncollected_ngn_bn"] == pytest.approx(42.02 - 26.37)   # billed - collected
    assert r["primary_leak"] == "collection"


def test_classification_examples(datasets):
    leak, _ = datasets
    q1 = leak[leak["period"] == "2026Q1"].set_index("disco")["primary_leak"]
    assert q1["Benin"] == "billing" and q1["Ikeja"] == "billing" and q1["Kano"] == "collection"
    assert q1["Abuja"] == "both"


def test_shares_sum_to_100_and_rank_is_unique_top(datasets):
    leak, _ = datasets
    q1 = leak[leak["period"] == "2026Q1"]
    assert q1["share_of_disco_leak_pct"].sum() == pytest.approx(100)
    assert q1.loc[q1["rank_total_leak"] == 1, "disco"].iloc[0] == "Ibadan"  # largest received-minus-collected gap


def test_national_uses_printed_totals_not_row_sums(datasets):
    _, agg = datasets
    n = national_summary(agg).set_index("period").loc["2026Q1"]
    assert n["unbilled_ngn_bn"] == pytest.approx(955.19 - 756.93)
    assert n["uncollected_ngn_bn"] == pytest.approx(756.93 - 597.56)


def test_methodology_break_hides_be_change_but_keeps_collection_change(datasets):
    leak, _ = datasets
    q = quarter_changes(leak)
    row = q[(q["period"] == "2026Q1") & (q["disco"] == "Eko")].iloc[0]
    assert row["consecutive"] and not row["be_comparable"]          # VAT basis starts in 2026Q1
    assert np.isnan(row["be_change_pp"]) and np.isnan(row["atcc_change_pp"])
    assert row["ce_change_pp"] == pytest.approx(89.64 - 90.34)


def test_projection_refuses_to_trend_on_two_quarters(datasets):
    leak, _ = datasets
    proj, bt = projection(leak)
    assert proj["ce_next_trend_pct"].isna().all() and bt["n_predictions"] == 0
    assert proj.set_index("disco").loc["Jos", "ce_next_naive_pct"] == pytest.approx(58.41)


def test_projection_trend_and_backtest_with_longer_history():
    rows = [{"period": f"2025Q{q}" if q < 5 else "2026Q1", "disco": "X", "collection_eff_pct": v, "billing_method": "commercial"}
            for q, v in zip([1, 2, 3, 4, 5], [70.0, 72.0, 74.0, 76.0, 78.0])]
    proj, bt = projection(pd.DataFrame(rows))
    assert proj["ce_next_trend_pct"].iloc[0] == pytest.approx(80.0)
    assert bt["n_predictions"] == 2 and bt["mae_trend_pp"] == pytest.approx(0.0)
    assert bt["mae_naive_pp"] == pytest.approx(2.0)


def test_versions_show_added_quarters_and_restatements(tmp_path, interim):
    t6q2 = {k: (v[3], v[4], v[5], v[3], v[4], v[5]) for k, v in T6.items()}
    t6q2["Ibadan"] = (113.13, 77.82, 68.79, 113.13, 77.82, 68.79)
    t8q2 = {k: (v[3], v[4], v[5], v[3], v[4], v[5]) for k, v in T8.items()}
    t9q2 = {k: (v[0], v[2], v[2], v[4], v[4], v[5]) for k, v in T9.items()}
    extract_report(make_report_pdf(tmp_path / "2026_Q2.pdf", t6q2, t8q2, t9q2), interim)
    manifest = build_versions(interim, tmp_path / "versions")
    assert [m["version"] for m in manifest] == [1, 2]
    assert manifest[0]["quarters"] == ["2025Q4", "2026Q1"] and manifest[0]["restated_rows"] == 0
    assert manifest[1]["added_quarters"] == ["2026Q2"] and manifest[1]["restated_rows"] == 1
    assert "restated" in manifest[1]["commit_message"]
    assert json.loads((tmp_path / "versions" / "manifest.json").read_text())[1]["rows"] == 33


def test_dashboard_builds_with_embedded_data(tmp_path, datasets):
    import json as _json
    from src.analyse import main as analyse_main
    from src.build_dashboard import build
    leak, agg = datasets
    proc = tmp_path / "processed"
    proc.mkdir()
    leak.drop(columns=["unbilled_ngn_bn", "uncollected_ngn_bn", "total_leak_ngn_bn", "recovery_pct", "unbilled_share",
                       "primary_leak", "share_of_disco_leak_pct", "rank_total_leak"]).to_csv(proc / "disco_quarterly.csv", index=False)
    agg.to_csv(proc / "aggregate_quarterly.csv", index=False)
    analyse_main(str(proc))
    out = build(str(proc), "dashboard/template.html", str(tmp_path / "index.html"))
    html = out.read_text()
    blob = html.split('type="application/json">')[1].split("</script>")[0]
    data = _json.loads(blob.replace("<\\/", "</"))
    assert len(data["disco"]) == 22 and len(data["national"]) == 2
    assert "/*DATA*/" not in html
