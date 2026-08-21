# Verification Report — Space Tracking & Orbital Debris Claims

**Date of verification:** August 21, 2026
**Method:** Direct fetch of primary-source pages (Space-Track.org documentation, PyPI, GitHub, NASA JSC Orbital Debris, ESA DISCOS, astropy/skyfield docs) plus corroborating web searches. Nothing below was confirmed without a direct quote from a primary source actually viewed.

---

## Claim 1 — Space-Track.org access is gated (not open); User Agreement required; approval can take days; efficient API usage policy

**Status: VERIFIED**

**Primary sources:**
- https://www.space-track.org/ (login page, archived: web.archive.org/web/20090107014138/http://space-track.org/)
- https://www.space-track.org/documentation
- https://www.space-track.org/auth/createAccount
- https://www.space-track.org/documents/USSTRATCOM_ODR_v09.2_JFSCC.pdf

**Confirming excerpts:**

National Security Restrictions + approved registered user (archived login page):
> "Due to existing National Security Restrictions pertaining to access of and use of U.S. Government-provided information and data, all users accessing this web site must be an approved registered user to access data on this site."
> "Users with a established account select this option to access the website. By logging in to the site, you accept and agree to the terms of the User Agreement"

User Agreement requirement (createAccount page):
> "I have read the User Agreement"

Approval lead time (ODR instructions PDF):
> "Please allow 30 days from the date of [submission]"

Efficient-query usage policy (https://www.space-track.org/documentation, "Retrieval Strategy"):
> "Do not send hundreds of individual /class/gp/ or /class/satcat/ queries to space-track.org with one request per satellite. Instead, use the API as efficiently as possible to minimuze the number of requests, combining queries for multiple objects using a comma-delimited list where appropriate."

**Notes:** The claim says "approval can take days" — the ODR document actually specifies up to 30 days for routine requests, so the claim is conservative. The core gating + User Agreement + efficiency-policy sub-claims are all directly confirmed. (Minor: the live page contains the typo "minimuze" verbatim.)

---

## Claim 2 — Space-Track API base, docs URL, auth via POST to ajaxauth/login, basicspacedata query path pattern

**Status: VERIFIED**

**Primary sources:**
- https://www.space-track.org/documentation (official help page)
- https://spacetrack.readthedocs.io/en/stable/_modules/spacetrack/base.html (official Python client source)
- https://apis.io/apis/spacetrack/spacetrack-authentication-api/ (OpenAPI spec)

**Confirming excerpts:**

API base + documentation URL (https://www.space-track.org/documentation):
> "Space-Track.org's Application Programming Interface (API) allows users to access data on this site programmatically using custom, stable URLs with configurable parameters. This API conforms to the general principles of a design called Representational State Transfer or 'REST'..."

Query path pattern — example URLs shown directly on the documentation page:
> "https://www.space-track.org/basicspacedata/query/class/gp/norad_cat_id/25544/format/tle"
> "https://www.space-track.org/basicspacedata/query/class/gp/NORAD_CAT_ID/100000--339999/format/tle/emptyresult/show"
> "https://www.space-track.org/basicspacedata/query/class/boxscore/format/html"

Auth via POST to ajaxauth/login (official `spacetrack` Python client source):
```python
data = {"identity": self.identity, "password": self.password}
resp = yield NormalRequest(
    self.client.build_request("POST", "ajaxauth/login", data=data)
)
```

OpenAPI spec confirmation:
> "All API requests require a valid session cookie obtained by POSTing credentials to /ajaxauth/login."
> url: "https://www.space-track.org/ajaxauth/login"
> body: "identity=user%40example.com&password=yourpassword"

Classes confirmed on the documentation page: `gp`, `satcat`, `boxscore`, `decay`, `cdm` (CDM), `gp_history`, `satcat_debut`, `tip`.

**Notes:** The claim lists `cdm_public` and `decay` among the classes in the basicspacedata path. `decay` is explicitly in the throttling table on the docs page. `cdm_public` is confirmed via the OpenAPI specs (see Claim 3). All structural details are accurate.

---

## Claim 3 — Space-Track provides cdm_public (public conjunction data messages) and decay classes

**Status: VERIFIED**

**Primary sources:**
- https://www.space-track.org/documentation (for `decay`)
- https://apis.io/apis/spacetrack/spacetrack-conjunction-data-api/ (OpenAPI spec for `cdm_public`)
- https://duncaneddy.github.io/brahe/latest/learn/ephemeris/spacetrack/cdm.html (third-party lib docs confirming the class name)

**Confirming excerpts:**

decay class — throttling table on https://www.space-track.org/documentation:
> "DECAY — 1 / day — Once you download an object's decay history, you need to store it on your own servers; do not download it again."

cdm_public class — OpenAPI spec:
> paths:
>   /basicspacedata/query/class/cdm_public/{queryParams}:
>     get:
>       summary: Query public Conjunction Data Messages (CDM)
>       description: 'Returns conjunction data messages for close approaches between tracked objects. Rate limit: 3 queries per day for all conjunctions; 1 per hour for specific events.'

Example query URL from the same spec:
> "https://www.space-track.org/basicspacedata/query/class/cdm_public/TCA/%3Enow/PC/%3E0.0001/orderby/TCA%20asc/format/json/"

The documentation page also references CDM under the expanded space data controller with throttling:
> "CDM — 3 / day — Once every 8 hours for all constellation Conjunction Data Messages (CDM)"

**Notes:** `cdm_public` (public CDMs, basicspacedata) and `cdm` (full CDMs, expandedspacedata) are distinct endpoints. The claim's specific mention of `cdm_public` is correct and confirmed.

---

## Claim 4 — ESA DISCOS data is gated; "DISCOS data can only be queried by registered users who meet permission criteria defined by the data providers"

**Status: PARTIALLY VERIFIED**

**Primary sources:**
- https://sdup.esoc.esa.int/ (Space Debris User Portal — DISCOS section)
- https://discosweb.esoc.esa.int/
- https://conference.sdo.esoc.esa.int/proceedings/sdc8/paper/204/SDC8-paper204.pdf

**Confirming excerpts (gating confirmed, exact quote NOT found verbatim):**

From https://sdup.esoc.esa.int/ (DISCOS description):
> "Users with a demonstrated need-to-know can apply for an account for on-line use (specified quotas apply) of DISCOS through a dedicated web-interface, if they belong to a research institute, to a government organisation, or to an industrial company of an ESA Member State (e.g., not as an individual)."

From https://discosweb.esoc.esa.int/:
> "DISCOSweb is a web based frontend to DISCOS. You can register by signing in with your Space Debris User Account and accepting the DISCOSweb terms and conditions. Note that orbital or attitude ephemeris from surveillance systems are not distributed via DISCOSweb."

From ESA SDC8 paper:
> "In addition to the DISCOSweb API, ESA also offers the DISCOSweb Operations API... Everyone with an operational need (e.g. collision avoidance) can apply for an account for the DISCOSweb API via email to space.debris.support@esa.int. This application needs to include proof of the operational need."

**Assessment:** The *substance* of the claim — DISCOS is gated, requires registration, and access is restricted to users meeting criteria — is **VERIFIED**. However, the specific quoted string *"DISCOS data can only be queried by registered users who meet permission criteria defined by the data providers"* was **NOT found verbatim** on any ESA page reviewed. The actual ESA wording uses "demonstrated need-to-know," "belong to a research institute, government organisation, or industrial company of an ESA Member State," and "proof of the operational need." The claim appears to be a paraphrase presented as a direct quote. Marked PARTIALLY VERIFIED because the factual substance is correct but the attributed quote could not be located.

---

## Claim 5 — NASA Orbital Debris Quarterly News archive exists at the stated URL and publishes quarterly PDFs with orbital debris research, news, statistics

**Status: VERIFIED**

**Primary source:** https://orbitaldebris.jsc.nasa.gov/quarterly-news/

**Confirming excerpt:**

Page description:
> "The Orbital Debris Quarterly News (ODQN) is a quarterly publication of the NASA Orbital Debris Program Office. The ODQN publishes some of the latest events in orbital debris research, offers orbital debris news and statistics, and presents project reviews and meeting reports, as well as upcoming events. Illustrating graphs, charts, photographs, and drawings support the articles and provide a detailed understanding of the topics. Each issue is available as a downloadable PDF."

The archive lists downloadable PDFs spanning 1996–2026, e.g.:
> "July 2026 | Volume 30 - Issue 1 & 2 — HUSIR and Goldstone Measurements of the Orbital Debris Environment: 2024-2025; Meeting Reports; Upcoming Meetings; Monthly Number of Objects in Earth Orbit by Object Type; Space Missions and Satellite Box Score"
> "September 2025 | Volume 29 - Issue 3 — An Updated Explosion Rate Methodology for Long-Term Orbital Debris Environment Modeling; Overview of the Cataloged Population over the Past 20 Years..."

All sub-claims (quarterly PDFs, research, news, statistics) are directly confirmed by the page content and article titles.

---

## Claim 6 — sgp4 Python library on PyPI and GitHub; tests agree to within 0.1 mm; error far less than 1–3 km/day satellite deviation from TLE orbits

**Status: VERIFIED**

**Primary sources:**
- https://pypi.org/project/sgp4/
- https://github.com/brandon-rhodes/python-sgp4

**Confirming excerpts:**

PyPI page — title and version:
> "sgp4 2.27 — The C++ SGP4 routine that, given an Earth satellite TLE, computes its position."
> "pip install sgp4"

0.1 mm accuracy + 1–3 km/day comparison (identical text on PyPI and GitHub README):
> "If your machine can't install or compile the C++ code, then this package falls back to using a slower pure-Python implementation of the library. Tests make sure that its positions **agree to within 0.1 mm** with the standard version of the algorithm — an error far less than the 1–3 km/day by which satellites themselves deviate from the ideal orbits described in TLE files."

GitHub repo URL confirmed:
> "Developers can check out this full project from GitHub: https://github.com/brandon-rhodes/python-sgp4"

The GitHub page confirms the repository exists with the same README and 449 commits.

**Notes:** Every component — PyPI URL, GitHub URL, 0.1 mm test accuracy, 1–3 km/day comparison — is quoted verbatim from the primary sources.

---

## Claim 7 — SGP4 returns raw x,y,z in TEME frame (Earth-centered, non-rotating); does NOT convert to ECEF/lat-long/WGS84; need astropy or skyfield for conversion

**Status: VERIFIED**

**Primary source:** https://pypi.org/project/sgp4/ (identical text on https://github.com/brandon-rhodes/python-sgp4 README)

**Confirming excerpt (verbatim):**
> "Note that the SGP4 propagator returns raw x,y,z Cartesian coordinates in a 'True Equator Mean Equinox' (TEME) reference frame that's centered on the Earth but does not rotate with it — an 'Earth centered inertial' (ECI) reference frame. The SGP4 propagator itself does not implement the math to convert these positions into more official ECI frames like J2000 or the ICRS, nor into any Earth-centered Earth-fixed (ECEF) frames like the ITRS, nor into latitudes and longitudes through an Earth ellipsoid like WGS84. For conversions into these other coordinate frames, look for a comprehensive astronomy library, like the Skyfield library that is built atop this one (see the section on Earth satellites in its documentation)."

OMM export also confirms the frame label:
> "'REF_FRAME': 'TEME'"

**Notes:** The claim is a near-verbatim summary of this exact paragraph. The claim mentions "astropy or skyfield" — the sgp4 docs name Skyfield specifically; astropy's TEME support is verified separately in Claim 10. Both libraries are valid for this purpose.

---

## Claim 8 — Foster/Chan/Alfano collision probability method exists and is documented; computes 2D Pc using combined hard-body radius + positional covariance ellipsoid overlap; open-source implementations exist

**Status: VERIFIED**

**Primary sources:**
- NASA CARA Handbook Appendix N: https://ntrs.nasa.gov/api/citations/20240003468/downloads/CA_Hanbook_Appendix.pdf
- Alfano review paper (AGI): https://www.agi.com/getmedia/05e56d95-73f9-422e-bde8-3a0c34946a69/Review-of-Conjunction-Probability-Methods-for-Short-term-Encounters.pdf
- Orekit API docs: https://www.orekit.org/site-orekit-latest/apidocs/org/orekit/ssa/collision/shorttermencounter/probability/twod/Alfano2005.html and .../Chan1997.html
- Open-source repo: https://github.com/JavierHernando/CollisionProbability

**Confirming excerpts:**

Method origins and 2D nature (NASA CARA Handbook Appendix N):
> "The conjunction plane method of Pc calculation, which is by far the most widely used approach in the conjunction assessment industry, was developed for the Space Shuttle Program and first described in the literature in 1992 (Foster and Estes). There have been a number of important treatments since that time — e.g., Akella and Alfriend (2000), Patera (2001), Alfano (2005a), Chan (2008), Garcia-Pelayo (2016), and Elrod (2019) — but all rely on the same basic methodology... calculating the Pc estimate by integrating over a two-dimensional region on a conjunction encounter plane."

Combined hard-body radius + covariance ellipsoid overlap (Alfano review paper):
> "Because the covariance matrices are expected to be uncorrelated, they are simply summed to form one, large, combined, covariance ellipsoid that is centered at the primary object... A physical overlap occurs if the secondary sphere comes within a distance equal to the sum of the two radii. Thus, we have a condition for collision. The probability of collision is obtained by evaluating the integral of the three-dimensional pdf within a long circular cylinder. It can be shown that this is equivalent to evaluating the integral of the two-dimensional pdf within a circle on a plane perpendicular to the relative velocity at closest approach."

Four named models (Alfano review):
> "In broad general terms and in chronological order, the four main models were developed by Foster, Chan, Patera, and Alfano."

Open-source implementations:
- Orekit (Java) ships `Alfano2005` and `Chan1997` classes with documented assumptions: "Short encounter leading to a linear relative motion. Spherical collision object. Uncorrelated positional covariance. Gaussian distribution of the position uncertainties."
- JavierHernando/CollisionProbability (Fortran 90): "implementation of five methods for calculating Collision probability... CollisionProbability_Chan.f90 Chan's method; CollisionProbability_Alfano.f90 Alfano's method; CollisionProbability_Foster.f90 Foster's method"

**Notes:** All sub-claims — method existence, Foster/Chan/Alfano attribution, 2D Pc, combined hard-body radius + covariance ellipsoid overlap, and open-source implementations — are directly confirmed.

---

## Claim 9 — The skyfield Python library can rotate TEME vectors to ITRS/ECEF and convert to geodetic WGS84 lat/lon/alt

**Status: VERIFIED**

**Primary sources:**
- https://rhodesmill.org/skyfield/coordinates.html (Coordinates chapter)
- https://rhodesmill.org/skyfield/api-framelib.html (ITRS frame reference)
- https://github.com/skyfielders/python-skyfield (source — `TEME_to_ITRF` routine and test)

**Confirming excerpts:**

ITRS as the ECEF frame in Skyfield (https://rhodesmill.org/skyfield/api-framelib.html):
> "skyfield.framelib.itrs = <skyfield.framelib.itrs object> — The International Terrestrial Reference System (ITRS). This is the IAU standard for an Earth-centered Earth-fixed (ECEF) coordinate system, anchored to the Earth's crust and continents."

WGS84 lat/lon/alt conversion (https://rhodesmill.org/skyfield/coordinates.html):
> "Skyfield uses the standard ITRS reference frame to specify positions that are fixed relative to the Earth's surface."
> "A location's latitude will vary slightly depending on whether you model the Earth as a simple sphere or more realistically as a slightly flattened ellipsoid. The most popular choice today is to use the WGS84 ellipsoid, which is the one used by the GPS system."
```python
from skyfield.api import wgs84
from skyfield.framelib import itrs
position = earth.at(t).observe(mars).apparent()
x, y, z = position.frame_xyz(itrs).au
lat, lon = wgs84.latlon_of(position)
height = wgs84.height_of(position)
```

TEME→ITRF rotation routine (source link from GitHub issue #438):
> "It's the `TEME_to_ITRF()` routine you will probably be interested in: https://github.com/skyfielders/python-skyfield/blob/.../skyfield/sgp4lib.py#L306"

Test validating TEME→ITRF against Vallado Appendix C (from the test file):
> "# Note that the following test is based specifically on Revision 2 of 'Revisiting Spacetrack Report #3' AIAA 2006-6753"
> "def test_appendix_c_conversion_from_TEME_to_ITRF():"

**Notes:** Skyfield provides both the TEME→ITRF rotation (via `TEME_to_ITRF()` in `sgp4lib.py`) and WGS84 geodetic conversion (via `wgs84.latlon_of()` / `wgs84.height_of()`). Both sub-claims confirmed.

---

## Claim 10 — The astropy.coordinates library can do TEME→ECEF conversions

**Status: VERIFIED**

**Primary source:** https://docs.astropy.org/en/stable/coordinates/satellites.html ("Working with Earth Satellites Using Astropy Coordinates")

**Confirming excerpts:**

TEME as a built-in astropy frame:
> "The output coordinate frame of the SGP4 model is the True Equator, Mean Equinox frame (TEME), which is one of the frames built-in to astropy.coordinates. TEME is an Earth-centered inertial frame (i.e., it does not rotate with respect to the stars). Several definitions exist; `astropy` uses the implementation described in Vallado et al (2006)."

TEME→ITRS(ECEF)→geodetic transform:
> "Once you have satellite positions in TEME coordinates they can be transformed into any astropy.coordinates frame."
```python
from astropy.coordinates import ITRS
itrs_geo = teme.transform_to(ITRS(obstime=t))
location = itrs_geo.earth_location
location.geodetic
# GeodeticLocation(lon=..., lat=..., height=...)
```

**Notes:** Astropy provides a built-in `TEME` frame and supports direct transformation to `ITRS` (the ECEF frame) via `transform_to(ITRS(...))`, and from there to geodetic lat/lon/height via `earth_location.geodetic`. The claim is fully confirmed.

---

# Summary Table

| # | Claim (short) | Status |
|---|---|---|
| 1 | Space-Track gated; User Agreement; approval time; efficient-query policy | VERIFIED |
| 2 | Space-Track API base, docs, ajaxauth/login POST, basicspacedata path | VERIFIED |
| 3 | Space-Track cdm_public and decay classes | VERIFIED |
| 4 | ESA DISCOS gated + specific quote | PARTIALLY VERIFIED (substance confirmed; exact quote not found verbatim) |
| 5 | NASA ODQN archive at stated URL with quarterly PDFs | VERIFIED |
| 6 | sgp4 on PyPI/GitHub; 0.1 mm test accuracy; 1–3 km/day comparison | VERIFIED |
| 7 | SGP4 returns TEME; no ECEF/WGS84 conversion; use astropy/skyfield | VERIFIED |
| 8 | Foster/Chan/Alfano 2D Pc method; hard-body radius + covariance overlap; OSS impls | VERIFIED |
| 9 | skyfield TEME→ITRS/ECEF→WGS84 lat/lon/alt | VERIFIED |
| 10 | astropy.coordinates TEME→ECEF | VERIFIED |

**Result:** 9 of 10 claims fully VERIFIED against primary sources. Claim 4 is PARTIALLY VERIFIED — the factual substance (DISCOS access is gated and criteria-based) is confirmed, but the exact quoted string attributed to ESA could not be located verbatim on any ESA page reviewed; it appears to be a paraphrase.
