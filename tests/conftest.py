from __future__ import annotations

from pathlib import Path

import pytest

from openlending.config import REPO_ROOT, Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a temporary data directory and the committed sample."""
    return Settings(
        data_dir=tmp_path / "data",
        sample_dir=REPO_ROOT / "sample",
        docs_dir=tmp_path / "docs",
        duckdb_memory_limit="1GB",
        duckdb_threads=2,
    )
