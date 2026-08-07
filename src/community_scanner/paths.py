from __future__ import annotations

import os
from pathlib import Path


def package_seed_dir() -> Path:
    return Path(__file__).resolve().parent / "seed_data"


def data_dir() -> Path:
    """Resolve writable/runtime data dir (SCANNER_DATA_DIR or /app/data or cwd/data)."""
    env = os.environ.get("SCANNER_DATA_DIR")
    if env:
        return Path(env)

    candidates = [
        Path.cwd() / "data",
        Path("/app/data"),
    ]
    here = Path(__file__).resolve()
    for up in range(2, 6):
        try:
            candidates.append(here.parents[up - 1] / "data")
        except IndexError:
            break

    for path in candidates:
        if path.is_dir():
            return path
    return Path.cwd() / "data"


def resolve_data_file(name: str) -> Path:
    """Prefer runtime data/, then packaged seed_data/ (always in Docker wheel)."""
    runtime = data_dir() / name
    if runtime.exists():
        return runtime
    packaged = package_seed_dir() / name
    if packaged.exists():
        return packaged
    return runtime
