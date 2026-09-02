# CI/CD Investigation: `ingest-and-build` Workflow Instability

**Date:** 2026-09-02
**Scope:** Investigation only — no code changes made.
**Workflow:** `.github/workflows/ingest.yml` (daily cron `0 6 * * *`, timeout 45 min)
**Data source:** CelesTrak (celestrak.org) — nonprofit, run by Dr. T.S. Kelso from home infrastructure

---

## 1. Observed behavior (all 11 runs on GitHub Actions)

| Run | Trigger | Result | Duration | Actual start (scheduled 06:00 UTC) |
|-----|---------|--------|----------|------------------------------------|
| 11 | schedule | success | 14.7 min | 09-01 10:51 |
| 10 | schedule | cancelled (45m timeout) | 45.3 min | 08-31 12:17 |
| 9  | schedule | cancelled (45m timeout) | 45.3 min | 08-30 10:57 |
| 8  | schedule | failure | 30.8 min | 08-29 12:01 |
| 7  | schedule | cancelled (45m timeout) | 45.3 min | 08-28 17:56 |
| 6  | schedule | success | 15.3 min | 08-27 17:09 |
| 5  | schedule | failure | 42.2 min | 08-26 06:33 |
| 4  | schedule | success | **612 min (10.2 h)** | 08-25 06:32 |
| 3  | schedule | success | 14.5 min | 08-24 06:39 |
| 2  | workflow_dispatch | success | 14.8 min | 08-23 12:25 |
| 1  | schedule | failure | 14.4 min | 08-23 06:26 |

Every observed error class appears in the logs:

- **Run 8:** mid-SATCAT-sweep → `HTTP Error 403: Forbidden`, then `503`, then `403`; cascade into growth.csv and boxscore.php → 3 datasets FAIL.
- **Run 5:** sweep reached year 2014 (39/70) → `403` × 3 attempts (each burning a 300 s backoff ≈ 10+ min per URL) → cascading FAIL.
- **Run 10:** `Connection timed out (Errno 110)` at TCP level → killed by 45-min timeout.
- **Run 4:** **16 × `503 Service Unavailable`** during sweep; retry/backoff storm stretched a 15-min job to 10+ hours before eventually succeeding.
- **Run 1:** ingestion succeeded; tests failed on a hardcoded path `gp_active_2026-08-22.json`. Already fixed by commit `747c693` (tests now resolve latest bronze file dynamically). Historical, not current.

---

## 2. Root causes (evidence-backed)

### 2.1 The request pattern violates CelesTrak's published usage policy

Source: https://celestrak.org/usage-policy.php (updated 2026-05-22) and
https://celestrak.org/NORAD/documentation/gp-data-formats.php FAQ (updated 2026-06-23).

Each CI run makes **~86 requests from one IP**: 13 GP groups + 70 × `records.php?INTDES=<year>` (SATCAT sweep) + growth.csv + boxscore.php + SOCRATES CSV. The policy explicitly says:

- *"Only download the data you need... **There is no reason to download all of the GROUPs**"* (constellation groups are subsets of `active`).
- *"There is no need to download the list of active satellites **and** the list of all Starlink satellites, since the latter is a subset of the former."* — our pipeline downloads `active` **and** `starlink` **and** every other constellation group.
- JSON is **3× the size** of CSV; they enforce bandwidth because they are a nonprofit on home-tier bandwidth (usage jumped ~125 GB/day → ~330 GB/day in 2026).

### 2.2 Enforced limits (numbers straight from CelesTrak, 2026)

1. **One-download-per-update:** since 2026-03-26 enforced for all users, **starting with `GROUP=active` and `GROUP=starlink`** — the two groups this pipeline downloads first. Second download within a 2-h update window → HTTP 403 with explanation.
2. **Error budget → firewall:** *"we now set a limit on HTTP errors (301, 403, or 404) of **50 in a 2-hour period**, at which point the IP address is sent to the firewall."*
3. **Bandwidth:** >100 MB/day per IP *"you can expect that your IP address may end up in the firewall"*.
4. **HTTP 50x** = *"the server is struggling under heavy load. **Queries need to stop immediately** to allow system recovery."*

### 2.3 Our retry logic is the exact anti-pattern CelesTrak warns against

Policy: *"**M2M software should immediately stop querying when it receives any non-HTTP 200 responses**... Repeatedly ignoring them will end up sending your IP address to the firewall."* And: *"if you receive an HTTP 403 or 404 error, **the response is not going to change by repeating the request** and can result in your IP address being put in the firewall."*

`src/ingestion/fetch_bronze.py` (`_http_get`, lines 80–100):
- Retries 403 three times (with 300 s sleeps), then **continues to the next URL** — converting one throttled request into many errors that push the IP over the 50-errors-in-2h firewall threshold, mid-run.
- This explains why, in runs 5 and 8, once the first 403 appears, **every subsequent request also fails** — the IP got firewalled during the run.
- It also explains the 45-min timeouts: 3 attempts × 300 s backoff ≈ 15 min wasted per blocked URL, and run 4 shows the retry storm extending a job to 10+ hours.

### 2.4 "Connection timed out" = firewall DROP, confirmed by third parties

Blocked IPs don't get a 403 forever — packets are dropped. Third-party CelesTrak client docs (macstarosielec/celestrak): *"Subsequent requests from that IP simply **time out at the TCP level** — they appear as connection timeouts or socket errors rather than as a 429 or 403 response."* Community reports (AllskyTeam/allsky discussion #5119) confirm blocks can persist until the IP changes and that CelesTrak rate limits are "very strict".

This matches run 10's `Errno 110 Connection timed out` exactly.

### 2.5 Why it's *intermittent*: shared egress IPs on GitHub-hosted runners

GitHub-hosted runners are ephemeral Azure VMs drawing from a **shared egress IP pool used by all Actions users**. Consequences:

- Our runs land on a different IP each time — some IPs are hot/blocked (other repos run CelesTrak scrapers from the same pool; CelesTrak firewall-bans are per-IP), some are clean. Success vs 403 is largely **luck of the draw**. This same shared-pool mechanism is documented for GitHub API throttling (d12frosted, "Chasing a GitHub 429 across my Emacs CI", 2026-06-29).
- Blocks auto-clear ~2 h after the offending process stops (per CelesTrak FAQ) — which is why the *next day's* run often succeeds again.

### 2.6 Zero cache persistence in CI multiplies all of the above

`.gitignore` excludes `data/*` (except `data/gold/exports`). The ingestion script's idempotency ("skip if today's file exists", "historical years cached in satcat/years/") assumes a **persistent disk** — but CI is ephemeral. Therefore **every** scheduled run re-downloads everything: the full 70-year SATCAT sweep (~11.7 min of pure politeness delays) plus 13 GP groups. Locally this design is great; in CI it guarantees maximum request volume per run and maximum exposure to throttling.

### 2.7 Cron at exactly `0 6 * * *` — documented GitHub anti-pattern

Official GitHub docs (Events that trigger workflows → `schedule`): *"The `schedule` event **can be delayed during periods of high loads**... **High load times include the start of every hour**... To decrease the chance of delay, schedule your workflow to run at a different time of the hour."*

Observed start drift: 06:26 → 10:51 → 12:17 → **17:56** (nearly 12 h late). This doesn't cause the 403s, but it makes the pipeline unpredictable and can drop queued jobs entirely.

### 2.8 Secondary issue (historical): date-coupled test fixture

Run 1 failed because tests hardcoded `gp_active_2026-08-22.json`. Fixed in `747c693`. Note `tests/test_silver_transforms.py` still requires a fresh GP download to exist in CI (module fixture reads latest bronze GP file) — tests depend on the network step having succeeded.

---

## 3. Recommended CI/CD plan (for discussion — NOT yet implemented)

### A. Make the fetcher policy-compliant (highest impact, smallest change)
1. **Stop immediately on any non-200** (403/404/5xx): no retries on HTTP errors; abort the run, report which URL failed, exit non-zero. One retry max, and only for network-level errors (DNS/reset), never HTTP errors. This single change prevents mid-run firewall escalation and most 45-min timeouts.
2. On 503: stop immediately (per policy), let the next scheduled run try.

### B. Cut request count per run by ~95%
3. **GP: download only `GROUP=active` (+ optionally `stations`) in CSV format** (3× smaller than JSON). Derive starlink/oneweb/kuiper/debris groups locally by filtering `active` (they are strict subsets; SATCAT name/status fields allow debris filtering). 13 requests → 1–2.
4. **SATCAT: commit historical year files (1957…current-1) to the repo once.** Historical years never change; CI then fetches only the current year → 70 requests → 1. This also makes the pipeline honest about its own idempotency design.
5. Total per run: ~3 requests, ~15–20 MB, well inside every documented limit (2-h update cadence, 100 MB/day, 50-error budget).

### C. Make runs fast and independent of luck
6. With B, healthy runs drop from ~15 min to **~3–5 min** (no sweep delays, no bulk GP downloads), comfortably inside the 45-min timeout even with one polite backoff.
7. Add `concurrency: group: ingest` so overlapping runs can't pile up.
8. Consider `actions/cache` for the bronze current-year file as belt-and-braces (optional once B is in place).

### D. Scheduling
9. Move off the top of the hour per GitHub's own advice, e.g. `cron: "37 6 * * *"` (or `13 5 * * *`). Note: CelesTrak does not publish a low-traffic window; their guidance is instead to *download less often and less data* and *"randomize when that occurs (which spreads out the load)"*. A less-popular minute/hour reduces GitHub queue delay; data minimization reduces CelesTrak throttling — both together address the full problem.
10. Keep the daily cadence (well within the 2-h-per-download rule). If fresher SOCRATES data is wanted, a second daily run at a different hour is policy-safe (SOCRATES updates every 10–11 h upstream).

### E. Operational hygiene
11. The ingestion summary already distinguishes FAIL datasets; keep failing loudly and visibly (exit 1, job marked failed) so a human investigates instead of retrying blindly — this is literally what CelesTrak's policy asks M2M users to do.
12. Make the pytest GP fixture tolerant of a missing bronze GP file (skip with clear message) so a data outage doesn't mask test results — or feed tests a small committed fixture instead of live data.

---

## 4. Verification checklist for the eventual fix

- [x] Local run of fetcher with new rules produces ≤ ~30 HTTP requests in `_run_summary.json` (27 verified in CI simulation: 6 GP + 17 rotating historical years + current year + growth + boxscore + SOCRATES)
- [x] Simulated 403 (local mock server) aborts within seconds, exits non-zero, no further URLs queried
- [x] Simulated 503 aborts immediately, no retry
- [x] Simulated unreachable host: 1 transport retry, then whole-run abort (closes the run-10 failure mode)
- [x] CI run completes < 10 min with all sources OK (simulation: fetch 7.7 min + silver 0.1 + gold 0.2 + tests 0.1)
- [x] Historical years rotate: 52 reused from committed cache / 18 fetched (17 rotated + current year); 4 consecutive date buckets cover all 69 years exactly once (verified offline)
- [ ] Schedule start-time drift reduced (observed over ≥ 5 scheduled runs)
- [ ] 14 consecutive green daily runs (2 weeks) before considering the issue closed

---

## 5. Implementation record (2026-09-02)

### Changes made

| File | Change |
|------|--------|
| `src/ingestion/fetch_bronze.py` | `StopQueries` exception hierarchy (`CelesTrakHTTPError`, `CelesTrakTransportError`); `_http_get` never retries HTTP errors and aborts the whole run on them; transport failures retry once (30 s) then abort the run; GP groups trimmed 13 → 6; SATCAT sweep: historical years from committed cache **with a rotating date-keyed refresh slice (`SATCAT_REFRESH_PER_RUN = 20` — full history every 4 runs, stateless)**, current year always fetched fresh into `satcat/` (outside `years/`); `main()` records `abort` in `_run_summary.json`; UA identifies the repo; `pipeline_version` bumped to `bronze-0.2` |
| `.github/workflows/ingest.yml` | cron `0 6 * * *` → `37 6 * * *` (GitHub documents top-of-hour queue delays); added `concurrency: ingest-and-build` (no cancel) |
| `.gitignore` | whitelists `data/bronze/satcat/years/` (69 immutable historical files get committed); current-year file stays ignored by construction (stored outside `years/`) |
| `tests/test_silver_transforms.py` | GP fixture skips with a clear message when no bronze snapshot exists (local dev before first fetch); CI behavior unchanged |
| `README.md`, `technical_reference.md` | group count, cadence table, sweep/cache scheme, fail-fast semantics documented |

### Data decisions (empirically grounded, from 2026-08-22 bronze snapshots)

- **Dropped as exact duplicates of `GROUP=active`:** starlink (10,973/10,973 in active), oneweb (651/651), kuiper (391/391), qianfan (238/238), hulianwang (199/199), geo (568/568). Silver dedups by NORAD ID, so these were pure request overhead.
- **Dropped `stations`:** 20/22 records already in active; the 2 unique objects (CSS elements 49271, 66052) remain in every fact table via SATCAT — they only lose GP enrichment.
- **Kept `analyst` (569 unique, 348 six-digit), `last-30-days` (210, feeds fresh-launch/overflow narrative), and the 3 debris clouds (2,647 unique — populate the globe page's default `Legacy-Debris` regime).**
- Accepted loss vs the old 13-group set: 2 station elements' GP enrichment. Verified: CI simulation produced `analytics_gp_snapshot` = 19,749 rows (predicted old-set-minus-2).

### Deviation from the original estimate

The plan estimated ~3–5 requests/run; after the user-directed increase of the
rotation slice to 20 years/run, the implementation makes **~27** (6 GP + ~17-18
rotated historical years + current year + growth + boxscore + SOCRATES — all
genuinely consumed datasets). Still an ~69% cut from 86 and unambiguously
policy-compliant: every request is a distinct, used dataset, once per day,
paced at 10 s during the sweep. Benefit over the 10-request variant: the full
SATCAT history (decay dates, late cataloging) refreshes every 4 days instead
of never.

### Verification performed

1. `python -m pytest tests -q` — 39 passed (repo).
2. Fail-fast simulation (mock HTTP server in temp, zero real CelesTrak hits):
   - 403 → exactly 1 request seen, run aborted, exit 1, `abort` recorded in manifest
   - 503 → same
   - unreachable host → 1 retry (30 s) then whole-run abort, exit 1
3. Rotation math (offline): 4 consecutive date buckets cover all 69 historical
   years exactly once — no gaps, no overlap; bucket size caps at 20 as history grows.
4. Full CI simulation (temp checkout with only committed SATCAT history + fresh clone semantics):
   - fetch: **27 requests**, bucket 3/4 → 17 rotated years re-fetched, 52 cache-reused,
     current year fresh, 70,532 SATCAT rows, 0 failures
   - silver: 6 s · gold: 12 s (all 12 tables, GP snapshot 19,749 rows) · pytest: 39 passed
4. `git check-ignore` confirms `data/bronze/satcat/satcat_year_2026.csv` is ignored; `git ls-files --others` lists exactly the 69 historical files.

### What the user must do (one-time)

1. Commit the 69 historical year files with the code changes: `git add -A && git commit` (they appear as `?? data/bronze/`).
2. On the next scheduled run (06:37 UTC), confirm the job is green and check the run duration (~10 min expected).
3. Each January: the just-finished year is fetched once into `years/` on the first run — commit that new frozen file (no gitignore edit needed; it's outside the ignore rules by design).

## Sources

- CelesTrak Usage Policy: https://celestrak.org/usage-policy.php
- CelesTrak GP data formats FAQ (blocking mechanics, enforced limits): https://celestrak.org/NORAD/documentation/gp-data-formats.php
- GitHub Docs — `schedule` event delays: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- GitHub Docs — Troubleshooting scheduled workflows: https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
- AllskyTeam/allsky discussion #5119 (community: strict rate limits, persistent IP blocks, IP-change required): https://github.com/AllskyTeam/allsky/discussions/5119
- macstarosielec/celestrak client docs (TCP-timeout signature of firewall blocks, 100 MB/day limit): https://github.com/macstarosielec/celestrak
- d12frosted, "Chasing a GitHub 429 across my Emacs CI" (shared runner egress pool → intermittent destination throttling): https://www.d12frosted.io/posts/2026-06-29-chasing-a-github-429
- juliensimon/space-datasets commits (transient 500/403 pattern on CelesTrak GP endpoints): https://github.com/juliensimon/space-datasets/commit/523e273
