"""Phase 3: upload the version snapshots to Strata, oldest first.

This does NOT guess Strata's SDK signatures. Wire `upload_version` to your own SDK client
(backend/src/strata_sdk/client.py exposes upload_dataset and commit_version). Until then, run
`python scripts/load_to_strata.py` to print the exact sequence to follow in the Strata UI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATASET_NAME = "nigeria-disco-performance"
MANIFEST = Path("data/versions/manifest.json")


def upload_version(path: Path, message: str, first: bool) -> None:
    """Replace the body with real SDK calls: upload_dataset(...) for the first version, commit_version(...) after."""
    raise NotImplementedError("connect this to strata_sdk, or follow the printed manual steps")


def main() -> int:
    if not MANIFEST.exists():
        print("Run `uv run python -m src.versions` first.")
        return 1
    manifest = json.loads(MANIFEST.read_text())
    try:
        for i, m in enumerate(manifest):
            upload_version(MANIFEST.parent / m["file"], m["commit_message"], first=(i == 0))
            print(f"uploaded {m['file']}")
    except NotImplementedError:
        print(f"Manual steps (dataset name: {DATASET_NAME}):")
        for i, m in enumerate(manifest):
            verb = "Upload as a new dataset" if i == 0 else "Commit as a new version"
            print(f"  {i + 1}. {verb}: data/versions/{m['file']}\n     message: {m['commit_message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
