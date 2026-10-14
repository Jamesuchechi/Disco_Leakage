import copy

import pandas as pd
import pytest

from src.clean import build_observations, consolidate
from src.extract import extract_report
from src.validate import validate_final, validate_observations
from tests.golden import T6, T8, T9
from tests.make_pdf import make_report_pdf


@pytest.fixture()
def interim(tmp_path):
    extract_report(make_report_pdf(tmp_path / "2026_Q1.pdf", T6, T8, T9), tmp_path / "interim")
    return tmp_path / "interim"


def test_golden_values_pass_every_reconciliation_check(interim):
    obs = build_observations(interim)
    disco, agg, _ = consolidate(obs)
    issues = validate_observations(obs) + validate_final(disco)
    assert [i for i in issues if i.level == "error"] == []
    assert len(disco) == 22 and set(disco["period"]) == {"2025Q4", "2026Q1"}


def test_known_source_inconsistency_is_surfaced_as_a_warning(interim):
    # In NERC's Q1 2026 report the 11 DisCos' "received" values sum to 955.73, but the printed total is 955.19.
    warns = [i for i in validate_observations(build_observations(interim)) if i.level == "warn"]
    assert any("received_ngn_bn" in i.detail and "955.73" in i.detail for i in warns)
    # likewise 2025/Q4 collected: rows sum to 630.85, printed total is 630.93
    assert any("collected_ngn_bn" in i.detail and "630.85" in i.detail for i in warns)


def test_aggregate_atcc_is_derived_from_identity(interim):
    _, agg, _ = consolidate(build_observations(interim))
    q1 = agg[agg["period"] == "2026Q1"].iloc[0]
    assert q1["atcc_loss_pct"] == pytest.approx(37.44, abs=0.01)  # NERC reports 37.44%
    assert bool(q1["atcc_derived"])


def test_methodology_flags(interim):
    disco, _, _ = consolidate(build_observations(interim))
    assert set(disco.loc[disco["period"] == "2026Q1", "received_basis"]) == {"vat_adjusted"}
    assert set(disco.loc[disco["period"] == "2025Q4", "received_basis"]) == {"pre_vat"}
    assert set(disco["billing_method"]) == {"commercial"}


def test_a_bad_number_is_caught(tmp_path):
    t6 = copy.deepcopy(T6)
    t6["Eko"] = (130.89, 124.32, 94.98, 130.06, 115.73, 98.98)  # published BE mistyped
    extract_report(make_report_pdf(tmp_path / "2026_Q1.pdf", t6, T8, T9), tmp_path / "i")
    errors = [i for i in validate_observations(build_observations(tmp_path / "i")) if i.level == "error"]
    assert any(i.check == "billing_identity" and "Eko" in i.where for i in errors)


def test_restatement_between_reports_is_logged_and_latest_wins(tmp_path):
    interim = tmp_path / "interim"
    extract_report(make_report_pdf(tmp_path / "2026_Q1.pdf", T6, T8, T9), interim)
    # A later report restates Ibadan's 2026Q1 received value (its "previous quarter" columns).
    t6q2 = {k: (v[3], v[4], v[5], v[3], v[4], v[5]) for k, v in T6.items()}
    t6q2["Ibadan"] = (113.13, 77.82, 68.79, 113.13, 77.82, 68.79)
    t8q2 = {k: (v[3], v[4], v[5], v[3], v[4], v[5]) for k, v in T8.items()}
    t9q2 = {k: (v[0], v[2], v[2], v[4], v[4], v[5]) for k, v in T9.items()}
    extract_report(make_report_pdf(tmp_path / "2026_Q2.pdf", t6q2, t8q2, t9q2), interim)
    disco, _, restatements = consolidate(build_observations(interim))
    row = disco[(disco["period"] == "2026Q1") & (disco["disco"] == "Ibadan")].iloc[0]
    assert row["received_ngn_bn"] == 113.13 and row["reported_in"] == "2026Q2" and bool(row["restated"])
    assert (restatements["field"] == "received_ngn_bn").any()
    assert not disco[(disco["period"] == "2026Q1") & (disco["disco"] == "Abuja")].iloc[0]["restated"]
