# Orbital Commons — Task Plan

## Task 1: Bronze Layer — Download All Raw Data (COMPLETE)

All sources are free, no-auth CelesTrak endpoints (per kickstart Section 2, 100%-free-only strategy).
Format rule: **OMM JSON only for GP data — never legacy TLE** (TLE cannot represent 6-digit catalog numbers post July-2026 overflow).

### Endpoints (verified live 2026-08-22)

| Source | URL | Format |
|---|---|---|
| GP orbital elements | `https://celestrak.org/NORAD/elements/gp.php?GROUP=<slug>&FORMAT=JSON` | OMM JSON |
| SATCAT full snapshot | `records.php?INTDES=<year>&FORMAT=CSV` sweep, 1957..current | CSV |
| SATCAT growth history | `https://celestrak.org/satcat/growth.csv` | CSV |
| Boxscore | `https://celestrak.org/satcat/boxscore.php` | HTML |
| SOCRATES conjunctions | `https://celestrak.org/SOCRATES/sort-minRange.csv` | RFC4180 CSV |

### Critical data-quality findings (verified live 2026-08-22)

1. **`/pub/satcat.csv` and bare `records.php?FORMAT=CSV` are legacy-capped.** The static file contains only objects with catalog numbers < 70000 (70,355 rows). The kickstart's example URL `records.php?ONORBIT=TRUE&FORMAT=CSV` is rejected by the live API ("Invalid query") — ONORBIT is a flag, not a selector; a selector is mandatory.
2. **The documented `INTDES=<year>` query reaches ALL public objects**, including six-digit IDs (verified: Saramago, NORAD 100000, appears in INTDES=2026; max ID in that year = 100403).
3. **"Official USSF SATCAT at 100,403" is the max catalog NUMBER ever assigned, not the public row count.** CelesTrak's public SATCAT holds 70,355 rows. The ~30k gap = the unpublished 70000–99999 block (8xxxx analyst range used by 18 SDS per SOCRATES Plus notes + withheld entries). Pre-2025 launch years max out at ID ~69,092.
4. **CelesTrak's official `growth.csv` also counts only the public catalog** (Cataloged tops out at 70,355). The divergence between max-assigned-number and public-cataloged size going forward IS the overflow crisis, quantifiable from our own daily snapshots.
5. **SOCRATES bulk CSV header** (live): `NORAD_CAT_ID_1, OBJECT_NAME_1, DSE_1, NORAD_CAT_ID_2, OBJECT_NAME_2, DSE_2, TCA, TCA_RANGE, TCA_RELATIVE_SPEED, MAX_PROB, DILUTION` — note: no MIN_RANGE column; range at TCA = `TCA_RANGE`.
6. **Rate limiting:** CelesTrak serves HTTP 403 bursts after ~80 rapid requests; cooldown required (~minutes). Ingestion must stay under ~1 request / 3–6 s.

### Checklist

- [x] Verify environment (Python 3.13.1) and live endpoint availability
- [x] Extract exact GP GROUP slugs from live index HTML (no guessing)
- [x] Locate SOCRATES bulk CSV link from socrates-format.php
- [x] Write idempotent ingestion script `src/ingestion/fetch_bronze.py`
- [x] Execute download into `data/bronze/` (all 11 datasets)
- [x] Validate row counts vs live figures
- [x] Manifests written per layer with sha256 checksums
- [x] Idempotency proof: rerun validates from cache in seconds, zero network
- [x] Manual Audit Checkpoint: sample data presented to user for confirmation → Silver layer approved to start

## Task 2: Silver Layer — Physics-Validated Clean Tables

### Plan (loop: think→analyze→verify→plan→implement→verify)

- [x] VERIFY env/APIs: skyfield 1.55 has `EarthSatellite.from_omm`; SARAMAGO propagates to 510 km vs SATCAT 496–509 ✓
- [ ] `src/utils/alpha5.py` — bidirectional Alpha-5↔int codec (A=10..Z=33, skip I/O, ceiling Z9999=339999)
- [ ] `src/utils/paths.py` — central path constants
- [ ] `src/transformation/shells.py` — semi-major axis from mean motion; perigee/apogee; canonical regime bins + 25 km bands
- [ ] `src/transformation/silver_gp.py` — OMM→validated objects: dedup by CATNR keep freshest epoch, SGP4 propagate @epoch, TEME→geodetic via skyfield, validation gates (perigee>0, e∈[0,1), sgp4 error), staleness flag (>14 d), shell assignment
- [ ] `src/transformation/silver_satcat.py` — typed SATCAT (dates, numerics, object_type, ops_status, on_orbit flag)
- [ ] `src/transformation/silver_socrates.py` — typed conjunction events (TCA parse, floats, pair IDs)
- [ ] `src/transformation/silver_growth.py` — growth series → dated parquet + daily delta
- [ ] `src/pipeline/run_silver.py` — orchestrator → data/silver/*.parquet + quality report JSON
- [ ] tests/test_alpha5.py, test_shells.py, test_silver_transforms.py → pytest green
- [ ] Run on real Bronze data; audit outputs (row counts, null rates, rejection reasons)

### Design decisions
- Rejected rows are KEPT with `reject_reason` (data-quality KPI input), never silently dropped
- Propagation at element epoch (deterministic; no wall-clock dependency in outputs except staleness flag computed against run date)
- μ=398600.4418 km³/s², R=6378.137 km consistent with SATCAT apogee/perigee convention

**Final state: 11 ok / 0 fail / 6 informational warnings. 252,208 records, ~38 MB total.**

| Dataset | Records | Validation vs live reference |
|---|---|---|
| GP active | 16,400 | 331 six-digit IDs incl. SARAMAGO (100000) |
| GP starlink / oneweb / kuiper / qianfan / hulianwang | 10,973 / 651 / 391 / 238 / 199 | constellation counts |
| GP analyst / stations / geo / last-30-days | 569 / 22 / 568 / 210 | six-digit IDs present in analyst+last-30 |
| GP debris clouds (FY-1C, IR-33, COSMOS-2251) | 1,944 / 111 / 592 | classic breakup populations |
| SATCAT full snapshot | **70,355 rows** | unique-ID audit passed; matches growth.csv Cataloged exactly; max CATNR = 100,403 |
| SATCAT growth history | 25,435 daily rows | official series, last row 2026-08-21 |
| Boxscore HTML | — | content sanity passed |
| SOCRATES conjunctions | **148,985** | exact match to live run banner |

**Key structural decisions recorded:**
- Incremental sweep: baseline years cached in `satcat/years/satcat_year_<year>.csv` (fetched once); only current year re-fetched daily (~2 requests/day steady-state).
- On-orbit subset derived in Silver via empty `DECAY_DATE` (no undocumented API hacks).
- OMM JSON only for GP — TLE would silently drop 331+ already-cataloged objects.

### Sample rows for audit (from bronze files)

- GP active, NORAD 100000: `SARAMAGO, epoch 2026-08-21T19:22:27, mean motion 15.20979429, e=0.00093573`
- SOCRATES top row: `STARLINK-34567 [+] vs 60819, TCA 2026-08-23 04:16:59, range 0.016 km, MAX_PROB 1.918E-01`
- growth.csv: `1957-01-01,0,0,0` … `2026-08-21,70355,35487,34868`
- satcat_full first row: `SL-1 R/B,1957-001A,1,R/B,D,CIS,1957-10-04,TYMSC,1957-12-01,…`

### Expected validation targets (live values seen today)

- SOCRATES run current as of 2026 Aug 21 10:16:41 UTC: **148,985 conjunctions** ✓ ingested, exact match
- Public SATCAT snapshot: **70,355 rows** (max catalog number 100,403)
- Official growth series `growth.csv`: **25,435 daily rows** (1957 → 2026-08-21), Cataloged=70,355
- GP active: **16,400 payloads** incl. **331 six-digit IDs** — proves OMM-JSON-only design decision
