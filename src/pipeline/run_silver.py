"""Silver-layer orchestrator: bronze -> data/silver/*.parquet + quality report."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import pandas as pd

from src.transformation import silver_datasets, silver_gp
from src.utils.paths import (
    GP_DIR,
    REPO_ROOT,
    SATCAT_DIR,
    SOCRATES_DIR,
    SILVER_DIR,
    latest_bronze_file,
)


def quality_report(frames: dict[str, pd.DataFrame]) -> dict:
    report: dict = {}
    gp = frames.get("gp_objects")
    if gp is not None:
        report["gp_objects"] = {
            "rows": int(len(gp)),
            "valid": int(gp["is_valid"].sum()),
            "rejected": int((~gp["is_valid"]).sum()),
            "reject_reasons": (
                gp.loc[~gp["is_valid"], "reject_reason"]
                .str.split(";").explode().value_counts().head(10).to_dict()
            ),
            "stale": int(gp["is_stale"].sum()),
            "six_digit_ids": int((gp["norad_cat_id"] >= 100_000).sum()),
            "regime_counts": gp.loc[gp["is_valid"], "regime"].value_counts().to_dict(),
        }
    satcat = frames.get("satcat")
    if satcat is not None:
        report["satcat"] = {
            "rows": int(len(satcat)),
            "on_orbit": int(satcat["is_on_orbit"].sum()),
            "object_types": satcat["OBJECT_TYPE"].value_counts().to_dict(),
        }
    soc = frames.get("conjunctions")
    if soc is not None:
        report["conjunctions"] = {
            "rows": int(len(soc)),
            "tca_min": str(soc["TCA"].min()),
            "tca_max": str(soc["TCA"].max()),
            "prob_ge_1e_4": int((soc["max_probability"] >= 1e-4).sum()),
            "prob_ge_1e_2": int((soc["max_probability"] >= 1e-2).sum()),
        }
    growth = frames.get("catalog_growth")
    if growth is not None:
        report["catalog_growth"] = {
            "rows": int(len(growth)),
            "last_date": str(growth["date"].max().date()),
            "last_cataloged": int(growth["cataloged"].iloc[-1]),
        }
    return report


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    run_date = datetime.now(timezone.utc)
    print(f"=== Orbital Commons Silver build — {run_date.isoformat(timespec='seconds')} ===")

    gp_files = sorted(GP_DIR.glob("gp_*_*.json"))
    frames: dict[str, pd.DataFrame] = {}

    print(f"[silver/gp] transforming {len(gp_files)} group files ...")
    gp = silver_gp.build_silver_gp(gp_files, run_date)
    frames["gp_objects"] = gp

    print("[silver/satcat] normalizing full catalog snapshot ...")
    satcat_path = latest_bronze_file(SATCAT_DIR, "satcat_full", ".csv")
    frames["satcat"] = silver_datasets.build_silver_satcat(satcat_path)

    print("[silver/socrates] normalizing conjunction events ...")
    soc_path = latest_bronze_file(SOCRATES_DIR, "socrates_conjunctions", ".csv")
    frames["conjunctions"] = silver_datasets.build_silver_socrates(soc_path)

    print("[silver/growth] normalizing catalog growth series ...")
    growth_path = latest_bronze_file(SILVER_DIR.parent / "bronze" / "satcat", "satcat_growth_history", ".csv")
    frames["catalog_growth"] = silver_datasets.build_silver_growth(growth_path)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        out = SILVER_DIR / f"{name}.parquet"
        df.to_parquet(out, index=False)
        size_kb = out.stat().st_size / 1024
        print(f"    wrote {out.relative_to(REPO_ROOT)} ({len(df):,} rows, {size_kb:,.0f} KB)")

    report = quality_report(frames)
    report_path = SILVER_DIR / "_quality_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("\n=== QUALITY REPORT ===")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
