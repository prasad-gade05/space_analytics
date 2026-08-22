# Lessons Learned

## 2026-08-22 — Bronze ingestion (CelesTrak)

1. **Never trust spec URLs without a live probe — even verified ones.** The kickstart's
   `records.php?ONORBIT=TRUE&FORMAT=CSV` was "verified" on 2026-08-21 yet returns
   `Invalid query` live. ONORBIT/PAYLOADS/ACTIVE are flags; records.php requires a real
   selector (`CATNR|INTDES|GROUP|NAME|SPECIAL`). Always smoke-test one request before
   writing bulk logic against an API.
2. **Bulk endpoints can silently cap populations.** `/pub/satcat.csv`, `growth.csv`,
   and pre-2025 `INTDES=<year>` sweeps all stop at legacy catalog numbers < 70000.
   Only exact `CATNR=` lookups and recent-year INTDES queries reach six-digit IDs.
   When three sources agree on a number (70,355), question whether they share a blind
   spot rather than assuming independent confirmation.
3. **"Official total" ≠ row count.** The banner figure "official USSF SATCAT at 100,403"
   is the max catalog number ever assigned (includes the unpublished 7xxxx–9xxxx
   analyst/withheld block). Public queryable rows = 70,355. Read primary-source wording
   carefully before encoding thresholds into validators — my initial MIN=99,000
   hard-fail threshold was wrong because of this misreading.
4. **CelesTrak rate limiting:** ~80 requests in ~15 minutes triggers an IIS-level 403
   block lasting 30+ minutes across the whole site. Keep bulk sweeps at ≥6 s/request,
   add 120 s cooldown on 403, and never run probe loops while a block may be active —
   every hit during a block risks extending it.
5. **Idempotent skip-if-exists pays off immediately.** Because same-day files are
   validated and skipped on rerun, throttling only cost us the SATCAT sweep, not the
   13 GP pulls or SOCRATES download.
6. **Column names must be read from actual responses**, not guessed from docs:
   SOCRATES ships `TCA_RANGE` / `TCA_RELATIVE_SPEED` / `MAX_PROB` — there is no
   `MIN_RANGE_KM` column despite docs describing "minimum range".
7. **Design bulk fetches to be incremental from day one.** Historical launch years
   never gain new objects, so the SATCAT sweep caches each year file on arrival
   (atomic tmp+rename) and only re-fetches the current year daily. Steady-state
   cost: ~2 requests/day instead of 70. A mid-sweep throttle now costs nothing —
   the next run resumes where it stopped.
8. **Buffered stdout hides progress.** Long-running scripts piped through CI or
   shells must set `sys.stdout.reconfigure(line_buffering=True)` (or flush=True)
   and print per-unit progress, or the operator cannot distinguish "hung" from
   "working".
9. **CelesTrak pacing that worked:** ~10 s between requests completed all 70
   year-queries in one pass after a full block expiry; 6 s spacing got cut off
   at ~53 requests earlier the same hour. When blocked, wait quietly 45–60 min;
   do not let retries poke the block.

## 2026-08-22 — HF dataset card YAML

8. **Enum-looking metadata values must be checked against the live official list.**
   `task_categories: tabular` looked plausible but is NOT in Hugging Face's
   task vocabulary (valid: `tabular-classification`, `tabular-regression`,
   `time-series-forecasting`, `other`, ...). HF only *warns* — it does not
   fail the upload — so the bad value shipped silently. Rule: before writing any
   controlled-vocabulary field (task_categories, size_categories, license ids,
   Kaggle license codes), diff the value against the platform's published enum,
   and prefer the honest generic bucket (`other`) over an inexact match.
