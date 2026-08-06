from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Resolve data/ for local repo, editable install, and Docker (/app/data)."""
    env = os.environ.get("SCANNER_DATA_DIR")
    if env:
        return Path(env)

    candidates = [
        Path.cwd() / "data",
        Path("/app/data"),
    ]
    # src/community_scanner/... → repo root /data when developing from source tree
    here = Path(__file__).resolve()
    for up in range(2, 6):
        candidates.append(here.parents[up - 1] / "data")

    for path in candidates:
        if path.is_dir():
            return path
    return Path.cwd() / "data"
