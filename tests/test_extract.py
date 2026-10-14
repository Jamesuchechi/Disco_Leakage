import pytest

from src.extract import ExtractionError, SPECS, extract_report
from tests.golden import T6, T8, T9
from tests.make_pdf import make_report_pdf

COLS = {s.name: s.columns for s in SPECS}


def _check(frames, name, golden):
    df = frames[name].set_index("disco")
    for disco, vals in golden.items():
        assert list(df.loc[disco, list(COLS[name])]) == pytest.approx(list(vals)), (name, disco)


def test_extracts_all_three_tables_exactly(tmp_path):
    pdf = make_report_pdf(tmp_path / "2026_Q1.pdf", T6, T8, T9)
    frames = extract_report(pdf, tmp_path / "interim")
    _check(frames, "billing", T6)
    _check(frames, "collection", T8)
    _check(frames, "atcc", T9)
    assert len(frames["billing"]) == 12 and len(frames["atcc"]) == 11


def test_ignores_table_of_contents_and_reports_true_page(tmp_path):
    frames = extract_report(make_report_pdf(tmp_path / "2026_Q1.pdf", T6, T8, T9), tmp_path / "i")
    assert set(frames["billing"]["source_page"]) == {3}
    assert set(frames["collection"]["source_page"]) == {4}


def test_stops_before_the_next_table_that_repeats_disco_names(tmp_path):
    frames = extract_report(make_report_pdf(tmp_path / "2026_Q1.pdf", T6, T8, T9), tmp_path / "i")
    abuja = frames["billing"].set_index("disco").loc["Abuja"]
    assert abuja["cur_be"] == 84.16  # not Table 7's 84.16/78.38 row, and not overwritten by it


def test_missing_row_fails_loudly(tmp_path):
    pdf = make_report_pdf(tmp_path / "2026_Q1.pdf", T6, T8, T9, drop={"billing": "Kano"})
    with pytest.raises(ExtractionError, match="Kano"):
        extract_report(pdf, tmp_path / "i")
