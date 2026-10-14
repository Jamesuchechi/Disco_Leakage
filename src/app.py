"""FastAPI interactive web application for DisCo Leakage Intelligence.

Run via:
    uv run python -m src.app
or:
    uv run uvicorn src.app:app --reload --port 8000
"""
from __future__ import annotations

import argparse
import io
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .build_dashboard import build
from .ingest import IngestResult, ingest_file

log = logging.getLogger("disco_app")

app = FastAPI(title="DisCo Leakage Intelligence Platform")

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "app.html"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
DOCS_INDEX = BASE_DIR / "docs" / "index.html"

# Global in-memory state of current loaded data
_CURRENT_INGEST: IngestResult | None = None


def get_default_dataset() -> IngestResult:
    """Load default dataset from data/processed if available, otherwise synthesize or extract."""
    global _CURRENT_INGEST
    if _CURRENT_INGEST is not None:
        return _CURRENT_INGEST

    disco_csv = PROCESSED_DIR / "disco_quarterly.csv"
    if disco_csv.exists():
        content = disco_csv.read_bytes()
        _CURRENT_INGEST = ingest_file(content, "disco_quarterly.csv")
        return _CURRENT_INGEST

    raw_pdf = BASE_DIR / "data" / "raw" / "2026_Q1.pdf"
    if raw_pdf.exists():
        content = raw_pdf.read_bytes()
        _CURRENT_INGEST = ingest_file(content, "2026_Q1.pdf")
        return _CURRENT_INGEST

    # Return empty placeholder
    return IngestResult(
        status="warning",
        filename="No data loaded",
        format="NONE",
        periods=[],
        discos_found=[],
        missing_discos=[],
        issues=[{"level": "info", "check": "data", "where": "workspace", "detail": "Upload a PDF, CSV, Excel, or Parquet file to begin."}],
        disco_data=[],
        national_data=[],
        changes_data=[],
        kpis={},
        summary_note="No dataset loaded. Drag and drop a file above.",
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    if not TEMPLATE_PATH.exists():
        raise HTTPException(status_code=500, detail="Template not found")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


@app.get("/docs/index.html", response_class=HTMLResponse)
def static_dashboard() -> str:
    if DOCS_INDEX.exists():
        return DOCS_INDEX.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail="Static dashboard not generated yet")


@app.get("/api/data")
def api_get_data() -> dict[str, Any]:
    dataset = get_default_dataset()
    return dataset.to_dict()


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    global _CURRENT_INGEST
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    result = ingest_file(content, file.filename)
    if result.status != "error" or result.disco_data:
        _CURRENT_INGEST = result
    return result.to_dict()


@app.post("/api/save")
def api_save_to_workspace() -> dict[str, str]:
    global _CURRENT_INGEST
    if not _CURRENT_INGEST or not _CURRENT_INGEST.disco_data:
        raise HTTPException(status_code=400, detail="No ingested data to save.")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df_disco = pd.DataFrame(_CURRENT_INGEST.disco_data)
    df_nat = pd.DataFrame(_CURRENT_INGEST.national_data)

    df_disco.to_csv(PROCESSED_DIR / "disco_quarterly.csv", index=False)
    try:
        df_disco.to_parquet(PROCESSED_DIR / "disco_quarterly.parquet", index=False)
    except Exception as e:
        log.warning("Parquet save failed: %s", e)

    if not df_nat.empty:
        df_nat.to_csv(PROCESSED_DIR / "aggregate_quarterly.csv", index=False)

    analysis_dir = PROCESSED_DIR / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    df_disco.to_csv(analysis_dir / "leakage_by_disco.csv", index=False)
    if not df_nat.empty:
        df_nat.to_csv(analysis_dir / "national_summary.csv", index=False)
    if _CURRENT_INGEST.changes_data:
        pd.DataFrame(_CURRENT_INGEST.changes_data).to_csv(analysis_dir / "quarter_changes.csv", index=False)

    # Rebuild static dashboard
    try:
        build(processed=str(PROCESSED_DIR), out=str(DOCS_INDEX))
    except Exception as e:
        log.warning("Failed to rebuild static dashboard: %s", e)

    return {"message": "Data saved to data/processed and static dashboard updated at docs/index.html"}


@app.get("/api/export/{fmt}")
def api_export(fmt: str, period: str = "") -> Response:
    global _CURRENT_INGEST
    data = get_default_dataset()
    if not data.disco_data:
        raise HTTPException(status_code=404, detail="No data available to export")

    df = pd.DataFrame(data.disco_data)
    if period and "period" in df.columns:
        filtered = df[df["period"] == period]
        if not filtered.empty:
            df = filtered

    fmt_lower = fmt.lower()
    if fmt_lower == "csv":
        out = io.StringIO()
        df.to_csv(out, index=False)
        return Response(
            content=out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="disco_leakage_{period or "all"}.csv"'}
        )
    elif fmt_lower == "parquet":
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return Response(
            content=buf.getvalue(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="disco_leakage_{period or "all"}.parquet"'}
        )
    elif fmt_lower == "json":
        return Response(
            content=json.dumps(data.to_dict(), indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="disco_leakage_{period or "all"}.json"'}
        )
    elif fmt_lower == "html":
        # Build self-contained HTML
        template = BASE_DIR / "dashboard" / "template.html"
        if not template.exists():
            template = TEMPLATE_PATH
        html_content = template.read_text(encoding="utf-8")
        payload = {
            "note": data.summary_note,
            "disco": data.disco_data,
            "national": data.national_data,
            "changes": data.changes_data,
        }
        rendered = html_content.replace("/*DATA*/", json.dumps(payload).replace("</", "<\\/"))
        return Response(
            content=rendered,
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="disco_leakage_report_{period or "all"}.html"'}
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported export format '{fmt}'")


def main() -> None:
    import uvicorn
    parser = argparse.ArgumentParser(description="Run DisCo Leakage Intelligence Web App")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable live reload")
    args = parser.parse_args()

    print(f"\n=======================================================")
    print(f"🚀 DisCo Leakage Intelligence App running at:")
    print(f"   http://{args.host}:{args.port}")
    print(f"=======================================================\n")
    uvicorn.run("src.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
