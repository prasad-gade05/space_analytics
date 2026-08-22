# Orbital Commons — Technical Reference

Version: 2026-08-22 (build 1). All figures below were produced from the actual
data files in this repository unless marked as upstream constants.

## 1. Pipeline contract (Medallion)

| Layer | Input | Output | Guarantees |
|---|---|---|---|
| Bronze | CelesTrak HTTP endpoints | pristine bytes + `manifest_<date>.json` (sha256, row counts, source URL, `ingested_at_utc`) | byte-faithful raw storage; idempotent per UTC day; structural validation with hard-fail thresholds |
| Silver | bronze files | typed Parquet in `data/silver/` | strict dtypes; dedup by NORAD ID keeping freshest epoch; rejected rows retained with `reject_reason`; no silent drops |
| Gold | silver parquet | `data/gold/orbital.duckdb` + exports | star schema; referential checks at build time; exports committed to git |

## 2. Bronze ingestion decisions

1. **OMM JSON only for GP data.** TLE cannot represent catalog numbers ≥ 100000;
   the live catalog entered the six-digit era on 2026-07-11. Verified live:
   our GP pulls contain 331+ six-digit-ID objects that TLE-based pipelines lose.
2. **Full SATCAT via documented year sweep** (`records.php?INTDES=<year>&FORMAT=CSV`,
   1957..current). Rejected alternatives, verified live:
   - `/pub/satcat.csv`: capped at legacy IDs < 70000 (70,355 rows = sub-70000 population).
   - bare `records.php?FORMAT=CSV` / `ONORBIT=TRUE&FORMAT=CSV`: rejected by the API
     ("Invalid query") — ONORBIT is a flag and a selector is mandatory.
3. **SOCRATES bulk CSV** (`sort-minRange.csv`, RFC 4180). Live header:
   `NORAD_CAT_ID_1, OBJECT_NAME_1, DSE_1, NORAD_CAT_ID_2, OBJECT_NAME_2, DSE_2,
   TCA, TCA_RANGE, TCA_RELATIVE_SPEED, MAX_PROB, DILUTION`.
   There is no MIN_RANGE column; range-at-TCA is `TCA_RANGE`.
4. **Incremental sweep with per-year cache.** Historical launch years never gain
   objects; each year file is persisted atomically on arrival under
   `data/bronze/satcat/years/`. Steady state ≈ 2 requests/run.
5. **Rate limiting.** ~80 requests in ~15 min triggers an IIS-level 403 site block
   lasting ≥ 30–60 min. Mitigations: UA identification, ≥3 s pacing (10 s during
   sweeps), 300 s cooldown on 403, skip-if-exists idempotency.

## 3. Silver transformations

### Alpha-5 codec (`src/utils/alpha5.py`)
Bidirectional 5-char field ↔ integer. Letters A..Z map to ten-thousands digits
10..33 skipping I and O: A=10 … H=17, J=18 … N=22, P=23 … Z=33. Ceiling
`Z9999` = 339,999. Numbers < 100000 use plain `%05d`.

### Geometry (`src/transformation/shells.py`)
- Semi-major axis from mean motion: `a = (μ/n²)^⅓`, n converted rev/day → rad/s
  over the **sidereal day** (86 164.0905 s), μ = 398 600.4418 km³/s².
- Perigee/apogee relative to equatorial radius R = 6378.137 km (matches SATCAT columns).
- Canonical regimes: VLEO 100–350 · LEO-Constellation 350–650 · LEO-SSO 650–950 ·
  Legacy-Debris 950–1500 · Upper-LEO 1500–2000 · MEO 2000–35586 · GEO 35586–36100 · HEO/Deep-Space.
- Fine density grid: 25 km bands below 2000 km.

### GP validation gates (`src/transformation/silver_gp.py`)
Per object: positive mean motion; eccentricity ∈ [0,1); SGP4 propagation must
succeed (skyfield `EarthSatellite.from_omm`, propagated **at the element epoch**);
TEME position rotated to WGS84 subpoint via Skyfield's ITRS machinery.
Staleness flag when epoch > 14 days at run time. Validation result of the current
build: **19,634/19,634 valid, 144 stale, 0 rejections**.

Cross-check performed: SATCAT on-orbit count (34,868) equals the final
`On Orbit` value of CelesTrak's official growth series to the object.

## 4. Gold star schema

```
dim_space_object   object_id PK, name, intl_designator, owner_code→nation,
                   operator_id FK, object_type(PAY/R/B/DEB/UNK), ops status,
                   RCS m², launch/decay dates, on-orbit & active flags,
                   mean_altitude_km, band_25km, regime, has_gp_elements, is_stale
dim_altitude_shell shell_id PK, regime, bounds, volume
dim_operator       operator_id PK, name, parent_company, nation, constellation
dim_date           date_key PK, y/q/m, solar-cycle phase label (SC25 heuristic)
fact_orbital_inventory    run_date × regime × object_type → counts (+active)
fact_spatial_density      run_date × 25 km band → counts, debris, volume,
                          density_per_1000km³, owner-share HHI, clutter ratio
fact_conjunction_events   event grain: TCA, miss km, rel speed, Pc, dilution,
                          regimes+nations of both objects
fact_catalog_growth       daily since 1957 + new/decay deltas + format era
analytics_foster_topn     top-50 events re-scored with our Foster integrator
```

Population policy: inventory/density use the **SATCAT on-orbit population binned
by its own APOGEE/PERIGEE columns** (34,250 of 34,868 have both values; 98.2%).
GP propagation enriches `dim_space_object` rather than limiting coverage.

Format eras on `fact_catalog_growth`: `5-digit` before 2020-05-01 (Alpha-5 format
did not exist yet), `alpha5-capable` 2020-05-01 → 2026-07-10, `6-digit` from
2026-07-11 (SARAMAGO, first public six-digit ID).

## 5. Analytics definitions

- **HHI** `Σ sᵢ²` on fractional shares within a band/regime. Current build:
  450–475 km band HHI ≈ 0.92 (dominated by one operator's payloads).
- **Gini** standard rank formula on national debris counts (on-orbit).
- **Foster/Chan Pc** — 2D integral over the encounter plane of an isotropic
  Gaussian N(0, σ²I) evaluated inside a disk of combined hard-body radius
  R centred at the miss vector. Assumptions (CARA/Foster): short encounter,
  linear relative motion, spherical bodies, uncorrelated Gaussian covariance.
  - σ taken from SOCRATES `DILUTION` (km, interpreted as combined 1σ positional
    uncertainty; present for 148,985/148,985 rows).
  - R = 20 m combined hard-body radius.
  - Grid: 1601×1601 points over ±8σ; validated against the analytic zero-miss
    limit `Pc = 1 − exp(−R²/2σ²)` to <1%.
  - Benchmark vs SOCRATES reported Pc on top-50 events: median ratio 0.06,
    full spread 0–42×. Expected divergence: SOCRATES uses STK/CAT with richer
    covariance handling; our spherical assumption is deliberately conservative.

## 6. Data-quality findings worth citing

1. Official counter 100,403 = max catalog number ever assigned; public queryable
   catalog = 70,355. The ~30k gap is the unpublished 7xxxx–9xxxx block (8xxxx
   analyst range used by 18 SDS plus withheld entries). Pre-2025 launch years top
   out at ID ≈ 69,092.
2. Public numbering jumped from the 69xxx range straight past the reserved block
   into six-digit IDs starting 2026-07-11 — visible as a discontinuity, not a
   crossing, because the public series never reached 99,999.
3. 5,502 "on-orbit" SATCAT rows carry mean altitude ≤ 25 km (decaying or lost
   objects still without decay dates) — surfaced honestly instead of filtered.

## 7. Deliberate exclusions

- **Space-Track.org**: gated (account + up-to-30-day approval); adds CDM
  covariance and decay event logs. Dropped to keep the pipeline reproducible by
  anyone with zero gating. Revisit as an enrichment module if approved.
- **ESA DISCOS**: gated to ESA-member-state affiliated users. Excluded.
- **Prophet/ARIMA forecasting**: not yet wired; the dashboard extrapolates the
  crisis narrative structurally (era markers, official-counter line) rather than
  fitting a model. Planned next iteration.

## 8. Operations

- Local: `make all && make dashboard`.
- CI (`.github/workflows/ingest.yml`): nightly 06:00 UTC — bronze → silver → gold
  → pytest → commit refreshed `data/gold/exports/`. Manual dispatch supports
  forced re-download.
- Tests: 29 (codec edge cases, geometry sanity incl. ISS/GEO orbits, SGP4
  propagation vs SATCAT apogee/perigee, metric identities, Foster-vs-analytic,
  figure builders).
