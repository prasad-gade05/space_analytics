---
license: cc-by-4.0
task_categories:
- tabular
tags:
- space
- orbital-debris
- satellites
- conjunction-analysis
- sgp4
- celestrak
size_categories:
- 100K<n<1M
pretty_name: Orbital Commons - Satellite Traffic & Conjunction Risk 2026
---

# Orbital Commons — Satellite Traffic & Conjunction Risk Analytics Dataset

Processed and enriched datasets derived from CelesTrak's public GP / SATCAT /
SOCRATES Plus feeds, produced by the Orbital Commons Medallion pipeline on
**2026-08-22**. Every table ships as Parquet with explicit dtypes.

## Why this dataset is different

1. **OMM-native, six-digit-ID complete.** Ingested exclusively via OMM JSON/CSV,
   so it includes satellites cataloged after 2026-07-11 ("SARAMAGO", NORAD ID
   100000) that legacy-TLE pipelines silently drop.
2. **Pre-computed conjunction-event log with reported Pc.** 148,985 screened
   events from one full SOCRATES Plus run with TCA, miss distance, closing speed,
   max probability and dilution - ready for analysis without re-running STK.
3. **Danger-zone clustering.** 25 km altitude bands scored by a K-Means model
   over crowding, debris share, ownership concentration and conjunction load.
4. **ARIMA growth forecast.** Weekly catalog-size forecast to 2031 with 95% CI
   and holdout MAPE.
5. **Documented catalog-overflow gap.** The public catalog (70,355 rows) vs the
   official counter (100,403): the withheld 7xxxx-9xxxx block is quantified.

## Tables

| File | Rows | Grain | Highlights |
|---|---|---|---|
| `dim_space_object.parquet` | 70,355 | one object | name, intl designator, owner state, nation, operator attribution, type (PAY/R/B/DEB), ops status, RCS m2, launch/decay dates, mean altitude, regime band, GP freshness |
| `fact_conjunction_events.parquet` | 148,985 | event | primary/secondary objects + names, TCA UTC, miss km, closing speed km/s, max probability, dilution km, regimes of both sides |
| `fact_catalog_growth.parquet` | 25,435 | day since 1957 | cumulative cataloged/decayed/on-orbit, daily deltas, numbering-format era |
| `fact_spatial_density.parquet` | 74 | run_date x 25 km band | counts by type, density per 1000 km3, owner-share HHI, clutter ratio |
| `fact_orbital_inventory.parquet` | 29 | run_date x regime x type | object and active-payload counts |
| `analytics_band_clusters.parquet` | 73 | 25 km band | K-Means cluster + risk label (Quiet/Moderate/Busy/Critical), features |
| `analytics_catalog_forecast.parquet` | 260 | forecast week | ARIMA(1,1,1) point forecast + 95% CI, holdout MAPE |
| `analytics_foster_topn.parquet` | 50 | top-risk event | our Foster/Chan Pc vs SOCRATES reported Pc |

## Quickstart

```python
import pandas as pd
obj = pd.read_parquet("dim_space_object.parquet")
con = pd.read_parquet("fact_conjunction_events.parquet")

top = con.nlargest(10, "max_probability")
print(top[["primary_name", "secondary_name", "min_range_km", "max_probability"]])
```

## Column notes

- `NORAD_CAT_ID` / `object_id`: integer catalog number (includes six-digit IDs >= 100000).
- `object_type`: PAY payload, R/B rocket body, DEB debris, UNK unknown.
- `regime`: VLEO <350km, LEO-Constellation 350-650, LEO-SSO 650-950,
  Legacy-Debris 950-1500, Upper-LEO 1500-2000, MEO, GEO, HEO/Deep-Space.
- `max_probability`: collision probability reported by SOCRATES Plus (STK/CAT).
- `shell_hhi`: Herfindahl index of OWNER-state shares within a band (0-1).

## Provenance & citation

Source data: CelesTrak (celestrak.org), Dr T.S. Kelso; SATCAT/SOCRATES/GP are
products of the US Space Surveillance Network via CelesTrak. Please cite
CelesTrak when using this dataset, e.g.:

> Kelso, T.S. "CelesTrak." https://celestrak.org/ (accessed August 2026).

Processing pipeline: Orbital Commons (github.com/<user>/orbital_commons),
Medallion architecture; SGP4 propagation via python-sgp4/Skyfield.

## Limitations

- Public SATCAT excludes the unpublished 7xxxx-9xxxx catalog-number block;
  row-level records cover ~70k of ~100k officially assigned numbers.
- Conjunction table reflects ONE SOCRATES run (7-day lookahead); it is not a
  historical archive.
- Pc re-derivations use spherical-covariance assumptions (see methodology tab
  of the companion dashboard).
