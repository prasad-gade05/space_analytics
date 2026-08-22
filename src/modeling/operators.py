"""Curated operator attribution and OWNER-code nation mapping.

dim_operator is intentionally small and verifiable: it attributes the
mega-constellations driving LEO congestion plus a handful of reference
operators. Attribution uses OBJECT_NAME prefixes observed in live data
(verified 2026-08-22: 'QIANFAN-*', 'GUOWANG *', 'KUIPER-*', ...).
Everything else falls back to the SATCAT OWNER code (state-level proxy).
"""

from __future__ import annotations

import pandas as pd

# operator_id, operator_name, parent_company, nation, constellation_name, name_prefix
OPERATORS: list[dict[str, str]] = [
    {"operator_id": 1, "operator_name": "SpaceX Starlink", "parent_company": "SpaceX",
     "nation": "United States", "constellation_name": "Starlink", "name_prefix": "STARLINK"},
    {"operator_id": 2, "operator_name": "Eutelsat OneWeb", "parent_company": "Eutelsat Group",
     "nation": "United Kingdom", "constellation_name": "OneWeb", "name_prefix": "ONEWEB"},
    {"operator_id": 3, "operator_name": "Amazon Kuiper", "parent_company": "Amazon",
     "nation": "United States", "constellation_name": "Kuiper", "name_prefix": "KUIPER"},
    {"operator_id": 4, "operator_name": "Spacesail Qianfan", "parent_company": "Shanghai Spacecom",
     "nation": "China", "constellation_name": "Qianfan (Thousand Sails)", "name_prefix": "QIANFAN"},
    {"operator_id": 5, "operator_name": "China SatNet Guowang", "parent_company": "China Satellite Network Group",
     "nation": "China", "constellation_name": "Guowang (Hulianwang Digui)", "name_prefix": "GUOWANG"},
    {"operator_id": 6, "operator_name": "Iridium Communications", "parent_company": "Iridium",
     "nation": "United States", "constellation_name": "Iridium NEXT", "name_prefix": "IRIDIUM"},
    {"operator_id": 7, "operator_name": "Planet Labs", "parent_company": "Planet Labs PBC",
     "nation": "United States", "constellation_name": "Flock/SkySat", "name_prefix": "PLANET"},
    {"operator_id": 8, "operator_name": "Orbcomm", "parent_company": "Orbcomm Inc.",
     "nation": "United States", "constellation_name": "Orbcomm", "name_prefix": "ORBCOMM"},
    {"operator_id": 9, "operator_name": "Globalstar", "parent_company": "Globalstar Inc.",
     "nation": "United States", "constellation_name": "Globalstar", "name_prefix": "GLOBALSTAR"},
]

# SATCAT OWNER codes -> display names (subset covering >95% of catalog rows).
OWNER_NATION: dict[str, str] = {
    "US": "United States", "CIS": "Russia/CIS", "PRC": "China", "FR": "France",
    "JPN": "Japan", "IND": "India", "UK": "United Kingdom", "ESA": "ESA (multi)",
    "GER": "Germany", "ITA": "Italy", "CAN": "Canada", "BRA": "Brazil",
    "SPN": "Spain", "SKOR": "South Korea", "ISRA": "Israel", "AUS": "Australia",
    "NETH": "Netherlands", "SWED": "Sweden", "NOR": "Norway", "POL": "Poland",
    "UKR": "Ukraine", "ARGN": "Argentina", "SAUD": "Saudi Arabia", "UAE": "UAE",
    "TURK": "Turkey", "SING": "Singapore", "LUXE": "Luxembourg", "ISS": "ISS (multi)",
    "EUTE": "Eutelsat (multi)", "IM": "Inmarsat (multi)", "TBD": "Unattributed",
}


def build_dim_operator() -> pd.DataFrame:
    return pd.DataFrame(OPERATORS)[
        ["operator_id", "operator_name", "parent_company", "nation", "constellation_name"]
    ]


def attribute_operator(names: pd.Series) -> pd.Series:
    """Vectorized name-prefix -> operator_id attribution; 0 = unattributed."""
    out = pd.Series(0, index=names.index, dtype="int64")
    upper = names.fillna("").str.upper()
    for op in OPERATORS:
        out[upper.str.startswith(op["name_prefix"])] = int(op["operator_id"])
    return out


def owner_to_nation(codes: pd.Series) -> pd.Series:
    return codes.map(OWNER_NATION).fillna(codes)
