"""Period and DisCo-name helpers shared by every stage."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

PERIOD_RE = re.compile(r"(\d{4})[_\-\s]?Q([1-4])", re.IGNORECASE)

DISCOS = [
    "Abuja", "Benin", "Eko", "Enugu", "Ibadan", "Ikeja",
    "Jos", "Kaduna", "Kano", "Port Harcourt", "Yola",
]
AGGREGATE = "All DisCos"

# NERC tables use several spellings for the same company.
ALIASES = {
    "abuja": "Abuja", "benin": "Benin", "eko": "Eko", "enugu": "Enugu",
    "ibadan": "Ibadan", "ikeja": "Ikeja", "jos": "Jos", "kaduna": "Kaduna",
    "kano": "Kano", "port harcourt": "Port Harcourt", "ph": "Port Harcourt",
    "p/harcourt": "Port Harcourt", "p/h": "Port Harcourt", "yola": "Yola",
    "all discos": AGGREGATE, "all disco": AGGREGATE,
}

# Methodology breaks documented in NERC's own report footnotes.
BILLING_COMMERCIAL_FROM = "2025Q2"  # earlier reports computed billing efficiency from energy (GWh)
VAT_BASIS_FROM = "2026Q1"           # naira value of energy received adjusted for VAT from here


def canonical_disco(raw: str) -> str | None:
    return ALIASES.get(re.sub(r"\s+", " ", raw.strip().lower()))


def period_from_filename(name: str | Path) -> str:
    m = PERIOD_RE.search(Path(name).name)
    if not m:
        raise ValueError(f"cannot read a period like 2026_Q1 from {name!r}")
    return f"{m.group(1)}Q{m.group(2)}"


def prev_period(period: str) -> str:
    year, q = int(period[:4]), int(period[5])
    return f"{year - 1}Q4" if q == 1 else f"{year}Q{q - 1}"


def quarter_end(period: str) -> date:
    year, q = int(period[:4]), int(period[5])
    month, day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[q]
    return date(year, month, day)
