# Orbital Commons

**Global satellite traffic, congestion and conjunction-risk analytics on the live
public space catalog — Medallion architecture (Bronze → Silver → Gold in DuckDB),
SGP4 orbital propagation, and a Streamlit mission console.**

Built entirely on free, ungated sources: [CelesTrak](https://celestrak.org/)
(GP/SATCAT/SOCRATES, nonprofit) with validation benchmarks from NASA ODQN.
No accounts, no API keys — clone and run.

## Why this is interesting right now

- **The catalog overflow crisis.** On 2026-07-11 the 5-digit NORAD catalog number
  space ran out ("SARAMAGO", ID 100000). Legacy TLE _cannot represent_ the new
  six-digit IDs, so every TLE-based pipeline silently drops newly cataloged
  satellites. This project ingests **OMM JSON/CSV only**, so the 331+ six-digit-ID
  objects already tracked appear in every layer. The dashboard quantifies the gap:
  official counter **100,403** vs ~70k publicly queryable records (the unpublished
  7xxxx–9xxxx block).
- **LEO congestion, measured.** The 450–500 km bands hold >9,000 objects at HHI ≈
  0.92 — a near-monopoly operator signature. Debris inequality across nations is
  Gini-scored; conjunction load by regime comes straight from SOCRATES's weekly
  screen (~149k events, refreshed ~3×/day upstream).
- **Physics, not vibes.** Every object is propagated with SGP4 and transformed
  TEME→WGS84 via Skyfield; the top-N riskiest encounters are re-scored with our own
  Foster/Chan 2D collision-probability integrator and benchmarked against
  SOCRATES's reported Pc.

## Architecture

```
CelesTrak GP (OMM JSON, 13 groups)   ┐
SATCAT full snapshot (year sweep)    ├─▶ Bronze  data/bronze/   raw bytes + sha256 manifests
SOCRATES bulk CSV + growth.csv       ┘
        │
        ▼  Alpha-5 codec · dedup · SGP4@epoch · TEME→geodetic · validation gates · shells
Silver  data/silver/*.parquet          (+ _quality_report.json)
        │
        ▼  star schema: 4 dims + 4 facts + Foster top-N benchmark
Gold    data/gold/orbital.duckdb  +  data/gold/exports/*.parquet (committed)
        │
        ▼
Streamlit console (8 pages)  ·  pytest suite  ·  nightly GitHub Actions refresh
```

## Quickstart

```bash
pip install -r requirements.txt
make all          # bronze → silver → gold → tests
make dashboard    # streamlit run src/visualization/app.py
```

Windows without make:

```bash
python src/ingestion/fetch_bronze.py
python -m src.pipeline.run_silver
python -m src.modeling.build_gold
python -m pytest tests -q
streamlit run src/visualization/app.py
```

## Data sources & usage policy

| Source              | Endpoint                                                  | Cadence here                             |
| ------------------- | --------------------------------------------------------- | ---------------------------------------- |
| GP orbital elements | `celestrak.org/NORAD/elements/gp.php?GROUP=…&FORMAT=JSON` | daily                                    |
| SATCAT snapshot     | `records.php?INTDES=<year>&FORMAT=CSV` sweep (1957→now)   | baseline cached once; current year daily |
| SOCRATES Plus       | `celestrak.org/SOCRATES/sort-minRange.csv`                | each run (~3×/day upstream)              |
| Growth history      | `celestrak.org/satcat/growth.csv`                         | daily                                    |
| Boxscore            | `celestrak.org/satcat/boxscore.php`                       | daily                                    |

All use of CelesTrak follows their published usage policy (identified User-Agent,
polite pacing ≥3 s, incremental caching). Space-Track.org and ESA DISCOS were
evaluated and deliberately dropped — see `technical_reference.md`.

## Repository map

```
src/
├── ingestion/fetch_bronze.py     # idempotent raw fetcher (skip-if-exists per day)
├── transformation/               # silver: silver_gp, silver_datasets, shells
├── analytics/metrics.py          # HHI, Gini, Foster/Chan Pc (pure functions)
├── modeling/                     # gold: operators curation + star-schema builder
├── pipeline/run_silver.py        # orchestrator + quality report
├── utils/                        # paths, Alpha-5 codec
└── visualization/                # figures.py (pure) + app.py (Streamlit)
tests/                            # 29 checks: codecs, physics, metrics, figures
tasks/todo.md, tasks/lessons.md   # build log and self-correction notes
technical_reference.md            # schemas, formulas, assumptions, findings
```
