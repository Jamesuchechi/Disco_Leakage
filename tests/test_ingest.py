"""Tests for src.ingest across PDF, CSV, Excel, and Parquet."""
import io
from pathlib import Path
import pandas as pd
import pytest
from src.ingest import ingest_file


def test_ingest_csv_and_parquet(tmp_path):
    # Create sample tidy DisCo table
    df = pd.DataFrame([
        {"period": "2026Q1", "disco": "Abuja", "received_ngn_bn": 100.0, "billed_ngn_bn": 80.0, "collected_ngn_bn": 60.0},
        {"period": "2026Q1", "disco": "Benin", "received_ngn_bn": 50.0, "billed_ngn_bn": 40.0, "collected_ngn_bn": 30.0},
        {"period": "2026Q1", "disco": "All DisCos", "received_ngn_bn": 150.0, "billed_ngn_bn": 120.0, "collected_ngn_bn": 90.0},
    ])
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    res_csv = ingest_file(csv_bytes, "sample.csv")
    assert res_csv.status in {"success", "warning"}
    assert res_csv.format == "CSV"
    assert "2026Q1" in res_csv.periods
    assert len(res_csv.disco_data) == 2
    assert res_csv.kpis["received_ngn_bn"] == 150.0

    # Test Parquet
    pq_buf = io.BytesIO()
    df.to_parquet(pq_buf, index=False)
    res_pq = ingest_file(pq_buf.getvalue(), "sample.parquet")
    assert res_pq.status in {"success", "warning"}
    assert res_pq.format == "PARQUET"
    assert len(res_pq.disco_data) == 2


def test_ingest_excel(tmp_path):
    df = pd.DataFrame([
        {"period": "2026Q1", "disco": "Ikeja", "energy received": 120.0, "energy billed": 100.0, "collections": 90.0},
        {"period": "2026Q1", "disco": "Eko", "energy received": 110.0, "energy billed": 95.0, "collections": 85.0},
    ])
    xlsx_buf = io.BytesIO()
    with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Data", index=False)
    res_xlsx = ingest_file(xlsx_buf.getvalue(), "report.xlsx")
    assert res_xlsx.status in {"success", "warning"}
    assert res_xlsx.format == "XLSX"
    assert len(res_xlsx.disco_data) == 2
    assert res_xlsx.disco_data[0]["disco"] in ["Ikeja", "Eko"]


def test_ingest_pdf():
    pdf_path = Path("data/raw/2026_Q1.pdf")
    if not pdf_path.exists():
        pytest.skip("2026_Q1.pdf not present")
    content = pdf_path.read_bytes()
    res = ingest_file(content, "2026_Q1.pdf")
    assert res.status in {"success", "warning"}
    assert res.format == "PDF"
    assert "2026Q1" in res.periods
    assert len(res.discos_found) == 11
    assert res.kpis["received_ngn_bn"] == pytest.approx(955.19, rel=1e-3)

