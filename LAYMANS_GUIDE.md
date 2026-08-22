# Orbital Commons — The Plain-English Guide

*This document explains the whole project using everyday language first.
Whenever a technical term appears, it is introduced right next to its
plain-English meaning.*

---

## What is this project? (the 30-second version)

Right now, there are tens of thousands of objects flying over your head —
working satellites, spent rocket stages, and pieces of broken junk. A few
organisations watch all of it and publish their measurements for free.
Orbital Commons takes those free measurements and answers three questions:

1. **How crowded is space up there, and where exactly?**
2. **What might crash into what this week, and how likely is it?**
3. **Who is responsible for the mess?**

It does this with an automated data pipeline (software that downloads,
cleans and organises the measurements every night) and an interactive
website (a *Streamlit dashboard*) where anyone can explore the answers.

---

## Why right now? (the numbering crisis)

Every tracked object gets a serial number, called a **NORAD catalog number**
(NORAD = North American Aerospace Defense Command, the US-Canadian military
organisation that has tracked satellites since the 1950s).

For almost 70 years these numbers had **5 digits**, so there could never be
more than 99,999 of them. On **11 July 2026** that limit was hit — an object
named *"SARAMAGO"* received number **100000**. From that day, every newly
cataloged object needs **six digits**.

Here is the problem: the old way of describing a satellite's orbit — a text
format called **TLE** (*Two-Line Element*, two lines of numbers published
since the 1960s) — physically cannot hold six-digit serial numbers. Any
software still reading only TLE files **silently misses every satellite
launched since July 2026**. No error message. Just missing data.

This project saw that coming and reads a modern format instead — **OMM**
(*Orbit Mean-Elements Message*, a JSON-style format without the digit
limit) — which is why our dataset already contains 331+ of the new-era
satellites while older pipelines do not.

Think of it like a car-registration system that ran out of license-plate
combinations: the roads are fine, but every new car would be invisible to
any camera that can only read old plates.

---

## Space traffic 101 (words you will see everywhere)

| Plain English | Technical term | What it means |
|---|---|---|
| Satellite's ID number | **NORAD catalog number** | Serial number assigned when an object is first tracked |
| Orbit description file | **TLE / OMM** | Text formats describing "this object circles Earth roughly like THIS". OMM is the modern one we use |
| Junk | **Debris (DEB)** | Anything broken or dead: exploded parts, dead satellites |
| Spent rocket | **Rocket body (R/B)** | The stage that carried the satellite up, then got left behind |
| Working satellite | **Payload (PAY)** | The useful hardware actually doing a job |
| Two things passing close | **Conjunction** | A forecast moment when two objects will be near each other |
| Crash likelihood | **Pc (probability of collision)** | Number between 0 and 1; 0.19 on our data means "19% chance" |
| Where it is right now | **SGP4 propagation** | A standard maths recipe that turns the orbit description into positions in space |
| Map coordinates | **TEME / WGS84 geodetic** | TEME = space-fixed 3D axes; WGS84 = normal latitude/longitude/altitude like your phone's GPS uses |
| Height slice of space | **Altitude band / shell** | Space divided into 25-km-tall layers, like floors of a building |
| Ownership concentration | **HHI** (Herfindahl-Hirschman Index) | One number saying "is this floor shared by many players or run by one giant?" (0 = everyone equal, 1 = one player owns all) |
| Fairness of the mess | **Gini coefficient** | Same idea used for income inequality, applied to junk: 0 = debris spread evenly across nations, 1 = one nation holds everything |
| Grouping similar things | **K-Means clustering** | An algorithm that automatically sorts bands into groups like Quiet / Busy / Critical |
| Predicting the future from history | **ARIMA** | A classical statistics method that extends a time trend forward |

---

## How the data flows (from raw download to dashboard)

Imagine running a restaurant:

1. **Bronze = groceries as bought.** We download CelesTrak's files *exactly
   as served* — untouched, timestamped, fingerprinted with a SHA-256 checksum
   (a unique digital fingerprint used to detect any corruption).
   *Technical:* `data/bronze/`, byte-faithful storage + manifest JSONs.

2. **Silver = washed, chopped, weighed.** Every object's orbit is run through
   SGP4 to get real positions; bad records are flagged, not thrown away;
   each object gets sorted into altitude bands; duplicate entries collapse
   to the freshest measurement.
   *Technical:* `data/silver/*.parquet` — typed tables + validation gates.

3. **Gold = plated dishes.** Everything is organised into a star schema — a
   database layout with dimension tables ("who/what/where" lookup lists) and
   fact tables ("things that happened", one row per event) inside DuckDB,
   a fast analytical database. This shape is what makes dashboards fast.
   *Technical:* `data/gold/orbital.duckdb` + Parquet exports committed to git.

A free GitHub robot (**GitHub Actions CI/CD**) repeats steps 1–3 every night,
so the website always shows fresh numbers.

---

## A tour of the website, page by page

- **Mission Control** — the front page. Big numbers at the top (how many
  objects, how much junk), today's single scariest close approach, and how
  the catalog keeps growing.
- **Conjunction Radar** — every forecast near-miss for the coming week as a
  cloud of dots: left = closer, higher = more dangerous. Filters let you
  zoom into one altitude class or probability level.
- **Congestion Atlas** - space as a high-rise building: which 25 km "floor"
  is most crowded, who dominates it (ownership concentration), and which
  floors the algorithm rated *Critical*.
- **League Tables** — countries ranked by payloads vs junk, with an
  inequality curve showing whether debris responsibility is shared fairly.
- **Catalog Crisis** — the numbering story told in charts: three eras of
  catalog numbers, daily growth, and a statistical forecast of when the
  public catalog itself approaches the next milestone.
- **Orbit Explorer 3D** — a globe showing where objects were when last
  measured, plus a 3D view of their actual orbital rings.
- **Explorer** — ready-made database questions (no SQL knowledge needed),
  each returning a table you can download as CSV.
- **Methodology** — the receipts: how every number is computed, error rates,
  and the honest limitations.

---

## What we actually found (so far)

- **One neighbourhood owns the danger.** The two altitude bands around
  450–500 km — where Starlink flies — contain about **13% of all objects but
  63% of all forecast close approaches**. The ownership-concentration score
  there is ~0.92, close to a monopoly.
- **Junk is not evenly shared.** The Gini curve shows a handful of states
  account for most of the on-orbit debris, echoing historical breakups
  (anti-satellite tests, accidental collisions).
- **Most warnings are routine.** Of ~149,000 screened events in a week, only
  54 have a collision probability above 1%. The sky is crowded, not falling —
  but the tail matters, because a single 14 km/s hit multiplies into
  thousands of new fragments.
- **The hidden catalog is real.** Officially ~100,403 numbers have been
  handed out, yet only ~70,355 objects are publicly listed. The difference —
  a reserved block of numbers never made public — is visible in our data as
  a jump straight past 69,999 to six-digit IDs.

---

## Honest limitations

- Public sources cover roughly 70k objects row-by-row; the withheld block
  (~30k numbers) is counted only in totals, not itemised anywhere public.
- Conjunction forecasts reflect **one weekly screening run** — not a
  historical archive of past conjunctions.
- Our re-computed collision probabilities use simplified assumptions
  (spherical objects, round uncertainty clouds). They are benchmarks against
  the official numbers, not replacements for operator-grade analysis.
- Forecasts extrapolate trends; they cannot predict new wars, new mega-
  constellations, or new explosions.

---

## FAQ

**Is this real data?**
Yes — CelesTrak (a non-profit run by Dr. T.S. Kelso) republishes the US
military's public tracking data. NASA publishes benchmark statistics we use
to sanity-check ours. Both are cited on the Methodology page.

**Can I use the cleaned data myself?**
Yes. `make package` builds a folder of ready-to-use Parquet files with a
readme card, licensed CC-BY-4.0 (use freely, attribute CelesTrak and us).

**Why does this matter for jobs/interviews beyond space?**
The engineering pattern — raw ingestion, validation gates, star schema,
forecasting, dashboards, automated CI — is identical to what banks, retailers
and logistics firms do with their own operational data. Space just makes the
story memorable.
