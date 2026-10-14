"""Runs only when the real NERC Q1 2026 PDF is present at data/raw/2026_Q1.pdf (run scripts/fetch_reports.py)."""
from pathlib import Path

import pytest

from src.extract import SPECS, extract_report
from src.validate import validate_observations
from src.clean import build_observations
from tests.golden import T6, T8, T9

PDF = Path("data/raw/2026_Q1.pdf")
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="real NERC PDF not downloaded")


def test_real_q1_2026_matches_transcribed_tables(tmp_path):
    frames = extract_report(PDF, tmp_path)
    cols = {s.name: s.columns for s in SPECS}
    for name, golden in (("billing", T6), ("collection", T8), ("atcc", T9)):
        df = frames[name].set_index("disco")
        for disco, vals in golden.items():
            assert list(df.loc[disco, list(cols[name])]) == pytest.approx(list(vals)), (name, disco)


def test_real_q1_2026_has_no_validation_errors(tmp_path):
    extract_report(PDF, tmp_path)
    errors = [i for i in validate_observations(build_observations(tmp_path)) if i.level == "error"]
    assert errors == []
