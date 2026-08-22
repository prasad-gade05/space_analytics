"""Bronze-layer raw ingestion for Orbital Commons.

Downloads pristine raw files from CelesTrak into data/bronze/.
Idempotent: filenames are date-stamped and same-day files that already
exist are skipped unless --force is passed. Raw bytes are stored exactly
as served; strict schema enforcement happens downstream in Silver.

Design decisions (documented per kickstart spec Section 2):
- GP data ingested as OMM JSON only. Legacy TLE cannot represent catalog
  numbers above 99999, mandatory since 2026-07-11 (catalog > 100,000).
- Full SATCAT snapshot built via the documented records.php?INTDES=<year>
  sweep (1957..current year): /pub/satcat.csv is capped at legacy catalog
  numbers < 70000 and misses the post-overflow population.
- Official growth baseline ingested from /satcat/growth.csv. It also only
  counts legacy-numbered objects (< 70000); the divergence from the real
  catalog size IS the catalog-overflow crisis, quantified.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRONZE_DIR = REPO_ROOT / "data" / "bronze"

USER_AGENT = "OrbitalCommons-BronzeIngest/0.1 (local development)"
REQUEST_TIMEOUT_S = 180
RETRIES = 3
RETRY_BACKOFF_S = 15
THROTTLE_BACKOFF_S = 300      # CelesTrak throttles bursts with 403s; long cooldown
POLITE_DELAY_S = 3
SATCAT_SWEEP_DELAY_S = 10     # first-run historical sweep pacing

GP_BASE = "https://celestrak.org/NORAD/elements/gp.php"
SATCAT_RECORDS_BASE = "https://celestrak.org/satcat/records.php"
SATCAT_GROWTH_URL = "https://celestrak.org/satcat/growth.csv"
BOXSCORE_URL = "https://celestrak.org/satcat/boxscore.php"
SOCRATES_CSV_URL = "https://celestrak.org/SOCRATES/sort-minRange.csv"

# Slugs verified against https://celestrak.org/NORAD/elements/ on 2026-08-22.
GP_GROUPS: dict[str, str] = {
    "active": "All active payloads (core dataset)",
    "analyst": "Analyst satellites (8xxxx / 27xxxx ranges)",
    "starlink": "Starlink constellation",
    "oneweb": "OneWeb/Eutelsat constellation",
    "kuiper": "Amazon Kuiper constellation",
    "qianfan": "Qianfan (Thousand Sails) constellation",
    "hulianwang": "Hulianwang Digui (Guowang) constellation",
    "stations": "Space stations",
    "geo": "Active geosynchronous satellites",
    "last-30-days": "Last 30 days launches",
    "fengyun-1c-debris": "FENGYUN 1C ASAT test debris",
    "iridium-33-debris": "Iridium 33 collision debris",
    "cosmos-2251-debris": "Cosmos 2251 collision debris",
}

# Hard-fail thresholds derived from live figures observed 2026-08-22.
MIN_GP_ACTIVE_RECORDS = 10_000
# Public CelesTrak SATCAT = 70,355 rows on 2026-08-22. The widely quoted
# "official SATCAT at 100,403" is the max catalog NUMBER ever assigned
# (incl. ~30k unpublished 7xxxx-9xxxx analyst/withheld entries), not the
# public row count. Fail hard only well below the observed population.
MIN_SATCAT_FULL_ROWS = 68_000
MIN_GROWTH_ROWS = 20_000       # daily series since 1957 (~25.4k rows live)
MIN_SOCRATES_ROWS = 100_000    # 148,985 conjunctions in run of 2026-08-21

REQUIRED_OMM_KEYS = {"OBJECT_NAME", "NORAD_CAT_ID", "EPOCH"}
GROWTH_HEADER = {"date", "cataloged", "decayed", "on orbit"}


def _http_get(url: str) -> bytes:
    """GET a URL with retries; long cooldown on HTTP 403 (rate-limit)."""
    last_err: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(url, resp.status, "non-200", resp.headers, None)
                return resp.read()
        except urllib.error.HTTPError as err:
            last_err = err
            print(f"    attempt {attempt}/{RETRIES} failed: {err}")
            if attempt < RETRIES:
                time.sleep(THROTTLE_BACKOFF_S if err.code in (403, 429) else RETRY_BACKOFF_S)
        except Exception as err:  # noqa: BLE001 - retry any transport failure
            last_err = err
            print(f"    attempt {attempt}/{RETRIES} failed: {err}")
            if attempt < RETRIES:
                time.sleep(RETRY_BACKOFF_S * attempt)
    raise RuntimeError(f"All {RETRIES} attempts failed for {url}") from last_err


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _save_raw(subdir: Path, filename: str, payload: bytes) -> Path:
    subdir.mkdir(parents=True, exist_ok=True)
    out_path = subdir / filename
    out_path.write_bytes(payload)
    return out_path


def _entry(dataset: str, description: str, url: str, payload: bytes | None,
           out_path: Path | None, records: int | None, warning: str) -> dict:
    ok = payload is not None and out_path is not None
    return {
        "dataset": dataset,
        "description": description,
        "source_url": url,
        "file": str(out_path.relative_to(REPO_ROOT)) if out_path else None,
        "bytes": len(payload) if payload else 0,
        "sha256": _sha256(payload) if payload else None,
        "records": records,
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": ("OK" if not warning else "WARN") if ok else "FAIL",
        "warning": warning,
    }


def _fail_entry(dataset: str, description: str, url: str, err: Exception) -> dict:
    entry = _entry(dataset, description, url, None, None, 0, "")
    entry["status"] = "FAIL"
    entry["warning"] = str(err)
    return entry


def _validate_gp_json(payload: bytes, group: str) -> tuple[int, str]:
    """Parse OMM JSON, verify structure, return (record_count, warning|'')."""
    records = json.loads(payload.decode("utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"gp/{group}: expected JSON array, got {type(records).__name__}")
    warning = ""
    if len(records) == 0:
        warning = f"gp/{group}: zero records returned"
    missing = REQUIRED_OMM_KEYS - set(records[0].keys()) if records else set()
    if missing:
        raise ValueError(f"gp/{group}: first record missing required OMM keys: {sorted(missing)}")
    cat_ids = [int(r["NORAD_CAT_ID"]) for r in records]
    if len(set(cat_ids)) != len(cat_ids):
        dup_count = len(cat_ids) - len(set(cat_ids))
        raise ValueError(f"gp/{group}: {dup_count} duplicate NORAD_CAT_ID values")
    if group == "active" and len(cat_ids) < MIN_GP_ACTIVE_RECORDS:
        raise ValueError(f"gp/active: {len(cat_ids):,} records < minimum {MIN_GP_ACTIVE_RECORDS:,}")
    six_digit = sum(1 for cid in cat_ids if cid >= 100_000)
    if six_digit:
        warning += f"{six_digit} six-digit IDs present (post-overflow era)"
    return len(records), warning


def _csv_rows_and_header(payload: bytes) -> tuple[int, list[str]]:
    text = payload.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    rows = sum(1 for _ in reader)
    return rows, [h.strip().lower() for h in header]


def ingest_gp(today: str, force: bool) -> list[dict]:
    results: list[dict] = []
    subdir = BRONZE_DIR / "gp"
    for group, description in GP_GROUPS.items():
        url = f"{GP_BASE}?GROUP={group}&FORMAT=JSON"
        filename = f"gp_{group}_{today}.json"
        existing = subdir / filename
        if existing.exists() and not force:
            try:
                cached = existing.read_bytes()
                _, warning = _validate_gp_json(cached, group)
                record_count = len(json.loads(cached))
                print(f"[gp] GROUP={group}: cached file valid, skipping download")
                results.append(_entry(f"gp_{group}", description, url,
                                      cached, existing, record_count, warning))
                continue
            except Exception as err:  # noqa: BLE001
                print(f"[gp] GROUP={group}: cached file invalid ({err}), re-fetching")
        print(f"[gp] downloading GROUP={group} ...")
        try:
            payload = _http_get(url)
            record_count, warning = _validate_gp_json(payload, group)
            out_path = _save_raw(subdir, filename, payload)
            results.append(_entry(f"gp_{group}", description, url, payload, out_path,
                                  record_count, warning))
            print(f"    -> {record_count:,} records ({len(payload):,} bytes)"
                  f"{(' WARN: ' + warning) if warning else ''}")
        except Exception as err:  # noqa: BLE001
            results.append(_fail_entry(f"gp_{group}", description, url, err))
            print(f"    -> FAIL: {err}")
        time.sleep(POLITE_DELAY_S)
    return results


def ingest_satcat_full_sweep(today: str, force: bool) -> dict:
    """Build the complete SATCAT snapshot incrementally.

    Historical years (1957..current-1) never gain new objects: each is
    fetched once and cached under satcat/years/, then reused on every run.
    Only the current year is re-fetched (new catalogs + decay updates),
    and only if not already fetched today. Every year is persisted to disk
    the moment it arrives, so a mid-sweep failure resumes cheaply.
    Pass --force to refresh historical years.
    """
    dataset = "satcat_full"
    description = (
        "Complete SATCAT snapshot assembled from documented "
        "records.php?INTDES=<year>&FORMAT=CSV queries. Historical years are "
        "cached in satcat/years/ after first fetch; current year refreshed "
        "daily. /pub/satcat.csv was rejected: capped at legacy IDs < 70000."
    )
    current_year = datetime.now(timezone.utc).year
    years = list(range(1957, current_year + 1))
    subdir = BRONZE_DIR / "satcat"
    years_dir = subdir / "years"
    filename = f"satcat_full_{today}.csv"
    existing = subdir / filename

    if existing.exists() and not force:
        try:
            row_count, header = _csv_rows_and_header(existing.read_bytes())
            if row_count >= MIN_SATCAT_FULL_ROWS and "norad_cat_id" in header:
                print(f"[satcat] satcat_full: today's snapshot already valid "
                      f"({row_count:,} rows), skipping sweep")
                entry = _entry(dataset, description,
                               f"{SATCAT_RECORDS_BASE}?INTDES=<1957..{current_year}>&FORMAT=CSV",
                               existing.read_bytes(), existing, row_count, "")
                return entry
            print("[satcat] satcat_full: cached file invalid, re-running sweep")
        except Exception as err:  # noqa: BLE001
            print(f"[satcat] satcat_full: cached file invalid ({err}), re-running sweep")

    print(f"[satcat] running incremental year sweep ({years[0]}..{years[-1]}, "
          f"{len(years)} years) ...")
    parts: list[bytes] = []
    header_line: bytes | None = None
    total_rows = 0
    fetched_now: list[int] = []
    from_cache: list[int] = []
    try:
        for i, year in enumerate(years, 1):
            is_current = (year == current_year)
            year_file = years_dir / f"satcat_year_{year}.csv"
            cache_fresh_today = (
                year_file.exists()
                and datetime.fromtimestamp(year_file.stat().st_mtime, timezone.utc)
                .date().isoformat() == today
            )
            use_cache = not force and year_file.exists() and (
                not is_current or cache_fresh_today
            )
            if use_cache:
                payload = year_file.read_bytes()
                source = "cache"
                from_cache.append(year)
            else:
                url = f"{SATCAT_RECORDS_BASE}?INTDES={year}&FORMAT=CSV"
                payload = _http_get(url)
                years_dir.mkdir(parents=True, exist_ok=True)
                tmp = year_file.with_suffix(".tmp")
                tmp.write_bytes(payload)
                tmp.replace(year_file)  # atomic-ish persist as we go
                source = "FETCHED"
                fetched_now.append(year)
                time.sleep(SATCAT_SWEEP_DELAY_S)

            lines = payload.splitlines(keepends=True)
            body = b"".join(lines[1:]) if lines else b""
            if header_line is None and lines:
                header_line = lines[0]
            n_rows = max(0, len(lines) - 1)
            total_rows += n_rows
            parts.append(body)
            print(f"    [{i:>2}/{len(years)}] {year}: {n_rows:>5,} rows "
                  f"({source}, running total {total_rows:,})")

        if header_line is None:
            raise ValueError("sweep returned no data at all")
        if total_rows < MIN_SATCAT_FULL_ROWS:
            raise ValueError(f"sweep yielded {total_rows:,} rows < minimum {MIN_SATCAT_FULL_ROWS:,}")

        combined = header_line + b"".join(parts)
        # structural uniqueness audit: NORAD_CAT_ID must be unique across years
        reader = csv.reader(io.StringIO(combined.decode("utf-8")))
        header = next(reader)
        id_idx = next(i for i, h in enumerate(header) if h.strip().lower() == "norad_cat_id")
        ids = [row[id_idx] for row in reader if row]
        duplicates = len(ids) - len(set(ids))
        if duplicates:
            raise ValueError(f"{duplicates} duplicate NORAD_CAT_ID values across sweep")

        out_path = _save_raw(subdir, filename, combined)
        entry = _entry(dataset, description,
                       f"{SATCAT_RECORDS_BASE}?INTDES=<1957..{current_year}>&FORMAT=CSV",
                       combined, out_path, total_rows, "")
        entry["years_fetched_now"] = len(fetched_now)
        entry["years_from_cache"] = len(from_cache)
        print(f"    -> {total_rows:,} rows ({len(combined):,} bytes); "
              f"fetched {len(fetched_now)} years now, reused {len(from_cache)} cached")
        return entry
    except Exception as err:  # noqa: BLE001
        print(f"    -> FAIL: {err}")
        return _fail_entry(dataset, description,
                           f"{SATCAT_RECORDS_BASE}?INTDES=<1957..{current_year}>&FORMAT=CSV", err)


def ingest_satcat_extras(today: str, force: bool) -> list[dict]:
    results: list[dict] = []
    subdir = BRONZE_DIR / "satcat"

    jobs = [
        {
            "dataset": "satcat_growth_history",
            "url": SATCAT_GROWTH_URL,
            "filename": f"satcat_growth_history_{today}.csv",
            "note": ("Official CelesTrak daily growth series (Date, Cataloged, Decayed, "
                     "On Orbit). Counts only legacy catalog numbers < 70000."),
            "validator": lambda p: _validate_growth(p),
        },
        {
            "dataset": "boxscore",
            "url": BOXSCORE_URL,
            "filename": f"boxscore_{today}.html",
            "note": "By-country payload/debris boxscore (validation/citation).",
            "validator": lambda p: _validate_boxscore(p),
        },
    ]
    for job in jobs:
        out_path = subdir / job["filename"]
        if out_path.exists() and not force:
            try:
                _, warning = job["validator"](out_path.read_bytes())
                print(f"[satcat] {job['dataset']}: cached file valid, skipping download")
                results.append(_entry(job["dataset"], job["note"], job["url"],
                                      out_path.read_bytes(), out_path, None, warning))
                continue
            except Exception as err:  # noqa: BLE001
                print(f"[satcat] {job['dataset']}: cached file invalid ({err}), re-fetching")
        print(f"[satcat] downloading {job['dataset']} ...")
        try:
            payload = _http_get(job["url"])
            _, warning = job["validator"](payload)
            saved = _save_raw(subdir, job["filename"], payload)
            results.append(_entry(job["dataset"], job["note"], job["url"], payload, saved,
                                  None, warning))
            print(f"    -> {len(payload):,} bytes{(' WARN: ' + warning) if warning else ''}")
        except Exception as err:  # noqa: BLE001
            results.append(_fail_entry(job["dataset"], job["note"], job["url"], err))
            print(f"    -> FAIL: {err}")
        time.sleep(POLITE_DELAY_S)
    return results


def _validate_growth(payload: bytes) -> tuple[int, str]:
    rows, header = _csv_rows_and_header(payload)
    if set(header[:4]) != GROWTH_HEADER:
        raise ValueError(f"growth.csv unexpected header: {header}")
    if rows < MIN_GROWTH_ROWS:
        raise ValueError(f"growth.csv {rows:,} rows < minimum {MIN_GROWTH_ROWS:,}")
    return rows, ""


def _validate_boxscore(payload: bytes) -> tuple[int, str]:
    text = payload.decode("utf-8", errors="replace")
    lowered = text.lower()
    if "boxscore" not in lowered or len(payload) < 5_000:
        raise ValueError("boxscore HTML failed content sanity check")
    return None, ""


def ingest_socrates(today: str, force: bool) -> list[dict]:
    dataset = "socrates_conjunctions"
    description = "Latest SOCRATES Plus run, sorted by minimum range (RFC 4180 CSV)"
    subdir = BRONZE_DIR / "socrates"
    filename = f"socrates_conjunctions_{today}.csv"

    def validate(payload: bytes) -> tuple[int, str]:
        rows, header = _csv_rows_and_header(payload)
        required = ["norad_cat_id_1", "norad_cat_id_2", "tca", "max_prob"]
        for pattern in required:
            if not any(pattern in h for h in header):
                raise ValueError(f"SOCRATES header missing '{pattern}'. Got: {header}")
        if rows < MIN_SOCRATES_ROWS:
            raise ValueError(f"socrates: {rows:,} rows < minimum {MIN_SOCRATES_ROWS:,}")
        return rows, ""

    out_path = subdir / filename
    if out_path.exists() and not force:
        try:
            rows, warning = validate(out_path.read_bytes())
            print(f"[socrates] cached file valid ({rows:,} rows), skipping download")
            return [_entry(dataset, description, SOCRATES_CSV_URL, out_path.read_bytes(),
                           out_path, rows, warning)]
        except Exception as err:  # noqa: BLE001
            print(f"[socrates] cached file invalid ({err}), re-fetching")

    print("[socrates] downloading bulk conjunction CSV ...")
    results: list[dict] = []
    try:
        payload = _http_get(SOCRATES_CSV_URL)
        rows, warning = validate(payload)
        saved = _save_raw(subdir, filename, payload)
        results.append(_entry(dataset, description, SOCRATES_CSV_URL, payload, saved,
                              rows, warning))
        print(f"    -> {rows:,} conjunctions ({len(payload):,} bytes)")
    except Exception as err:  # noqa: BLE001
        results.append(_fail_entry(dataset, description, SOCRATES_CSV_URL, err))
        print(f"    -> FAIL: {err}")
    return results


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    force = "--force" in sys.argv[1:]
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    print(f"=== Orbital Commons Bronze ingestion — {now.isoformat(timespec='seconds')} ===\n")

    all_results = (
        ingest_gp(today, force)
        + [ingest_satcat_full_sweep(today, force)]
        + ingest_satcat_extras(today, force)
        + ingest_socrates(today, force)
    )

    failures = [r for r in all_results if r["status"] == "FAIL"]
    warns = [r for r in all_results if r["status"] == "WARN"]

    manifest = {
        "run_started_at_utc": now.isoformat(timespec="seconds"),
        "pipeline_version": "bronze-0.1",
        "schema_version": "omm-json-1.0 + satcat-csv-1.0 + growth-csv-1.0 + socrates-csv-rfc4180",
        "force": force,
        "results": all_results,
        "totals": {
            "sources_attempted": len(all_results),
            "ok": len(all_results) - len(failures) - len(warns),
            "warn": len(warns),
            "fail": len(failures),
            "total_bytes": sum(r["bytes"] for r in all_results),
            "total_records": sum(r["records"] or 0 for r in all_results),
        },
    }

    summary_path = BRONZE_DIR / "_run_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for layer, datasets in (
        ("gp", lambda d: d.startswith("gp_")),
        ("satcat", lambda d: d.startswith(("satcat_", "boxscore"))),
        ("socrates", lambda d: d.startswith("socrates_")),
    ):
        layer_entries = [r for r in all_results if r["file"] and datasets(r["dataset"])]
        if layer_entries:
            manifest_path = BRONZE_DIR / layer / f"manifest_{today}.json"
            manifest_path.write_text(json.dumps(layer_entries, indent=2), encoding="utf-8")
            print(f"manifest written: {manifest_path.relative_to(REPO_ROOT)}")

    t = manifest["totals"]
    print("\n=== RUN SUMMARY ===")
    print(f"sources: {t['ok']} ok / {t['warn']} warn / {t['fail']} fail")
    print(f"total:   {t['total_records']:,} records, {t['total_bytes']:,} bytes")
    if warns:
        print("warnings:")
        for r in warns:
            print(f"  - {r['dataset']}: {r['warning']}")
    if failures:
        print("FAILURES:")
        for r in failures:
            print(f"  - {r['dataset']}: {r['warning']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
