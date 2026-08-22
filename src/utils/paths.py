"""Central path constants for the Orbital Commons pipeline."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
GOLD_EXPORTS_DIR = GOLD_DIR / "exports"

GP_DIR = BRONZE_DIR / "gp"
SATCAT_DIR = BRONZE_DIR / "satcat"
SOCRATES_DIR = BRONZE_DIR / "socrates"


def latest_bronze_file(directory: Path, prefix: str, suffix: str) -> Path:
    """Return the most recent bronze file matching prefix_*<suffix>."""
    candidates = sorted(directory.glob(f"{prefix}_*{suffix}"))
    if not candidates:
        raise FileNotFoundError(f"No bronze files matching {prefix}_*{suffix} in {directory}")
    return candidates[-1]
