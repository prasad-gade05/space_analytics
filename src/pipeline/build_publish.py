"""Assemble the publish-ready dataset folder for Kaggle / Hugging Face.

Copies the committed Gold exports + DatasetReadme.md into
data/publish/orbital_commons_v1/ and writes a checksums manifest.
Idempotent: rebuilds the folder from scratch each run.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.utils.paths import REPO_ROOT

EXPORTS = REPO_ROOT / "data" / "gold" / "exports"
README_SRC = REPO_ROOT / "packaging" / "DatasetReadme.md"
OUT = REPO_ROOT / "data" / "publish" / "orbital_commons_v1"

TABLES = [
    "dim_space_object",
    "dim_altitude_shell",
    "dim_operator",
    "fact_orbital_inventory",
    "fact_spatial_density",
    "fact_conjunction_events",
    "fact_catalog_growth",
    "analytics_band_clusters",
    "analytics_catalog_forecast",
    "analytics_foster_topn",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    now = datetime.now(timezone.utc)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    manifest: list[dict] = []
    for name in TABLES:
        src = EXPORTS / f"{name}.parquet"
        if not src.exists():
            raise FileNotFoundError(f"missing export {src} - run gold build first")
        dst = OUT / src.name
        shutil.copy2(src, dst)
        manifest.append({"file": dst.name, "sha256": sha256(dst),
                         "bytes": dst.stat().st_size})
        print(f"  + {dst.name} ({dst.stat().st_size/1024:,.0f} KB)")

    shutil.copy2(README_SRC, OUT / "DatasetReadme.md")
    print("  + DatasetReadme.md")

    meta = {
        "package": "orbital_commons_v1",
        "built_at_utc": now.isoformat(timespec="seconds"),
        "files": manifest,
    }
    (OUT / "_manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\npublish folder ready: {OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
