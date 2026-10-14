"""Phase 1: pull the DisCo tables out of NERC quarterly report PDFs.

NERC lays each table out as plain text lines ("Abuja 157.09 130.44 83.03 ..."),
so rows are parsed from page text instead of relying on ruling-line detection.
Every failure is logged and raised; nothing is skipped silently.
"""
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pdfplumber

from .periods import AGGREGATE, ALIASES, DISCOS, canonical_disco, period_from_filename

log = logging.getLogger("extract")


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TableSpec:
    name: str
    caption: re.Pattern
    columns: tuple[str, ...]
    needs_aggregate: bool


# Captions are matched by wording, not by table number, because numbering shifts between reports.
SPECS = (
    TableSpec(
        "billing",
        re.compile(r"Table\s*\d+\s*:\s*Billing efficiency by DisCos", re.I),
        ("prev_received", "prev_billed", "prev_be", "cur_received", "cur_billed", "cur_be"),
        True,
    ),
    TableSpec(
        "collection",
        re.compile(r"Table\s*\d+\s*:\s*Revenue Collection", re.I),
        ("prev_billings", "prev_collected", "prev_ce", "cur_billings", "cur_collected", "cur_ce"),
        True,
    ),
    TableSpec(
        "atcc",
        re.compile(r"Table\s*\d+\s*:\s*ATC&C Loss Performance", re.I),
        ("target", "prev_atcc", "cur_atcc", "prev_variance", "cur_variance", "cur_rev_loss_pct"),
        False,
    ),
)

_NUM = re.compile(r"^-?\d[\d,]*(?:\.\d+)?%?$")
_NAME_ALT = "|".join(sorted((re.escape(a) for a in ALIASES), key=len, reverse=True))
_ROW = re.compile(rf"^\s*(?P<name>{_NAME_ALT})\s+(?P<rest>.+?)\s*$", re.I)
_LEADERS = re.compile(r"\.{4,}")  # table-of-contents dot leaders
_NEXT_CAPTION = re.compile(r"^\s*Table\s*\d+\s*:", re.I)


def _normalise(text: str) -> str:
    text = text.replace("\u2212", "-").replace("\u2013", "-")
    return re.sub(r"Port\s*\n\s*Harcourt", "Port Harcourt", text)


def _parse_numbers(rest: str) -> list[float | None] | None:
    out: list[float | None] = []
    for tok in rest.split():
        if tok in {"-", "--"}:
            out.append(None)
        elif _NUM.match(tok):
            out.append(float(tok.replace(",", "").rstrip("%")))
        else:
            return None
    return out


def _scan(lines: list[str], spec: TableSpec) -> tuple[dict, list]:
    rows: dict[str, list] = {}
    bad: list[tuple[str, int]] = []
    for line in lines:
        m = _ROW.match(line)
        if not m:
            continue
        disco = canonical_disco(m["name"])
        nums = _parse_numbers(m["rest"])
        if disco is None or nums is None:
            continue
        if disco in rows:
            if len([d for d in rows if d != AGGREGATE]) == len(DISCOS):
                break  # the next table repeats the DisCo names; ours is finished
            continue
        if len(nums) != len(spec.columns):
            bad.append((disco, len(nums)))
            continue
        rows[disco] = nums
    return rows, bad


def find_table(pages: list[str], spec: TableSpec) -> tuple[int, dict]:
    last_problem = "caption not found"
    for i, text in enumerate(pages):
        lines = text.splitlines()
        for j, line in enumerate(lines):
            if not spec.caption.search(line) or _LEADERS.search(line):
                continue
            window = lines[j + 1:]
            for extra in pages[i + 1:i + 3]:
                window += extra.splitlines()
            # A table ends where the next captioned table begins. Without this cut, a missing row
            # could be silently filled from a different table's row of the same DisCo.
            for k, ln in enumerate(window):
                if _NEXT_CAPTION.match(ln):
                    window = window[:k]
                    break
            rows, bad = _scan(window, spec)
            missing = [d for d in DISCOS if d not in rows]
            if not missing and (AGGREGATE in rows or not spec.needs_aggregate):
                return i + 1, rows
            last_problem = f"page {i + 1}: missing {missing or 'aggregate row'}; wrong-width rows {bad}"
    raise ExtractionError(f"{spec.name}: {last_problem}")


def extract_report(pdf_path: Path, out_dir: Path) -> dict[str, pd.DataFrame]:
    period = period_from_filename(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        pages = [_normalise(p.extract_text() or "") for p in pdf.pages]
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    for spec in SPECS:
        try:
            page, rows = find_table(pages, spec)
        except ExtractionError as exc:
            errors.append(str(exc))
            continue
        df = pd.DataFrame(
            [{"reported_period": period, "disco": d, **dict(zip(spec.columns, v)), "source_page": page}
             for d, v in rows.items()]
        )
        df.to_csv(out_dir / f"{period}_{spec.name}.csv", index=False)
        frames[spec.name] = df
        log.info("%s %s: %d rows from page %d", period, spec.name, len(df), page)
    if errors:
        raise ExtractionError(f"{pdf_path.name}: " + " | ".join(errors))
    return frames


def main(raw_dir: str = "data/raw", out_dir: str = "data/interim") -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pdfs = sorted(Path(raw_dir).glob("*.pdf"))
    if not pdfs:
        log.error("no PDFs in %s. Run scripts/fetch_reports.py first.", raw_dir)
        return 1
    log_rows, failed = [], 0
    for pdf in pdfs:
        try:
            frames = extract_report(pdf, Path(out_dir))
            log_rows.append({"report": pdf.name, "status": "ok", "tables": len(frames), "message": ""})
        except (ExtractionError, ValueError) as exc:
            failed += 1
            log.error("FAILED %s", exc)
            log_rows.append({"report": pdf.name, "status": "failed", "tables": 0, "message": str(exc)})
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    pd.DataFrame(log_rows).to_csv(Path(out_dir) / "extraction_log.csv", index=False)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
