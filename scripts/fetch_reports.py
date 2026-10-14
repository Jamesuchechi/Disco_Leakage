"""Phase 0: download the NERC reports listed in data/raw/sources.csv.

Run this on your own machine (it needs access to nerc.gov.ng). Rows with an empty url are
skipped with a reminder. Each download is checked to be a real PDF and its sha256 is recorded.
"""
from __future__ import annotations

import csv
import hashlib
import sys
import urllib.request
from datetime import date
from pathlib import Path

RAW = Path("data/raw")


def main() -> int:
    rows = list(csv.DictReader((RAW / "sources.csv").open()))
    log_lines, missing = [], 0
    for r in rows:
        dest = RAW / r["filename"]
        if not r["url"]:
            print(f"SKIP {r['period']}: no url yet in sources.csv")
            missing += 1
            continue
        if not dest.exists():
            req = urllib.request.Request(r["url"], headers={"User-Agent": "disco-leakage/0.1"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if not data.startswith(b"%PDF"):
                print(f"FAIL {r['period']}: response is not a PDF")
                return 1
            dest.write_bytes(data)
        sha = hashlib.sha256(dest.read_bytes()).hexdigest()
        log_lines.append(f"| {r['period']} | {r['filename']} | {r['url']} | {date.today()} | `{sha[:16]}` |")
        print(f"OK   {r['period']} -> {dest} ({dest.stat().st_size // 1024} KB)")
    header = "# Sources\n\n| Period | File | URL | Retrieved | sha256 (first 16) |\n|---|---|---|---|---|\n"
    (RAW / "SOURCES.md").write_text(header + "\n".join(log_lines) + "\n")
    if missing:
        print(f"\n{missing} report(s) still need a url in data/raw/sources.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
