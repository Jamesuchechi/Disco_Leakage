"""Unit tests for FastAPI endpoints in src.app."""
import io
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def test_index_page():
    res = client.get("/")
    assert res.status_code == 200
    assert "DisCo Commercial Leakage Intelligence" in res.text


def test_api_data_endpoint():
    res = client.get("/api/data")
    assert res.status_code == 200
    data = res.json()
    assert "disco_data" in data
    assert "kpis" in data


def test_api_upload_csv():
    df = pd.DataFrame([
        {"period": "2026Q1", "disco": "Abuja", "received_ngn_bn": 100.0, "billed_ngn_bn": 80.0, "collected_ngn_bn": 60.0},
        {"period": "2026Q1", "disco": "Benin", "received_ngn_bn": 50.0, "billed_ngn_bn": 40.0, "collected_ngn_bn": 30.0},
    ])
    csv_buf = io.BytesIO()
    df.to_csv(csv_buf, index=False)
    csv_buf.seek(0)

    res = client.post("/api/upload", files={"file": ("test_upload.csv", csv_buf.getvalue(), "text/csv")})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in {"success", "warning"}
    assert len(data["disco_data"]) == 2
    assert data["format"] == "CSV"


def test_api_export_endpoints():
    for fmt in ["csv", "json", "parquet", "html"]:
        res = client.get(f"/api/export/{fmt}")
        assert res.status_code == 200, f"Format {fmt} failed"
        assert len(res.content) > 0
