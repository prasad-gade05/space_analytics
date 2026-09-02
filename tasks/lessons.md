# Lessons Learned

## 2026-09-02 — CI/CD (CelesTrak throttling in GitHub Actions)

1. **Idempotency designed for a persistent disk silently breaks in CI.** The
   "cache once, reuse forever" SATCAT sweep assumed the cache survives between
   runs; gitignored data dirs mean every CI run re-downloads everything
   (86 requests/run). Lesson: any cache that must survive across runs on
   ephemeral CI has to be committed, cached via actions/cache, or rebuilt
   cheaply — "skip-if-exists" alone is not idempotency in CI.
2. **Fail fast is the policy, not a preference.** CelesTrak firewall-bans IPs
   sending > 50 HTTP errors in 2 h; retrying 403s 3× per URL and then
   continuing to the next URL converts one throttle into a site-wide ban
   mid-run. M2M rule adopted: any non-200 → abort whole run, report, exit 1.
   Unreachable host (connect timeout) after 1 retry also aborts — that is the
   signature of a firewall DROP, and crawling URL-by-URL is what caused the
   45-minute CI timeouts (and one 612-minute run).
3. **Shared egress IP pools make destination throttling intermittent.**
   GitHub-hosted runners share Azure egress IPs with every other Actions user;
   whether a run lands on a clean or blocked IP is luck. Intermittent 403s
   against a data source from CI are usually not your request count alone.
4. **Top-of-hour crons are a documented GitHub delay trap.** Schedule at an
   off-minute (`37 6 * * *`) — observed start drift reached 06:26→17:56 with
   `0 6 * * *`.
5. **Verify subset relationships empirically before optimizing fetches.**
   The 6 dropped GP groups were proven strict subsets of `GROUP=active` by
   diffing same-date bronze snapshots (0 missing records) — not by trusting
   group descriptions. Also check dashboard consumers (the 3D globe's
   `Legacy-Debris` regime depends on debris-cloud GP records) before cutting.
6. **PowerShell `Copy-Item -Recurse src dest` into an existing dir nests
   (`dest\src`) instead of merging.** A verification run then silently
   executes stale code. Remove the destination first, or use
   `robocopy /MIR`; always assert the copied content contains the change
   under test (e.g. grep for the new symbol) before running.

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
