"""Builds a small synthetic NERC-style PDF for tests (real Q1 2026 values, simplified layout)."""
from __future__ import annotations

from pathlib import Path

from reportlab.pdfgen import canvas


def _fmt(v: float) -> str:
    return f"{v:,.2f}"


def _row(name: str, vals) -> str:
    return f"{name} " + " ".join(_fmt(v) for v in vals)


def _page(c: canvas.Canvas, lines: list[str]) -> None:
    c.setFont("Helvetica", 9)
    y = 800
    for ln in lines:
        c.drawString(40, y, ln)
        y -= 13
    c.showPage()


def make_report_pdf(path: Path, t6: dict, t8: dict, t9: dict, drop: dict[str, str] | None = None) -> Path:
    drop = drop or {}
    c = canvas.Canvas(str(path))
    _page(c, ["FIRST QUARTER 2026 NERC QUARTERLY REPORTS", "Cover page"])
    _page(c, [
        "List of Tables",
        "Table 6: Billing efficiency by DisCos in 2025/Q4 vs. 2026/Q1 ........................ 34",
        "Table 8: Revenue Collection Performance (%) of DisCos in 2025/Q4 vs. 2026/Q1 ....... 36",
        "Table 9: ATC&C Loss Performance (%) by DisCos in 2026/Q1 ............................ 39",
    ])
    lines = ["Table 6: Billing efficiency by DisCos in 2025/Q4 vs. 2026/Q1", "DisCos 2025/Q4 2026/Q1"]
    lines += [_row(k, v) for k, v in t6.items() if drop.get("billing") != k]
    lines += ["Table 7: Comparison of DisCos' Billing Efficiency (BE) and Energy Accounting Efficiency (EAE)",
              _row("Abuja", (83.03, 76.33, 6.71, 84.16, 78.38, 5.78)),
              _row("Benin", (65.51, 87.64, -22.13, 70.79, 87.23, -16.43))]
    _page(c, lines)
    lines = ["Table 8: Revenue Collection Performance (%) of DisCos in 2025/Q4 vs. 2026/Q1", "DisCos 2025/Q4 2026/Q1"]
    lines += [_row(k, v) for k, v in t8.items() if drop.get("collection") != k]
    _page(c, lines)
    lines = ["Table 9: ATC&C Loss Performance (%) and corresponding Revenue Loss/Gain by", "DisCos in 2026/Q1"]
    lines += [_row(k, v) for k, v in t9.items() if drop.get("atcc") != k]
    lines += ["All DisCos", "MYTO Level 16.92", "Total Technical,", "Commercial & Collection losses - 34.90 37.44 -19.05",
              "Table 10: Total GenCo Invoice and Final Obligation (DRO)", "Abuja 113.43 58.49"]
    _page(c, lines)
    c.save()
    return path
