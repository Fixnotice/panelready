"""PanelReady: build the public "new practices by state" pages from the weekly NPPES lead lists.

    py site\\build_pages.py            # on the PC: read output\\<week>\\leads_US_all.csv for every week, write the pages
    python build_pages.py --fetch      # on GitHub Actions: download any weekly file CMS posted since the last run

One page per state (states/texas/), one per state and category when the category had enough rows that week
(states/texas/behavioral-health/), a hub (states/), a sitemap and robots.txt, all written next to this file, which
is the folder that is published as the website. The week-by-week counts live in data/weeks.json so the trend
charts grow over time; samples, cities and specialties are kept for the newest week only. The landing page's
numbers (state picker, stats) are refreshed from the same data.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import io
import json
import re
import shutil
import sys
import urllib.request
from collections import Counter, defaultdict
from urllib.parse import quote
from pathlib import Path

HERE = Path(__file__).resolve().parent              # the site folder (the repository root on GitHub)
ROOT = HERE.parent                                   # the PanelReady project folder on the PC
for cand in (ROOT, HERE):                            # pr/npi.py lives in the project on the PC and is copied here for GitHub
    if (cand / "pr" / "npi.py").exists():
        sys.path.insert(0, str(cand))
        break
from pr import npi as N                              # noqa: E402

SITE = "https://panelready.co"                       # the site's address, no trailing slash (the old github.io address redirects here)
BUILD_VERSION = 21                                    # bump when the page layout changes, so the next run rewrites every page
COMPANY = "Avery Data Co."
PAYPAL_CLIENT_ID = "BAAQ4G4Hizw2wHo9EZQsTxcW_oBtYKOFEIoI41YQZJvC8ufp2vM9Z_lIU4ASqIUZvXAUrin0KLaYIpr8Js"   # the "PanelReady site" app on developer.paypal.com (Live); one-time orders
PAYPAL_ME = ""                                       # optional plan B: a PayPal.me handle (e.g. "averydataco"); shown as a second way to pay $39
WEEK_PRICE = 39                                      # one-time: this week's list for one state, every category
SMALL_WEEK, SMALL_WEEKS = 25, 4                      # a state under 25 new practices this week sells its last 4 weeks for the $39
LOCAL_PRICE, CAT_PRICE, ALL_PRICE, MULTI_PRICE = 49, 89, 149, 199   # monthly plans (yearly = 10 months); see pr/plans.py
SAMPLE_STATES = ["VT", "DE", "RI", "AK", "WY", "ND", "SD", "MT", "ME", "NH"]   # the free sample: the first of these with 8-25 rows this week
BRAND, MAIL = "PanelReady", "matt@panelready.co"
WEEKS = HERE / "data" / "weeks.json"
CAT_PAGE_MIN = 8                                     # a category page needs at least this many rows in the newest week
TREND_WEEKS = 12
CATS = N.CATEGORIES
CAT_TITLE = {"behavioral": "Behavioral health", "medical": "Medical practices & clinics", "dental": "Dental",
             "therapy": "Therapy & rehab", "home_senior": "Home care & senior living", "dme_transport": "DME, pharmacy & transport"}
CAT_NOUN = {"behavioral": "behavioral health practices", "medical": "medical practices & clinics", "dental": "dental practices",
            "therapy": "therapy & rehab practices", "home_senior": "home care & senior living providers",
            "dme_transport": "DME, pharmacy & transport providers"}
CAT_LEAD = {"behavioral": "Behavioral Health", "medical": "Medical Practice", "dental": "Dental Practice",
            "therapy": "Therapy & Rehab", "home_senior": "Home Care", "dme_transport": "DME & Pharmacy"}   # "{x} Leads" in titles
BUYERS = "credentialing & billing companies"          # who the pages are for (titles, headlines, descriptions)
CAT_SLUG = {"behavioral": "behavioral-health", "medical": "medical-practices", "dental": "dental", "therapy": "therapy-rehab",
            "home_senior": "home-care-senior-living", "dme_transport": "dme-pharmacy-transport"}
CAT_WHO = {"behavioral": "counselors, social workers, psychologists, psychiatry and psychiatric NPs, ABA providers and substance-use programs",
           "medical": "physicians, nurse practitioners, PAs, primary care and specialty clinics, urgent care and medical groups",
           "dental": "general dentists, dental specialists, hygienists, dental groups and clinics",
           "therapy": "physical, occupational and speech therapy, chiropractic, podiatry, optometry, acupuncture and dietitians",
           "home_senior": "home health agencies, in-home and personal care, assisted living, nursing facilities, hospice and case management",
           "dme_transport": "durable medical equipment suppliers, pharmacies, non-emergency medical transport and ambulance services"}
CAT_COLOR = {"behavioral": "#6d28d9", "medical": "#2563eb", "dental": "#be185d", "therapy": "#047857", "home_senior": "#b45309", "dme_transport": "#c2410c"}
STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut",
          "DE": "Delaware", "DC": "Washington, DC", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
          "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
          "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
          "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
          "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
          "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
          "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}
SLUG = {k: ("washington-dc" if k == "DC" else v.lower().replace(" ", "-")) for k, v in STATES.items()}
NEIGHBORS = {"AL": "FL GA MS TN", "AK": "WA HI OR", "AZ": "CA CO NM NV UT", "AR": "LA MS MO OK TN TX", "CA": "AZ NV OR", "CO": "AZ KS NE NM OK UT WY",
             "CT": "MA NY RI", "DE": "MD NJ PA", "DC": "MD VA", "FL": "AL GA", "GA": "AL FL NC SC TN", "HI": "CA AK WA", "ID": "MT NV OR UT WA WY",
             "IL": "IN IA KY MO WI", "IN": "IL KY MI OH", "IA": "IL MN MO NE SD WI", "KS": "CO MO NE OK", "KY": "IL IN MO OH TN VA WV",
             "LA": "AR MS TX", "ME": "NH MA", "MD": "DE DC PA VA WV", "MA": "CT NH NY RI VT", "MI": "IN OH WI", "MN": "IA ND SD WI",
             "MS": "AL AR LA TN", "MO": "AR IL IA KS KY NE OK TN", "MT": "ID ND SD WY", "NE": "CO IA KS MO SD WY", "NV": "AZ CA ID OR UT",
             "NH": "ME MA VT", "NJ": "DE NY PA", "NM": "AZ CO OK TX UT", "NY": "CT MA NJ PA VT", "NC": "GA SC TN VA", "ND": "MN MT SD",
             "OH": "IN KY MI PA WV", "OK": "AR CO KS MO NM TX", "OR": "CA ID NV WA", "PA": "DE MD NJ NY OH WV", "PR": "FL VI NY",
             "RI": "CT MA", "SC": "GA NC", "SD": "IA MN MT NE ND WY", "TN": "AL AR GA KY MS MO NC VA", "TX": "AR LA NM OK",
             "UT": "AZ CO ID NV NM WY", "VT": "MA NH NY", "VA": "DC KY MD NC TN WV", "WA": "ID OR", "WV": "KY MD OH PA VA",
             "WI": "IL IA MI MN", "WY": "CO ID MT NE SD UT"}
# resident population (millions, 2023 Census Bureau estimates) and the name the state's Medicaid program goes by:
# the per-100,000 rate and the program name are what make each state's page say something no other state's page says
STATE_FACTS = {
    "AL": (5.1, "Alabama Medicaid"), "AK": (0.7, "Alaska Medicaid"), "AZ": (7.4, "AHCCCS"), "AR": (3.1, "Arkansas Medicaid"),
    "CA": (39.0, "Medi-Cal"), "CO": (5.9, "Health First Colorado"), "CT": (3.6, "HUSKY Health"), "DE": (1.0, "Delaware Medicaid"),
    "DC": (0.7, "DC Medicaid"), "FL": (22.6, "Florida Medicaid"), "GA": (11.0, "Georgia Medicaid"), "HI": (1.4, "Med-QUEST"),
    "ID": (2.0, "Idaho Medicaid"), "IL": (12.5, "HealthChoice Illinois"), "IN": (6.9, "Indiana Medicaid"), "IA": (3.2, "Iowa Medicaid"),
    "KS": (2.9, "KanCare"), "KY": (4.5, "Kentucky Medicaid"), "LA": (4.6, "Healthy Louisiana"), "ME": (1.4, "MaineCare"),
    "MD": (6.2, "Maryland Medicaid"), "MA": (7.0, "MassHealth"), "MI": (10.0, "Michigan Medicaid"), "MN": (5.7, "Minnesota Medical Assistance"),
    "MS": (2.9, "Mississippi Medicaid"), "MO": (6.2, "MO HealthNet"), "MT": (1.1, "Montana Medicaid"), "NE": (2.0, "Heritage Health"),
    "NV": (3.2, "Nevada Medicaid"), "NH": (1.4, "New Hampshire Medicaid"), "NJ": (9.3, "NJ FamilyCare"), "NM": (2.1, "Turquoise Care"),
    "NY": (19.6, "New York Medicaid"), "NC": (10.8, "NC Medicaid"), "ND": (0.8, "North Dakota Medicaid"), "OH": (11.8, "Ohio Medicaid"),
    "OK": (4.1, "SoonerCare"), "OR": (4.2, "the Oregon Health Plan"), "PA": (13.0, "Pennsylvania Medical Assistance"), "PR": (3.2, "Plan Vital"),
    "RI": (1.1, "Rhode Island Medicaid"), "SC": (5.4, "Healthy Connections"), "SD": (0.9, "South Dakota Medicaid"), "TN": (7.1, "TennCare"),
    "TX": (30.5, "Texas Medicaid"), "UT": (3.4, "Utah Medicaid"), "VT": (0.6, "Vermont Medicaid"), "VA": (8.7, "Cardinal Care"),
    "WA": (7.8, "Apple Health"), "WV": (1.8, "West Virginia Medicaid"), "WI": (5.9, "BadgerCare Plus"), "WY": (0.6, "Wyoming Medicaid")}
US_POP = sum(v[0] for v in STATE_FACTS.values())
CODE_RE = re.compile(r"^\d{3}[A-Z0-9]{7}$")           # a bare taxonomy code where a specialty name should be
CMS_INDEX, CMS_BASE = "https://download.cms.gov/nppes/NPI_Files.html", "https://download.cms.gov/nppes/"
UA = {"User-Agent": "PanelReady/1.0 (public data; matt@panelready.co)"}


def say(m):
    print(m, flush=True)


def fmt(n) -> str:
    return f"{int(round(n)):,}"


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def long_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def short_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


SUFFIX = {"llc": "LLC", "pllc": "PLLC", "pc": "PC", "pa": "PA", "inc": "Inc", "ltd": "Ltd", "lp": "LP", "llp": "LLP", "md": "MD",
          "do": "DO", "dds": "DDS", "dmd": "DMD", "od": "OD", "dpm": "DPM", "phd": "PhD", "np": "NP", "rn": "RN", "lcsw": "LCSW",
          "cpa": "CPA", "sc": "SC", "ii": "II", "iii": "III", "iv": "IV", "dba": "DBA", "aba": "ABA", "ems": "EMS", "dme": "DME",
          "usa": "USA", "nyc": "NYC", "la": "LA", "pt": "PT", "ot": "OT"}


def nice_name(n: str) -> str:
    n = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), n)     # 1St -> 1st
    out = []
    for w in n.split():
        key = re.sub(r"[^a-z]", "", w.lower())
        out.append(re.sub(r"[A-Za-z]+", SUFFIX[key], w, count=1) if key in SUFFIX else w)
    return " ".join(out)


def mask_phone(p: str) -> str:
    return re.sub(r"\d{4}$", "••••", p or "")


# ------------------------------------------------------------------ data

def load() -> dict:
    if WEEKS.exists():
        return json.loads(WEEKS.read_text(encoding="utf-8"))
    return {"weeks": [], "counts": {}, "latest": None, "samples": {}, "cities": {}, "specialties": {}, "orgs": {}, "national": {}}


def save(data: dict):
    WEEKS.parent.mkdir(parents=True, exist_ok=True)
    data["weeks"] = sorted(set(data["weeks"]))[-104:]
    data["counts"] = {w: data["counts"][w] for w in data["weeks"] if w in data["counts"]}
    data["totals"] = {w: data.get("totals", {}).get(w, sum(sum(v) for v in data["counts"][w].values())) for w in data["weeks"] if w in data["counts"]}
    WEEKS.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


LATEST_LEADS: list[dict] = []                        # the newest week's rows seen this run (for the free sample file)


def ingest(data: dict, week_end: str, leads: list[dict]):
    """Fold one week's leads into the data file: counts for every week, details for the newest week only."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0] * len(CATS))
    for l in leads:
        if l["state"] in STATES and l["category"] in CATS:
            counts[l["state"]][CATS.index(l["category"])] += 1
    data["counts"][week_end] = dict(sorted(counts.items()))
    data.setdefault("totals", {})[week_end] = sum(1 for l in leads if l["category"] in CATS)   # includes territories outside STATES
    if week_end not in data["weeks"]:
        data["weeks"].append(week_end)
    if data["latest"] and week_end < data["latest"]:
        return
    data["latest"] = week_end
    LATEST_LEADS[:] = leads
    samples, cities, specs, orgs = {}, {}, {}, {}
    by_state: dict[str, list[dict]] = defaultdict(list)
    for l in leads:
        if l["state"] in STATES and l["category"] in CATS:
            by_state[l["state"]].append(l)
    for st, ls in by_state.items():
        ls.sort(key=lambda l: l["registered"], reverse=True)
        ls.sort(key=lambda l: l["entity"] != "practice/organization")       # organizations first, newest first (stable sorts)
        samples[st] = {"all": _spread(ls, 12)}
        for c in CATS:
            sub = [l for l in ls if l["category"] == c]
            if sub:
                samples[st][c] = [_row(l) for l in sub[:8]]
        cities[st] = Counter(l["city"] for l in ls if l["city"]).most_common(8)
        specs[st] = {"all": _top_specs(ls)}
        for c in CATS:
            specs[st][c] = _top_specs([l for l in ls if l["category"] == c])
        orgs[st] = sum(1 for l in ls if l["entity"] == "practice/organization")
    data["samples"], data["cities"], data["specialties"], data["orgs"] = samples, cities, specs, orgs
    usable = [l for l in leads if l["category"] in CATS]               # territories outside STATES still count nationally
    data["national"] = {"total": len(usable), "orgs": sum(1 for l in usable if l["entity"] == "practice/organization"),
                        "cats": [sum(1 for l in usable if l["category"] == c) for c in CATS], "states": len(counts)}


def _row(l: dict) -> list:
    spec = l["specialty"] if not CODE_RE.match(l["specialty"] or "") else CAT_TITLE[l["category"]]
    return [l["registered"], nice_name(l["name"]), spec, l["city"], mask_phone(l["phone"]), l["category"], l["entity"]]


def _spread(ls: list[dict], n: int) -> list:
    """Up to n rows that cover the categories (round-robin), organizations first within each."""
    buckets = {c: [l for l in ls if l["category"] == c] for c in CATS}
    out, i = [], 0
    while len(out) < n and any(buckets.values()):
        c = CATS[i % len(CATS)]
        if buckets[c]:
            out.append(_row(buckets[c].pop(0)))
        i += 1
    return out


def _top_specs(ls: list[dict]) -> list:
    return Counter(l["specialty"] for l in ls if l["specialty"] and not CODE_RE.match(l["specialty"])).most_common(6)


def local_weeks(data: dict) -> int:
    """On the PC: fold in every output\\<week>\\leads_US_all.csv (new weeks, plus the newest to refresh its details)."""
    n = 0
    for p in sorted((ROOT / "output").glob("*/leads_US_all.csv")):
        week = p.parent.name
        if week in data["counts"]:
            continue
        with open(p, encoding="utf-8", newline="") as f:
            leads = list(csv.DictReader(f))
        ingest(data, week, leads)
        say(f"  {week}: {len(leads):,} leads from {p.relative_to(ROOT)}")
        n += 1
    return n


def fetch_weeks(data: dict, limit: int = 4) -> int:
    """On GitHub: download the weekly files CMS has posted that aren't in data/weeks.json yet."""
    page = urllib.request.urlopen(urllib.request.Request(CMS_INDEX, headers=UA), timeout=60).read().decode("utf-8", "replace")
    found = re.findall(r"href=[\"']?([^\"' >]*NPPES_Data_Dissemination_(\d{6})_(\d{6})_Weekly(?:_V\d+)?\.zip)", page, re.I)
    files = sorted({(dt.datetime.strptime(b, "%m%d%y").date().isoformat(), link if link.startswith("http") else CMS_BASE + link.lstrip("./"))
                    for link, a, b in found})
    todo = [(w, u) for w, u in files if w not in data["counts"]][-limit:]
    if not todo:
        say(f"  nothing new on CMS (newest weekly file: {files[-1][0] if files else 'none listed'})")
        return 0
    names = taxonomy_names()
    for week, url in todo:
        say(f"  downloading {url.split('/')[-1]} ...")
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600).read()
        leads = N.leads_from_weekly(raw, dt.date.fromisoformat(week), names)
        ingest(data, week, leads)
        say(f"  {week}: {len(leads):,} leads")
    return len(todo)


def taxonomy_names() -> dict:
    for p in (ROOT / "data" / "nucc.json", HERE / "data" / "nucc.json"):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", "Accept": "*/*"}
    for ver in range(264, 240, -1):
        try:
            text = urllib.request.urlopen(urllib.request.Request(f"https://www.nucc.org/images/stories/CSV/nucc_taxonomy_{ver}.csv", headers=hdr), timeout=60).read().decode("utf-8", "replace")
            names = N.parse_nucc(text)
            if len(names) > 500:
                (HERE / "data").mkdir(exist_ok=True)
                (HERE / "data" / "nucc.json").write_text(json.dumps(names), encoding="utf-8")
                return names
        except Exception:                                # noqa: BLE001
            continue
    return {}


# ------------------------------------------------------------------ page pieces

CSS = """
.week{margin-top:22px;padding:18px 20px;border:1px dashed rgba(14,124,123,.5);border-radius:14px;background:rgba(14,124,123,.06)}
.week h3{margin:0 0 6px;font-size:18px}.week p{margin:0 0 12px}.week .paybox{max-width:320px}.week .note{min-height:1em}
:root{--bg:#f6f8fb;--bg2:#eef2f7;--card:#ffffff;--card2:#f3f6fa;--line:#e3e8ef;--line2:#cdd5e0;--ink:#0f2340;--body:#334155;--muted:#5b6b82;--dim:#8a97a9;--teal:#0e7c7b;--green:#15803d;--shadow:0 1px 2px rgba(15,35,64,.05),0 12px 32px -12px rgba(15,35,64,.14)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--body);font:16px/1.65 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
h1,h2,h3{font-family:"Source Serif 4",Georgia,"Times New Roman",serif;color:var(--ink);letter-spacing:-.01em;line-height:1.15;margin:0 0 10px;font-weight:600}
h1{font-size:clamp(30px,4.4vw,46px);line-height:1.08}h2{font-size:clamp(21px,2.6vw,28px);margin-top:0}
h1 em{font-style:italic;color:var(--teal)}
a{color:var(--teal)}p{margin:0 0 14px}
.wrap{max-width:1040px;margin:0 auto;padding:0 20px}@media(max-width:600px){.wrap{padding:0 16px}}
.nav{position:sticky;top:0;z-index:5;backdrop-filter:blur(14px);background:rgba(255,255,255,.88);border-bottom:1px solid var(--line)}
.nav .wrap{display:flex;align-items:center;justify-content:space-between;height:62px;gap:12px}
.logo{display:flex;align-items:center;gap:9px;font-family:"Source Serif 4",Georgia,serif;font-weight:700;font-size:21px;color:var(--ink);text-decoration:none}
.logo svg{width:28px;height:28px;border-radius:7px}
.nav nav{display:flex;gap:18px;align-items:center}.nav nav a{color:var(--muted);text-decoration:none;font-size:14px;font-weight:600}.nav nav a:hover{color:var(--ink)}
.nav nav a.mini{background:var(--ink);color:#fff;padding:9px 14px;border-radius:8px}
@media(max-width:700px){.nav nav a:not(.mini):not(.signin){display:none}.nav nav{gap:14px}.nav nav a{white-space:nowrap}}
@media(max-width:420px){.logo{font-size:18px;gap:7px}.logo svg{width:25px;height:25px}.nav nav{gap:10px}.nav nav a.signin{font-size:13px}.nav nav a.mini{padding:7px 10px;font-size:13px}}
@media(max-width:360px){.logo{font-size:16px;gap:6px}.logo svg{width:22px;height:22px}.nav nav{gap:8px}.nav nav a.signin{font-size:12px}.nav nav a.mini{padding:6px 8px;font-size:12px}}
.crumbs{font-size:13px;color:var(--dim);margin:18px 0 6px}.crumbs a{color:var(--muted);text-decoration:none}
.kicker{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--teal);margin-bottom:10px}
.lead{font-size:18px;color:var(--muted);max-width:760px}.lead b{color:var(--ink)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:26px 0}
@media(max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 16px 14px;box-shadow:var(--shadow)}
.stat b{display:block;font-family:"Source Serif 4",Georgia,serif;font-size:32px;font-weight:600;line-height:1.1;color:var(--ink)}.stat b small{font-size:14px;color:var(--muted);font-weight:600;font-family:Inter,sans-serif}
.stat span{display:block;color:var(--muted);font-size:13px;margin-top:6px;line-height:1.4}
section{margin:34px 0}
.grid2{display:grid;grid-template-columns:1.1fr .9fr;gap:22px}@media(max-width:800px){.grid2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:var(--shadow)}
.bar{display:grid;grid-template-columns:150px 1fr 44px;gap:10px;align-items:center;margin:9px 0;font-size:14px}
.bar .trk{height:12px;background:var(--bg2);border-radius:99px;overflow:hidden}.bar .fill{height:100%;border-radius:99px;min-width:3px}
.bar .v{text-align:right;font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums}.bar a{color:var(--ink);text-decoration:none}.bar a:hover{color:var(--teal)}
@media(max-width:480px){.bar{grid-template-columns:110px 1fr 40px;font-size:13px}}
.trend{display:flex;align-items:flex-end;gap:6px;height:150px;padding:10px 0 0}
.trend div{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;font-size:11px;color:var(--dim);gap:4px;min-width:0}
.trend i{display:block;width:100%;max-width:56px;background:linear-gradient(180deg,#14b8a6,var(--teal));border-radius:6px 6px 2px 2px}
.trend b{color:var(--ink);font-size:12px}.trend span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.06em;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}td:first-child,td:nth-child(5){white-space:nowrap}tr:last-child td{border-bottom:0}td.n{font-weight:600;color:var(--ink)}td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
.tscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.pill{display:inline-block;font-size:11px;font-weight:700;padding:3px 8px;border-radius:999px;background:var(--bg2);white-space:nowrap}
.cta{display:inline-block;background:var(--ink);color:#fff;font-weight:600;padding:13px 22px;border-radius:10px;text-decoration:none;font-size:15px;box-shadow:0 8px 24px -8px rgba(15,35,64,.45)}
.cta:hover{background:#1a365d}
.cta.ghost{background:#fff;color:var(--ink);border:1px solid var(--line2);box-shadow:none}.cta.ghost:hover{border-color:var(--teal);background:#fff}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.offer{background:linear-gradient(135deg,rgba(14,124,123,.08),rgba(37,99,235,.04));border:1px solid rgba(14,124,123,.35);border-radius:18px;padding:26px}
.offer h2{margin-top:0}.offer p{color:var(--muted)}
.links{display:flex;flex-wrap:wrap;gap:8px}.links a{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:7px 13px;text-decoration:none;color:var(--ink);font-size:14px}.links a:hover{border-color:var(--teal)}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:8px 0}summary{cursor:pointer;font-weight:600;color:var(--ink)}details p{margin:10px 0 0;color:var(--muted)}
.note{color:var(--dim);font-size:13px;margin-top:10px}
footer{color:var(--dim);font-size:13px;padding:30px 0 40px;border-top:1px solid var(--line);margin-top:40px}footer a{color:var(--muted)}
.flinks{display:flex;flex-wrap:wrap;gap:6px 18px;margin-bottom:10px}.flinks a{text-decoration:none;font-weight:600}.flinks a:hover{color:var(--ink)}
.prose{max-width:760px}.prose h2{margin-top:30px}.prose p,.prose li{color:var(--muted)}.prose li{margin:6px 0}.prose b{color:var(--ink)}
.all{columns:3;column-gap:20px}.all a{display:block;padding:5px 0;color:var(--ink);text-decoration:none;font-size:15px;break-inside:avoid}.all a small{color:var(--dim);margin-left:6px}
@media(max-width:700px){.all{columns:2}}
"""


def shell(title: str, desc: str, path: str, body: str, jsonld: dict | None = None) -> str:
    url = f"{SITE}/{path}" if path else f"{SITE}/"
    root = "../" * path.count("/")
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, separators=(",", ":"))}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{url}"><meta property="og:type" content="website">
<meta name="theme-color" content="#f6f8fb">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml"><link rel="icon" href="{root}favicon-32.png" sizes="32x32" type="image/png"><link rel="apple-touch-icon" href="{root}apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,600;0,8..60,700;1,8..60,600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
{ld}
</head>
<body>
<div class="nav"><div class="wrap">
  <a class="logo" href="{root}"><svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="15" fill="#0f2340"/><rect x="18" y="17" width="28" height="32" rx="4" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linejoin="round"/><rect x="25" y="13" width="14" height="8" rx="2.5" fill="#ffffff"/><path d="M25 34l5.5 5.5L40 29" fill="none" stroke="#2dd4bf" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>{BRAND}</a>
  <nav><a href="{root}search/">Live search</a><a href="{root}states/">All states</a><a href="{root}#how">How it works</a><a href="{root}#pricing">Pricing</a><a class="signin" href="{root}account/">Account</a><a class="mini" href="{root}#free">Get 2 lists free</a></nav>
</div></div>
<div class="wrap">
{body}
<footer><div class="flinks"><a href="{root}search/">Live search</a><a href="{root}states/">New practices by state</a><a href="{root}about/">About</a><a href="{root}contact/">Contact</a><a href="{root}privacy/">Privacy</a><a href="{root}terms/">Terms</a><a href="{root}sample/panelready-sample.csv">Sample spreadsheet</a></div>
{BRAND} · <a href="mailto:{MAIL}">{MAIL}</a> · an {COMPANY} product, New York<br>
Source: NPPES weekly dissemination files published by CMS. Public data, provided as-is; not affiliated with CMS or any payer. Practice names are from the public registry; phone numbers are masked on this page and complete in the subscriber spreadsheet.</footer>
</div>
</body>
</html>
"""


def bars(rows: list[tuple[str, int, str | None, str]]) -> str:
    """rows: (label, value, link or None, colour)"""
    mx = max([v for _, v, _, _ in rows] + [1])
    out = []
    for label, v, link, color in rows:
        lab = f'<a href="{link}">{esc(label)}</a>' if link else esc(label)
        out.append(f'<div class="bar"><div>{lab}</div><div class="trk"><div class="fill" style="width:{max(2, round(v / mx * 100))}%;background:{color}"></div></div><div class="v">{fmt(v)}</div></div>')
    return "".join(out)


def trend(data: dict, series: dict[str, int], label: str) -> str:
    weeks = data["weeks"][-TREND_WEEKS:]
    if len(weeks) < 2:
        w = weeks[-1] if weeks else ""
        return (f'<div class="trend"><div><b>{fmt(series.get(w, 0))}</b><i style="height:70%"></i><span>{short_date(w) if w else ""}</span></div></div>'
                f'<p class="note">Tracking started with the week ending {long_date(w) if w else "—"}; this chart fills in a bar a week.</p>')
    mx = max([series.get(w, 0) for w in weeks] + [1])
    cols = "".join(f'<div><b>{fmt(series.get(w, 0))}</b><i style="height:{max(3, round(series.get(w, 0) / mx * 100))}%"></i><span>{short_date(w)}</span></div>' for w in weeks)
    return f'<div class="trend">{cols}</div><p class="note">{label}, by the week the federal file covers.</p>'


def sample_table(rows: list, caption: str) -> str:
    if not rows:
        return ""
    body = "".join(f'<tr><td>{esc(r[0])}</td><td class="n">{esc(r[1])}</td><td>{esc(r[2])}</td><td>{esc(r[3])}</td><td>{esc(r[4])}</td>'
                   f'<td><span class="pill" style="color:{CAT_COLOR[r[5]]}">{esc(CAT_TITLE[r[5]].split(" &")[0].split(",")[0])}</span></td></tr>' for r in rows)
    return (f'<div class="card"><p class="note" style="margin:0 0 8px"><b style="color:var(--ink)">{esc(caption)}</b></p><div class="tscroll"><table>'
            f'<thead><tr><th>Registered</th><th>Practice</th><th>Specialty</th><th>City</th><th>Phone</th><th>Category</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div><p class="note">Real rows from the federal file. Subscribers get the full phone, street address, ZIP, NPI, taxonomy code and authorized official for every row.</p></div>')


def week_box(state_name: str, st: str, latest: str, total: int, avg: float = 0.0) -> str:
    """One-time purchase: this week's complete list for the state, every category, $39, sent to the PayPal email.
    A small state (under SMALL_WEEK rows this week) gets every new practice from the last 4 weeks for the same $39."""
    small = total < SMALL_WEEK
    if small:
        desc = f"PanelReady week list [{st}/all] last {SMALL_WEEKS} weeks ending {latest}"      # the PC reads 'last 4 weeks'
        est = max(total, round(avg * SMALL_WEEKS))
        head = f"The last {SMALL_WEEKS} weeks: ${WEEK_PRICE}, one time"
        what = (f"{esc(state_name)} is one of the smaller states, so the one-time list covers more than a week: every new practice "
                f"registered in {esc(state_name)} in the {SMALL_WEEKS} weeks ending {esc(short_date(latest))}"
                + (f", about {fmt(est)} rows at the recent pace" if est else "") + ", every category")
        paid = f"Your {esc(state_name)} list (the last {SMALL_WEEKS} weeks)"
    else:
        desc = f"PanelReady week list [{st}/all] week ending {latest}"
        head = f"Just this week: ${WEEK_PRICE}, one time"
        what = f"The complete {esc(state_name)} list for the week ending {esc(short_date(latest))}: all {fmt(total)} rows, every category"
        paid = f"This week's {esc(state_name)} list"
    payme = (f'<a class="cta ghost" href="https://paypal.me/{PAYPAL_ME}/{WEEK_PRICE}USD" target="_blank" rel="noopener">Pay ${WEEK_PRICE} with PayPal.me</a>'
             f' <span class="note">(type <b>{esc(state_name)}</b> in the note so the right list goes out)</span>') if PAYPAL_ME else ""
    PAYME_HTML = (f"Or <a href=\"https://paypal.me/{PAYPAL_ME}/{WEEK_PRICE}USD\" target=\"_blank\" rel=\"noopener\">pay ${WEEK_PRICE} with PayPal.me</a> and type {esc(state_name)} in the note."
                  if PAYPAL_ME else "Email matt@panelready.co for a PayPal invoice for $" + str(WEEK_PRICE) + ".")
    return f"""
<div class="week" id="week">
  <h3>{head}</h3>
  <p>{what}, as a spreadsheet, emailed to your PayPal address within minutes. One payment, nothing recurring. The charge shows as {COMPANY}</p>
  <div class="paybox" id="paypal-week"></div>
  <p class="note" id="week-done"></p>{('<p>' + payme + '</p>') if payme else ''}
</div>
<script src="https://www.paypal.com/sdk/js?client-id={PAYPAL_CLIENT_ID}&currency=USD&intent=capture&disable-funding=paylater"></script>
<script>
(function(){{
  var box = document.getElementById('paypal-week'), done = document.getElementById('week-done');
  if (!window.paypal || !box) {{ if (done) done.textContent = "To buy this list, email matt@panelready.co with the state."; return; }}
  paypal.Buttons({{
    style: {{ shape: 'pill', color: 'gold', layout: 'horizontal', label: 'pay', tagline: false, height: 44 }},
    createOrder: function(data, actions) {{
      return actions.order.create({{ purchase_units: [{{
        amount: {{ currency_code: 'USD', value: '{WEEK_PRICE}.00', breakdown: {{ item_total: {{ currency_code: 'USD', value: '{WEEK_PRICE}.00' }} }} }},
        description: {json.dumps(desc)}, custom_id: '{"week4" if small else "week"}:{st}:all:{latest}',
        items: [{{ name: {json.dumps(desc[:120])}, quantity: '1', unit_amount: {{ currency_code: 'USD', value: '{WEEK_PRICE}.00' }} }}] }}],
        application_context: {{ shipping_preference: 'NO_SHIPPING', brand_name: '{BRAND} ({COMPANY})' }} }});
    }},
    onApprove: function(data, actions) {{
      return actions.order.capture().then(function(o) {{
        var em = (o && o.payer && o.payer.email_address) || 'your PayPal email';
        box.style.display = 'none';
        done.innerHTML = "<b>Paid, thank you.</b> {paid} goes to " + em + " within minutes. If it hasn't arrived within the hour, email matt@panelready.co with your PayPal receipt.";
      }});
    }},
    onError: function(err) {{ done.innerHTML = "PayPal couldn't start the checkout" + (err && err.message ? " (" + String(err.message).slice(0, 160) + ")" : "") + ". {PAYME_HTML}"; console.error('PayPal week button', err); }}
  }}).render('#paypal-week');
}})();
</script>"""


def offer(state_name: str, st: str, cat: str | None, root: str, latest: str = "", total: int = 0, avg: float = 0.0) -> str:
    """The subscribe block. st="" makes the generic version for the hub."""
    what = f"{CAT_TITLE[cat].lower()} practice" if cat else "practice"
    plan = f"${CAT_PRICE}/month" if cat else f"${ALL_PRICE}/month"
    sub = "one spreadsheet every Monday" if cat else "every category, one spreadsheet every Monday"
    which = f"the {CAT_TITLE[cat].lower()} category" if cat else "all categories"
    q = f"?state={st}&cat={cat or 'all'}" if st else ""
    where = f"in {esc(state_name)}" if st else "in your state"
    week = week_box(state_name, st, latest, total, avg) if st and latest and (total or avg) else ""
    return (f'<section class="offer"><h2>Get every new {esc(what)} {where}, the week they register.</h2>'
            f'<p>This page shows a sample. Subscribers get the complete {esc(state_name) if st else "state"} list as a spreadsheet, {sub}, sorted best-first: the top 25 marked, a score and a ready-to-say opener for every practice, the owner\'s direct line where the registry lists it, phone, address and NPI, websites, emails and practice software for organizations where we can find them, an OIG exclusion check, and the practices that moved or added a specialty that week. Once a month: practices due for Medicare revalidation and practices that look stuck in credentialing. Your first paid list includes the last 90 days, teammates get copies, Roster Watch checks your own clients every week, and a webhook sends each list to your CRM. Backed by a 90-day guarantee. '
            f'{plan} per state through PayPal (or ${LOCAL_PRICE}/month for just your local area, ${MULTI_PRICE}/month for three states, 2 months free yearly; the charge shows as {COMPANY}, {BRAND}\'s parent company); cancel any time. Try two lists free first, no card needed: the first arrives within minutes.</p>'
            f'<div class="btns"><a class="cta" href="{root}{q}#free">Get two free {esc(state_name) if st else ""} lists</a><a class="cta ghost" href="{root}{q}#pricing">Subscribe · {plan}</a></div>{week}</section>')


def links_row(items: list[tuple[str, str]]) -> str:
    return '<div class="links">' + "".join(f'<a href="{href}">{esc(label)}</a>' for label, href in items) + "</div>"


# ------------------------------------------------------------------ pages

def state_series(data: dict, st: str, cat: str | None = None) -> dict[str, int]:
    out = {}
    for w in data["weeks"]:
        v = data["counts"].get(w, {}).get(st)
        if v:
            out[w] = v[CATS.index(cat)] if cat else sum(v)
    return out


def rank_of(data: dict, st: str) -> tuple[int, int]:
    week = data["counts"][data["latest"]]
    order = sorted(week, key=lambda k: -sum(week[k]))
    return (order.index(st) + 1 if st in order else len(order), len(order))


def avg4(series: dict[str, int]) -> float:
    vals = [series[w] for w in sorted(series)[-4:]]
    return sum(vals) / len(vals) if vals else 0.0


def pct(a: float, b: float) -> float:
    return a / b * 100 if b else 0.0


def state_context(data: dict, st: str, v: list, series: dict) -> str:
    """The paragraphs that are specific to this state: rate per resident, how it compares with its neighbors and
    with the national mix, which cities carry it, and what a new practice there has to do next. All of it is
    computed from the week's numbers, so it changes every week and differs from every other state's page."""
    name, latest = STATES[st], data["latest"]
    total, orgs = sum(v), data["orgs"].get(st, 0)
    pop, medicaid = STATE_FACTS.get(st, (0, "the state Medicaid program"))
    nat, week = data["national"], data["counts"][latest]
    people = f"{pop:g} million" if pop >= 1 else f"{pop * 1000:.0f},000"
    paras = []
    # 1. rate per 100,000 residents against the national rate, and against the state's own recent weeks
    if pop and total:
        rate, nat_rate = total / (pop * 10), nat["total"] / (US_POP * 10)
        rel = pct(rate, nat_rate) - 100
        how = ("about the national rate" if abs(rel) < 8 else
               f"{rate / nat_rate:.1f} times the national rate of {nat_rate:.1f}" if rel > 100 else
               f"{abs(rel):.0f}% {'above' if rel > 0 else 'below'} the national rate of {nat_rate:.1f}")
        s1 = (f"{name} has about {people} residents, so this week's {fmt(total)} registrations work out to "
              f"{rate:.1f} new practices per 100,000 people, {how}.")
        if len(series) >= 2:
            prev = series[sorted(series)[-2]]
            if prev:
                ch = pct(total - prev, prev)
                s1 += (f" That is {'up' if ch > 0 else 'down'} {abs(ch):.0f}% from the {fmt(prev)} registered the week before"
                       if abs(ch) >= 3 else f" That is level with the week before ({fmt(prev)}).")
        paras.append(s1)
    # 2. the category mix, where it differs from the country
    if total and nat.get("cats"):
        diffs = []
        for i, c in enumerate(CATS):
            here, there = pct(v[i], total), pct(nat["cats"][i], nat["total"])
            if v[i] >= 5 and abs(here - there) >= 4:
                diffs.append((here - there, c, here, there))
        diffs.sort(key=lambda d: -abs(d[0]))
        if diffs:
            d = diffs[0]
            s2 = (f"The mix leans {'toward' if d[0] > 0 else 'away from'} {CAT_TITLE[d[1]].lower()}: {d[2]:.0f}% of {name}'s new practices "
                  f"this week against {d[3]:.0f}% nationally")
            if len(diffs) > 1:
                e = diffs[1]
                s2 += f", and {CAT_TITLE[e[1]].lower()} is {'over' if e[0] > 0 else 'under'}-represented too ({e[2]:.0f}% vs {e[3]:.0f}%)"
            s2 += "."
        else:
            s2 = f"The category mix in {name} this week is close to the national mix."
        s2 += (f" {pct(orgs, total):.0f}% of the registrations are organizations rather than individual sole proprietors"
               f" (nationally {pct(nat['orgs'], nat['total']):.0f}%); organizations are the ones most likely to hire out credentialing and billing.")
        paras.append(s2)
    # 3. neighbors
    nb = [(STATES[n], sum(week[n])) for n in NEIGHBORS.get(st, "").split() if n in STATES and n in week]
    if nb:
        nb.sort(key=lambda x: -x[1])
        ahead = [n for n, k in nb if k > total]
        s3 = "Among neighboring states, " + ", ".join(f"{esc(n)} registered {fmt(k)}" for n, k in nb[:4]) + "."
        s3 += (f" {name} out-registered every neighbor this week." if not ahead else
               f" {name} trails {' and '.join(esc(a) for a in ahead[:2])} but is ahead of the rest." if len(ahead) < len(nb) else
               f" Every neighbor registered more than {name} this week.")
        paras.append(s3)
    # 4. where in the state
    cities = data["cities"].get(st, [])
    if cities and total:
        top3 = sum(k for _, k in cities[:3])
        s4 = (f"The top three cities ({', '.join(esc(c) for c, _ in cities[:3])}) account for {pct(top3, total):.0f}% of the state's new practices; "
              f"the rest are spread across smaller towns, which is where a weekly list earns its keep: nobody is driving past those offices to notice the new sign.")
        paras.append(s4)
    # 5. what happens next for a new practice in this state
    paras.append(f"A practice that registers in {name} still has its paperwork ahead of it. Seeing {medicaid} patients means enrolling with the "
                 f"state separately from the NPI, most commercial plans want a CAQH profile before they will credential anyone, and the whole "
                 f"cycle usually takes 60 to 120 days. That window, between the registry and the first claim, is when a {name} practice decides "
                 f"whether to do credentialing and billing in-house or hire it out, and it is why the practices on this page are worth a call "
                 f"this week rather than next quarter.")
    return (f'<section><h2>What stands out in {esc(name)} this week</h2>' + "".join(f"<p>{x}</p>" for x in paras) +
            f'<p class="note">Rates use the Census Bureau\'s 2023 population estimate ({people if pop else "n/a"}). Comparisons are to the same week\'s national file.</p></section>')


def state_page(data: dict, st: str) -> str:
    name, slug, latest = STATES[st], SLUG[st], data["latest"]
    v = data["counts"][latest].get(st, [0] * len(CATS))
    total, orgs = sum(v), data["orgs"].get(st, 0)
    series = state_series(data, st)
    rank, nstates = rank_of(data, st)
    nat = data["national"]["total"] or 1
    cats_sorted = sorted(range(len(CATS)), key=lambda i: -v[i])
    top = [(CATS[i], v[i]) for i in cats_sorted if v[i] > 0]
    cities = data["cities"].get(st, [])
    specs = data["specialties"].get(st, {}).get("all", [])
    month = total * 52 / 12
    root = "../../"
    cat_pages = {c: f"{CAT_SLUG[c]}/" for c in CATS if v[CATS.index(c)] >= CAT_PAGE_MIN}

    # headline paragraph, written from the numbers
    lead_bits = [f"<b>{fmt(total)}</b> healthcare practices and sole proprietors registered for an NPI in {name} in the week ending {long_date(latest)}"]
    if total:
        lead_bits.append(f"{fmt(orgs)} of them brand-new organizations (practices, clinics, agencies, suppliers) and {fmt(total - orgs)} sole proprietors")
    p1 = ", ".join(lead_bits) + "."
    p2 = ""
    if top:
        parts = [f"{esc(CAT_TITLE[c].lower())} ({fmt(n)})" for c, n in top[:3]]
        p2 = f"{esc(CAT_TITLE[top[0][0]])} led the week with {fmt(top[0][1])}" + (f", followed by {' and '.join(parts[1:])}" if len(parts) > 1 else "") + ". "
    if cities:
        p2 += f"The busiest cities were {', '.join(f'{esc(c)} ({n})' for c, n in cities[:3])}. "
    p2 += f"That is {total / nat * 100:.1f}% of the {fmt(nat)} new registrations nationwide, ranking {name} #{rank} of {nstates} states and territories this week."
    p3 = (f"At this week's pace {name} adds roughly {fmt(month)} new practices a month. Every one of them has to be credentialed with payers and set up for billing in the months after it registers, "
          f"which is why credentialing and medical-billing companies use this list as a call sheet: the practice is in the registry one to two weeks after it enrolled, usually before it has signed with anyone.")

    body = f"""
<div class="crumbs"><a href="{root}">{BRAND}</a> › <a href="../">All states</a> › {esc(name)}</div>
<span class="kicker">New practice leads for {esc(BUYERS)} · {esc(name)}</span>
<h1><em>{fmt(total)}</em> new healthcare practices registered in {esc(name)} last week: leads for credentialing &amp; billing companies</h1>
<p class="lead">{p1}</p>
<div class="stats">
  <div class="stat"><b>{fmt(total)}</b><span>new practices &amp; sole proprietors, week ending {esc(short_date(latest))}</span></div>
  <div class="stat"><b>{fmt(avg4(series))}<small> /wk</small></b><span>average over the last {min(4, len(series))} week{'s' if min(4, len(series)) != 1 else ''} tracked</span></div>
  <div class="stat"><b>{fmt(orgs)}</b><span>brand-new organizations: practices, clinics, agencies</span></div>
  <div class="stat"><b>#{rank}<small> of {nstates}</small></b><span>among states and territories this week · {total / nat * 100:.1f}% of the U.S. total</span></div>
</div>
<section><p>{p2}</p><p>{p3}</p></section>

{state_context(data, st, v, series)}

<section class="grid2">
  <div class="card"><h2>By category this week</h2>{bars([(CAT_TITLE[c], v[CATS.index(c)], cat_pages.get(c), CAT_COLOR[c]) for c in CATS])}
    <p class="note">Each practice is filed by the specialty code it registered under. Categories with a link have their own weekly page.</p></div>
  <div class="card"><h2>Week by week</h2>{trend(data, series, f"New practices and sole proprietors in {name}")}</div>
</section>

<section class="grid2">
  <div class="card"><h2>Busiest cities</h2>{bars([(c, n, None, "#2563eb") for c, n in cities]) if cities else '<p class="note">No city data this week.</p>'}</div>
  <div class="card"><h2>Most common specialties</h2>{bars([(s, n, None, "#6d28d9") for s, n in specs]) if specs else '<p class="note">No specialty data this week.</p>'}</div>
</section>

<section><h2>A sample of this week's {esc(name)} list</h2>
{sample_table(data["samples"].get(st, {}).get("all", []), f"leads_{st}_all.csv · week ending {short_date(latest)} · {fmt(total)} rows · organizations first")}</section>

{offer(name, st, None, root, latest, total, avg4(series))}

<section><h2>{esc(name)} by category</h2>
<p class="lead" style="font-size:16px">One state, one category is ${CAT_PRICE}/month; every category is ${ALL_PRICE}/month; three states are ${MULTI_PRICE}/month; just your local area (a ZIP code and a radius) is ${LOCAL_PRICE}/month. {('Weekly pages for: ' + ', '.join(f'<a href="{cat_pages[c]}">{esc(CAT_TITLE[c])}</a>' for c in CATS if c in cat_pages) + '.') if cat_pages else 'Category pages appear once a category has ' + str(CAT_PAGE_MIN) + '+ new practices in a week.'}</p>
<div class="tscroll"><table><thead><tr><th>Category</th><th>Who is in it</th><th class="r">This week</th><th class="r">4-wk avg</th></tr></thead><tbody>
{''.join(cat_row(data, st, c, v, cat_pages) for c in CATS)}
</tbody></table></div></section>

<section><h2>Questions about the {esc(name)} list</h2>
<details><summary>How many new healthcare practices open in {esc(name)} each month?</summary><p>About {fmt(month)} a month at the current pace ({fmt(total)} in the week ending {long_date(latest)}; {fmt(avg4(series))} a week on average over the weeks tracked). The count includes new organizations and individuals who registered as sole proprietors; employees who registered for an NPI to take a job are excluded.</p></details>
<details><summary>Where does this data come from?</summary><p>The National Plan and Provider Enumeration System (NPPES), run by CMS. Every provider and organization that bills insurance needs an NPI, and CMS publishes the weekly registrations as a public file. {BRAND} reads that file, keeps the practices and sole proprietors in {esc(name)}, sorts them into six categories and refreshes this page every week.</p></details>
<details><summary>How fresh are the names on this page?</summary><p>CMS posts each week's file about a week after the week ends, and most registrations in it are one to six days old at that point, so a practice shows up here one to two weeks after it registered. Subscribers get the full list the morning the file is posted.</p></details>
<details><summary>What does a subscriber get that this page doesn't show?</summary><p>Every {esc(name)} row, not a sample, with the complete phone number, street address, ZIP, NPI, taxonomy code, credential and authorized official, as a spreadsheet every Monday. {BRAND} does not sell email addresses; the registry doesn't contain them.</p></details>
</section>

<section><h2>Nearby states</h2>{links_row([(STATES[n], f"../{SLUG[n]}/") for n in NEIGHBORS.get(st, "").split() if n in STATES and n in data["counts"][latest]] + [("All states", "../")])}</section>
"""
    title = f"{name} New Practice Leads for Credentialing & Billing | {BRAND}"
    desc = (f"{fmt(total)} new healthcare practices registered in {name} the week ending {short_date(latest)}: weekly leads for credentialing "
            f"and medical billing companies, with name, specialty, city, phone and address.")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"New healthcare practices registered in {name}, by week",
          "description": desc, "url": f"{SITE}/states/{slug}/", "creator": {"@type": "Organization", "name": "Avery Data Co.", "url": SITE + "/"},
          "isBasedOn": "https://download.cms.gov/nppes/NPI_Files.html", "temporalCoverage": f"{data['weeks'][0]}/{latest}",
          "spatialCoverage": {"@type": "Place", "name": f"{name}, United States"}, "license": "https://www.usa.gov/government-works", "isAccessibleForFree": True,
          "variableMeasured": ["new NPI registrations by category", "new organizations", "busiest cities", "most common specialties"],
          "dateModified": latest}
    return shell(title, desc, f"states/{slug}/", body, ld)


def cat_row(data: dict, st: str, c: str, v: list, cat_pages: dict) -> str:
    label = f'<a href="{cat_pages[c]}">{esc(CAT_TITLE[c])}</a>' if c in cat_pages else esc(CAT_TITLE[c])
    return (f'<tr><td class="n">{label}</td><td style="color:var(--muted)">{esc(CAT_WHO[c])}</td><td class="r">{fmt(v[CATS.index(c)])}</td>'
            f'<td class="r">{fmt(avg4(state_series(data, st, c)))}</td></tr>')


def cat_context(data: dict, st: str, cat: str, n: int, total: int) -> str:
    name, ci, latest = STATES[st], CATS.index(cat), data["latest"]
    nat, week = data["national"], data["counts"][latest]
    pop, medicaid = STATE_FACTS.get(st, (0, "the state Medicaid program"))
    here, there = pct(n, total), pct(nat["cats"][ci], nat["total"])
    bits = []
    if pop:
        bits.append(f"That is {n / (pop * 10):.1f} new {CAT_TITLE[cat].lower()} practices per 100,000 {name} residents this week")
        bits[-1] += (f", a {'bigger' if here > there else 'smaller'} share of the state's registrations ({here:.0f}%) than this category takes nationally ({there:.0f}%)."
                     if abs(here - there) >= 3 else f", about the same share of the state's registrations as this category takes nationally ({there:.0f}%).")
    nb = sorted([(STATES[k], week[k][ci]) for k in NEIGHBORS.get(st, "").split() if k in STATES and k in week], key=lambda x: -x[1])
    if nb:
        bits.append("Next door, " + ", ".join(f"{esc(k)} had {fmt(c)}" for k, c in nb[:3]) + ".")
    bits.append(f"Each of these practices has to enroll with {medicaid} and the commercial plans it wants to bill before it can collect, "
                f"which is the stretch of weeks in which it chooses a credentialing or billing partner.")
    return " ".join(bits)


def cat_page(data: dict, st: str, cat: str) -> str:
    name, slug, latest, ci = STATES[st], SLUG[st], data["latest"], CATS.index(cat)
    v = data["counts"][latest].get(st, [0] * len(CATS))
    n, total = v[ci], sum(v)
    series = state_series(data, st, cat)
    rows = data["samples"].get(st, {}).get(cat, [])
    orgs = sum(1 for r in rows if r[6] == "practice/organization")
    specs = data["specialties"].get(st, {}).get(cat, [])
    cities = Counter(r[3] for r in rows if r[3]).most_common(5)
    nat = data["national"]["cats"][ci] or 1
    ct = CAT_TITLE[cat]
    root = "../../../"
    p1 = (f"<b>{fmt(n)}</b> {ct.lower()} practices and sole proprietors registered for an NPI in {name} in the week ending {long_date(latest)}, "
          f"{n / max(total, 1) * 100:.0f}% of the state's {fmt(total)} new registrations and {n / nat * 100:.1f}% of the {fmt(nat)} {ct.lower()} registrations nationwide.")
    p2 = f"This category covers {CAT_WHO[cat]}. " + (f"The most common specialties this week were {', '.join(f'{esc(s)} ({k})' for s, k in specs[:3])}. " if specs else "") + \
         f"At this pace {name} adds about {fmt(n * 52 / 12)} new {ct.lower()} practices a month, each of which will need payer credentialing and a billing setup before it can collect on a claim."
    body = f"""
<div class="crumbs"><a href="{root}">{BRAND}</a> › <a href="../../">All states</a> › <a href="../">{esc(name)}</a> › {esc(ct)}</div>
<span class="kicker">{esc(CAT_LEAD[cat])} leads for {esc(BUYERS)} · {esc(name)}</span>
<h1><em>{fmt(n)}</em> new {esc(CAT_NOUN[cat])} registered in {esc(name)} last week: leads for credentialing &amp; billing companies</h1>
<p class="lead">{p1}</p>
<div class="stats">
  <div class="stat"><b>{fmt(n)}</b><span>{esc(ct.lower())} registrations, week ending {esc(short_date(latest))}</span></div>
  <div class="stat"><b>{fmt(avg4(series))}<small> /wk</small></b><span>average over the last {min(4, len(series))} week{'s' if min(4, len(series)) != 1 else ''} tracked</span></div>
  <div class="stat"><b>{n / max(total, 1) * 100:.0f}%</b><span>of all new {esc(name)} practices this week ({fmt(total)})</span></div>
  <div class="stat"><b>{fmt(n * 52 / 12)}<small> /mo</small></b><span>new {esc(ct.lower())} practices a month at this pace</span></div>
</div>
<section><p>{p2}</p><p>{cat_context(data, st, cat, n, total)}</p></section>
<section class="grid2">
  <div class="card"><h2>Most common specialties</h2>{bars([(s, k, None, CAT_COLOR[cat]) for s, k in specs]) if specs else '<p class="note">No specialty data this week.</p>'}</div>
  <div class="card"><h2>Week by week</h2>{trend(data, series, f"New {ct.lower()} practices in {name}")}</div>
</section>
<section><h2>A sample of this week's {esc(name)} {esc(ct.lower())} list</h2>
{sample_table(rows, f"leads_{st}_{cat}.csv · week ending {short_date(latest)} · {fmt(n)} rows · organizations first")}</section>
{offer(name, st, cat, root, latest, total, avg4(state_series(data, st)))}
<section><h2>Other {esc(name)} categories</h2>{links_row([(CAT_TITLE[c], f"../{CAT_SLUG[c]}/") for c in CATS if c != cat and v[CATS.index(c)] >= CAT_PAGE_MIN] + [(f"All of {name}", "../")])}</section>
<section><h2>{esc(ct)} in nearby states</h2>{links_row([(STATES[k], f"../../{SLUG[k]}/{CAT_SLUG[cat]}/") for k in NEIGHBORS.get(st, "").split() if k in STATES and data["counts"][latest].get(k, [0] * 6)[ci] >= CAT_PAGE_MIN] + [("All states", "../../")])}</section>
"""
    title = f"{name} {CAT_LEAD[cat]} Leads for Credentialing & Billing | {BRAND}"
    desc = (f"{fmt(n)} new {CAT_NOUN[cat]} registered in {name} the week ending {short_date(latest)}: weekly leads for credentialing "
            f"and medical billing companies, with name, specialty, city, phone and address.")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"New {ct.lower()} practices registered in {name}, by week", "description": desc,
          "url": f"{SITE}/states/{slug}/{CAT_SLUG[cat]}/", "creator": {"@type": "Organization", "name": "Avery Data Co.", "url": SITE + "/"},
          "isBasedOn": "https://download.cms.gov/nppes/NPI_Files.html", "temporalCoverage": f"{data['weeks'][0]}/{latest}", "dateModified": latest,
          "spatialCoverage": {"@type": "Place", "name": f"{name}, United States"},
          "license": "https://www.usa.gov/government-works", "isAccessibleForFree": True}
    return shell(title, desc, f"states/{slug}/{CAT_SLUG[cat]}/", body, ld)


def hub_page(data: dict) -> str:
    latest, week = data["latest"], data["counts"][data["latest"]]
    nat = data["national"]
    order = sorted(week, key=lambda k: -sum(week[k]))
    rows = "".join(f'<tr><td class="n"><a href="{SLUG[k]}/">{esc(STATES[k])}</a></td><td class="r">{fmt(sum(week[k]))}</td><td class="r">{fmt(avg4(state_series(data, k)))}</td>'
                   f'<td class="r">{fmt(data["orgs"].get(k, 0))}</td><td>{esc(CAT_TITLE[CATS[max(range(len(CATS)), key=lambda i: week[k][i])]])}</td></tr>' for k in order if k in STATES)
    body = f"""
<div class="crumbs"><a href="../">{BRAND}</a> › All states</div>
<span class="kicker">New practice leads by state for {esc(BUYERS)}</span>
<h1><em>{fmt(nat['total'])}</em> new healthcare practices registered across the U.S. last week: leads for credentialing &amp; billing companies</h1>
<p class="lead">Every practice, clinic, agency and sole proprietor that registered for an NPI in the week ending {long_date(latest)}, from the federal NPPES file, sorted by state. {fmt(nat['orgs'])} were brand-new organizations. Pick a state for its weekly count, trend, busiest cities, top specialties and a sample of the list.</p>
<div class="stats">
  <div class="stat"><b>{fmt(nat['total'])}</b><span>new practices &amp; sole proprietors, week ending {esc(short_date(latest))}</span></div>
  <div class="stat"><b>{fmt(nat['orgs'])}</b><span>brand-new organizations: practices, clinics, agencies, suppliers</span></div>
  <div class="stat"><b>{nat['states']}</b><span>states and territories with at least one registration</span></div>
  <div class="stat"><b>{fmt(max(nat['cats']))}</b><span>{esc(CAT_TITLE[CATS[nat['cats'].index(max(nat['cats']))]].lower())}, the largest category</span></div>
</div>
<section><div class="card"><h2>Week by week, nationwide</h2>{trend(data, data.get("totals", {}), "New practices and sole proprietors, all states and territories")}</div></section>
<section><h2>Every state, this week</h2>
<div class="tscroll"><table><thead><tr><th>State</th><th class="r">This week</th><th class="r">4-wk avg</th><th class="r">Organizations</th><th>Largest category</th></tr></thead><tbody>{rows}</tbody></table></div></section>
{offer("", "", None, "../")}
<section><h2>All states and territories</h2><div class="all">{''.join(f'<a href="{SLUG[k]}/">{esc(STATES[k])}<small>{fmt(sum(week.get(k, [0])))}</small></a>' for k in sorted(STATES, key=lambda k: STATES[k]))}</div></section>
"""
    title = f"New Healthcare Practice Leads by State for Credentialing & Billing | {BRAND}"
    desc = (f"{fmt(nat['total'])} new healthcare practices registered across the U.S. the week ending {short_date(latest)}: weekly leads by state "
            f"for credentialing and medical billing companies, with counts, trends, cities and specialties.")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "New healthcare practices registered in the U.S., by state and week", "description": desc,
          "url": f"{SITE}/states/", "creator": {"@type": "Organization", "name": "Avery Data Co.", "url": SITE + "/"}, "isBasedOn": "https://download.cms.gov/nppes/NPI_Files.html",
          "temporalCoverage": f"{data['weeks'][0]}/{latest}", "dateModified": latest, "spatialCoverage": {"@type": "Place", "name": "United States"},
          "license": "https://www.usa.gov/government-works", "isAccessibleForFree": True}
    return shell(title, desc, "states/", body, ld)


# ------------------------------------------------------------------ about, contact, privacy, terms, sample

def info_pages(data: dict) -> list[str]:
    latest, root = data["latest"], "../"
    since = long_date(data["weeks"][0]) if data["weeks"] else "October 2026"
    pages = {}
    pages["about"] = ("About PanelReady", f"{BRAND} is a weekly list of newly registered healthcare practices from the federal NPI registry, built by {COMPANY} in New York for credentialing and medical-billing companies.", f"""
<div class="crumbs"><a href="{root}">{BRAND}</a> › About</div>
<span class="kicker">About</span>
<h1>Public data, sorted so you can <em>act on it</em> the week it appears.</h1>
<div class="prose">
<p class="lead">{BRAND} reads the federal NPI registry's weekly file, keeps the practices and sole proprietors, sorts them by state and specialty, and sends subscribers a spreadsheet every Monday. That's the whole product. No scraping, no guessed emails, no "enriched" data: the name, specialty, address and phone a practice gave CMS when it registered, one to two weeks after it did.</p>
<h2>Who makes it</h2>
<p>{BRAND} is a product of <b>{COMPANY}</b>, a small company in New York that builds subscription services from public data. {COMPANY} is the name you'll see on your PayPal receipt and card statement. You can reach the person who runs it at <a href="mailto:{MAIL}">{MAIL}</a>; replies come from a human, usually the same day.</p>
<h2>Where the data comes from</h2>
<p>The National Plan and Provider Enumeration System (NPPES), run by the Centers for Medicare &amp; Medicaid Services. Every provider and organization that bills insurance must hold a National Provider Identifier, and CMS publishes the full registry and a weekly file of changes as public data. {BRAND} processes the weekly file and nothing else. We don't alter records, and we don't add data from other sources.</p>
<h2>What we do with it</h2>
<ul>
<li>Keep organizations (practices, clinics, agencies, suppliers) and individuals registered as sole proprietors; drop employees who registered to take a job, students and deactivated numbers. Roughly one row in three survives.</li>
<li>File each one into one of six categories by the specialty code it chose: behavioral health, medical practices &amp; clinics, dental, therapy &amp; rehab, home care &amp; senior living, and DME, pharmacy &amp; transport.</li>
<li>Write one spreadsheet per state and category, organizations first, and send each subscriber theirs the morning the file is posted.</li>
<li>Publish the weekly counts for <a href="{root}states/">every state</a> here, free, so anyone can see the pace of new practices where they work.</li>
</ul>
<h2>What we don't do</h2>
<p>We don't sell email addresses (the registry has none), we don't promise exclusivity (every subscriber to a state and category gets the same list), and we don't guarantee results. We send the list; what you do with it, and compliance with the rules that apply to your outreach, is yours.</p>
<p>Tracking since {since}. <a href="{root}#free">Two lists are free</a> if you want to see it for yourself.</p>
</div>
""")
    pages["contact"] = ("Contact PanelReady", f"How to reach {BRAND} ({COMPANY}): email, what to include, and how fast you'll hear back.", f"""
<div class="crumbs"><a href="{root}">{BRAND}</a> › Contact</div>
<span class="kicker">Contact</span>
<h1>Email works best. A person <em>reads it</em>.</h1>
<div class="prose">
<p class="lead"><a href="mailto:{MAIL}">{MAIL}</a>, any time. Replies usually come the same business day, from the person who runs {BRAND}.</p>
<h2>Useful things to put in the email</h2>
<ul>
<li><b>Free lists:</b> the quickest way is <a href="{root}#free">the form</a>, but an email with your company, state and category works just as well.</li>
<li><b>Changing your list:</b> subscribers can reply to any {BRAND} email with the new state or category ("switch to dental", "add New Jersey") and the next list reflects it.</li>
<li><b>Several states or an exclusive arrangement:</b> say which states and categories and we'll quote a bundle.</li>
<li><b>Your account page:</b> subscribers can open it from <a href="{root}account/">Account</a> at the top of any page: enter your email and we send a sign-in link within the hour.</li>
<li><b>Cancelling:</b> from your PayPal account under Subscriptions (your lists continue to the end of the period you've paid for), or reply STOP to any email (our emails stop right away and we cancel the PayPal subscription for you). No forms.</li>
<li><b>Billing questions:</b> charges appear as {COMPANY}, {BRAND}'s parent company. Include the PayPal subscription ID (starts with I-) if you have it.</li>
</ul>
<h2>Mailing address</h2>
<p>{COMPANY}, New York. The full postal address is in the footer of every email we send, as the law requires.</p>
</div>
""")
    pages["privacy"] = ("Privacy policy", f"What {BRAND} collects (very little), what it does with it, and how to have it removed.", f"""
<div class="crumbs"><a href="{root}">{BRAND}</a> › Privacy</div>
<span class="kicker">Privacy policy</span>
<h1>Short, because we collect <em>very little</em>.</h1>
<div class="prose">
<p class="lead">This policy covers panelready.co and the {BRAND} email service, operated by {COMPANY} ("we"). Last updated {long_date(latest)}.</p>
<h2>What we collect</h2>
<ul>
<li><b>When you ask for lists or subscribe:</b> your email address, company name, the state and category you chose, and, for paid plans, the PayPal subscription ID. PayPal handles the payment itself; we never see your card or bank details.</li>
<li><b>If you use your account page or reply with settings:</b> the teammates' email addresses you add (they receive copies of your lists), the provider NPIs you add to Roster Watch, and a webhook address if you set one. Your account page's contents (your settings and recent lists) are stored with Cloudflare so the page can show them; files are deleted after about 8 weeks.</li>
<li><b>When you email us:</b> the email and anything you put in it.</li>
<li><b>When you visit the site:</b> nothing we keep. The site has no analytics, no advertising pixels and sets no cookies of its own. It is hosted on GitHub Pages, whose servers keep standard access logs (IP address, pages requested) under <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. Fonts load from Google Fonts, which sees your IP address when it serves them.</li>
</ul>
<h2>What we do with it</h2>
<p>We use your details to send you the lists you asked for, confirmations, and replies to your messages. We don't sell, rent or share them with anyone except the services that make the product work: PayPal for payments, our email provider for sending, and Cloudflare, which receives form submissions before we collect them and hosts your account page's data. If you set a webhook, each list is also sent to the address you gave. We don't use your data for advertising.</p>
<h2>Email</h2>
<p>Every email we send carries our postal address and a way to stop. Reply STOP to any message and you'll receive nothing further; the address goes on a do-not-contact list we keep for that purpose. We also send a small number of introductory emails to credentialing and billing companies found through public sources; the same STOP applies.</p>
<h2>The data in the lists</h2>
<p>The practices in our lists are organizations and sole proprietors who registered with CMS, taken from the public NPPES file as published. If you are a provider and want your public record changed, that is done with CMS through <a href="https://nppes.cms.hhs.gov/">NPPES</a>; we republish the file as it stands. If you'd rather not appear on this website's sample pages, email us and we'll remove the row from the pages we control.</p>
<h2>Keeping and deleting it</h2>
<p>We keep subscriber details while you're a subscriber and for our accounting afterwards. Email <a href="mailto:{MAIL}">{MAIL}</a> to see what we hold about you or to have it deleted; we'll do that within 30 days, keeping only what the law requires us to keep (for example payment records).</p>
<h2>Changes</h2>
<p>If this policy changes, the date at the top changes with it. Questions: <a href="mailto:{MAIL}">{MAIL}</a>.</p>
</div>
""")
    pages["terms"] = ("Terms of service", f"The terms for {BRAND} subscriptions and free lists: what you get, what it costs, cancelling, and the limits of a public-data product.", f"""
<div class="crumbs"><a href="{root}">{BRAND}</a> › Terms</div>
<span class="kicker">Terms of service</span>
<h1>Plain terms for a <em>plain product</em>.</h1>
<div class="prose">
<p class="lead">These terms apply to the {BRAND} lists and website, provided by {COMPANY} ("we"). By requesting lists or subscribing you agree to them. Last updated {long_date(latest)}.</p>
<h2>The service</h2>
<p>{BRAND} sends you a spreadsheet of healthcare practices and sole proprietors that registered for an NPI in the previous week, for the state(s) and category(ies) on your plan, on the morning CMS posts the weekly file (normally once a week; CMS occasionally skips or delays a week). Your first list goes out as soon as you sign up and we know your territory, usually within minutes, from the latest weekly file (if that file has nothing for your territory, with the next one). A subscription's first paid list goes out as soon as your payment comes through and we know your territory, usually within minutes, and also includes every new practice in your territory from the previous 90 days; after that, lists follow the weekly schedule above. The data comes from the public NPPES registry exactly as published. We sort it, score each practice and suggest an opener; for organizations we also look up websites, emails, Google ratings and the practice software their websites use, from public sources (Google and the practice's own website), and we check every name against the federal OIG exclusion list. Each week subscribers also get the practices whose registered location changed in the registry that week, and once a month two more lists: practices due (or overdue) for Medicare revalidation according to CMS's public Revalidation Due Date List, and practices that registered 2-12 months earlier and don't appear on Medicare's public enrollment list. A "Medicare pending" flag means the provider appears on CMS's public list of pending first-time applications. Scores, openers, practice-size counts and lookups are our best suggestions, not verified facts; dates and statuses are as CMS publishes them.</p>
<h2>The 90-day guarantee</h2>
<p>If you don't sign at least one new client from your {BRAND} lists during your first 90 days as a paying subscriber, tell us by email within 30 days after that and your next three months are free: we pause your PayPal subscription for three months, then it resumes at your normal price. One guarantee per company; no proof required.</p>
<h2>Free lists</h2>
<p>New companies can receive two weekly lists free, no payment details required. Free lists contain the weekly spreadsheet (with website and email lookups for its top 25 practices), the practices that moved or changed that week, a CRM import file and the outreach kit; the 90-day history, the monthly lists, the account page and Search &amp; export come with a subscription. After the second list, unless you subscribe, you receive a short free weekly digest (the best new practices by name, without contact details) until you reply STOP. We may decline or limit free lists at our discretion, for example to one per company.</p>
<h2>Plans and payment</h2>
<ul>
<li><b>Local area</b> (every new practice within 5 to 100 miles of one ZIP code, every category): ${LOCAL_PRICE} per month. <b>One state, one category:</b> ${CAT_PRICE} per month. <b>One state, every category:</b> ${ALL_PRICE} per month. <b>Three states, every category:</b> ${MULTI_PRICE} per month. Each plan can be billed yearly for the price of ten months. Subscriptions started at an earlier price keep that price.</li>
<li>Plans include teammates who receive copies of each list (2, 3, 5 or 10 people in all, by plan), Roster Watch for your own providers (100, 100, 500 or 2,000 NPIs) and an optional webhook. Teammates must work at your company. Your account page is for active subscribers. It opens from the private link in your list emails, or from a sign-in link we email you when you enter your address on the account page; keep these links private, as anyone with one can see your lists and change your settings. When a subscription ends, the account page closes; subscribing again with the same email reopens it.</li>
<li>Payment is by PayPal subscription, billed monthly or yearly in advance. Charges appear as <b>{COMPANY}</b>. Prices may change with at least 30 days' notice by email; your current month is never affected.</li>
<li>You can cancel at any time from your PayPal account: your lists and account page continue to the end of the period already paid for (the month, or the year on yearly billing), and no further charges are made. Replying STOP to any email also cancels: our emails stop right away and we cancel your PayPal subscription so no further charges are made. Partial periods are not refunded, except that if your first paid list never arrives we'll refund the month in full.</li>
</ul>
<h2>What you may do with the lists</h2>
<p>Use them inside your own business to find and contact practices. You may not resell, republish or redistribute the lists, or use them to build a competing product. The lists are not exclusive: other subscribers to the same state and category receive the same data. You are responsible for your own outreach and for complying with the laws that apply to it, including telephone and email marketing rules.</p>
<h2>No warranty</h2>
<p>The data is public information provided as-is. We don't warrant that it is complete, current or accurate, that a given practice is still operating or wants to be contacted, that a looked-up website or email belongs to the practice, that a practice missing from Medicare's quarterly enrollment list isn't credentialed elsewhere, or that using it will produce any result (beyond the guarantee above). Our total liability for any claim connected with the service is limited to the amount you paid us in the three months before the claim arose. We're not affiliated with CMS or any payer.</p>
<h2>Changes and law</h2>
<p>We may update these terms; the date at the top changes when we do, and material changes are announced by email to subscribers. These terms are governed by the laws of the State of New York. Questions: <a href="mailto:{MAIL}">{MAIL}</a>.</p>
</div>
""")
    out = []
    for slug, (title, desc, body) in pages.items():
        d = HERE / slug
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(shell(f"{title} — {BRAND}", desc, f"{slug}/", body), encoding="utf-8")
        out.append(f"{slug}/")
    return out


# ------------------------------------------------------------------ the subscriber account page (panelready.co/account/#t=TOKEN)

WORKER = "https://panelready-signup.matt-fixnotice.workers.dev"

ACCOUNT_CSS = """
.acct{max-width:860px}.acct h1{margin-top:6px}
.acct .card{margin:16px 0}.acct .card h2{font-size:22px;margin:0 0 6px}.acct .card p.help{color:var(--muted);font-size:14px;margin:0 0 12px}
.acct label{display:block;font-size:13px;color:var(--muted);font-weight:600;margin:10px 0 6px}
.acct input,.acct select,.acct textarea{width:100%;background:#fff;color:var(--ink);border:1.5px solid var(--line2);border-radius:10px;padding:11px 13px;font:500 15px Inter,sans-serif}
.acct textarea{min-height:110px;font:13px ui-monospace,Menlo,Consolas,monospace}
.acct input:focus,.acct select:focus,.acct textarea:focus{outline:none;border-color:var(--teal);box-shadow:0 0 0 4px rgba(14,124,123,.14)}
.acct button.cta{border:0;cursor:pointer;margin-top:12px}
.acct .row3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.acct .row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:640px){.acct .row3,.acct .row2{grid-template-columns:1fr}}
.acct .msg{min-height:1.2em;font-size:14px;margin-top:8px}.acct .msg.ok{color:var(--green)}.acct .msg.err{color:#be123c}
.acct .badge{display:inline-block;font-size:12px;font-weight:700;padding:4px 10px;border-radius:999px;background:rgba(14,124,123,.1);color:var(--teal);margin-right:6px}
.acct .dl a{font-weight:600}.acct .dl td{white-space:normal}.acct .muted{color:var(--muted)}
.acct .up{background:linear-gradient(135deg,rgba(14,124,123,.08),rgba(37,99,235,.04));border-color:rgba(14,124,123,.35)}
.acct .hide{display:none}
"""

ACCOUNT_BODY = """
<div class="crumbs"><a href="../">PanelReady</a> › Your account</div>
<div class="acct">
<span class="kicker">Your account</span>
<h1 id="hello">Your PanelReady account</h1>
<p class="lead" id="planline">Loading your account…</p>

<div class="card hide" id="needLink">
  <h2>Sign in</h2>
  <p class="help">Account pages are for PanelReady subscribers. Enter the email address your lists go to and we'll email you a private sign-in link (within the hour). The account link at the bottom of any weekly list email works too.</p>
  <form id="linkForm" novalidate><label for="lkEmail">Email</label><input type="email" id="lkEmail" placeholder="you@company.com" autocomplete="email" required>
  <input type="text" name="website" id="lkHp" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px" aria-hidden="true">
  <button class="cta" type="submit">Email me a sign-in link</button><div class="msg" id="linkMsg"></div></form>
  <p class="help" style="margin-top:14px">Not a subscriber yet? <a href="../#pricing">See plans</a> or <a href="../#free">get two lists free</a>.</p>
</div>

<div class="card up hide" id="lockedBox"><h2>For subscribers</h2><p class="help" id="lockedText"></p><a class="cta" href="../#pricing">See plans</a></div>

<div id="acctBody" class="hide">
<div class="card up hide" id="upsell"><h2>Keep the full lists coming</h2><p class="help" id="upsellText"></p><a class="cta" href="../#pricing">See plans</a></div>

<div class="card"><h2>Your lists</h2>
  <p class="help">Every weekly email, as one zip per week (kept about 8 weeks). Your first paid list includes the last 90 days of new practices in your territory.</p>
  <p class="help"><a id="searchLink" href="../search/"><b>Search &amp; export</b></a>: filter everything in your territory (the last 13 weeks, plus this month's stuck-in-credentialing and revalidation lists) by county, city, distance from a ZIP, specialty or practice type, and download just the rows you want.</p>
  <div class="tscroll"><table class="dl"><thead><tr><th>Week ending</th><th>Files</th><th class="r">Download</th></tr></thead><tbody id="dlRows"></tbody></table></div>
</div>

<div class="card"><h2>Territory</h2>
  <p class="help" id="terrHelp"></p>
  <form id="terrForm" novalidate>
    <div id="areaBox" class="row2 hide"><div><label for="zip">ZIP code</label><input id="zip" inputmode="numeric" maxlength="5" placeholder="12207"></div>
      <div><label for="radius">Radius (miles)</label><input id="radius" type="number" min="5" max="100" value="25"></div></div>
    <div id="stateBox" class="hide"><div class="row3" id="stateSels"></div>
      <div id="catBox"><label for="cat">Category</label><div class="sel"><select id="cat"></select></div></div></div>
    <button class="cta" type="submit">Save territory</button><div class="msg" id="terrMsg"></div>
  </form>
</div>

<div class="card" id="teamCard"><h2>Teammates</h2>
  <p class="help" id="teamHelp"></p>
  <form id="teamForm" novalidate><label for="team">Teammates' emails, one per line</label><textarea id="team" style="min-height:80px;font:500 15px Inter,sans-serif"></textarea>
  <button class="cta" type="submit">Save teammates</button><div class="msg" id="teamMsg"></div></form>
</div>

<div class="card" id="rosterCard"><h2>Roster Watch</h2>
  <p class="help">Paste the NPIs of your own providers (your current clients). Every week we check each one against the OIG exclusion list, Medicare opt-outs, NPI deactivations, Medicare revalidation due dates, Medicare enrollment and pending applications, and its registered address, and your weekly email tells you only what changed. <span id="rosterLimit"></span></p>
  <form id="rosterForm" novalidate><label for="roster">NPIs (any format: one per line, commas, or pasted from a spreadsheet)</label><textarea id="roster" placeholder="1234567893"></textarea>
  <button class="cta" type="submit">Save roster</button><div class="msg" id="rosterMsg"></div></form>
  <div id="rosterReport" class="hide"><h3 style="margin-top:18px;font-size:17px">Worth a look <span class="muted" id="rosterChecked" style="font:500 13px Inter,sans-serif"></span></h3>
  <div class="tscroll"><table><thead><tr><th>NPI</th><th>Provider</th><th>Notes</th></tr></thead><tbody id="rosterRows"></tbody></table></div></div>
</div>

<div class="card" id="hookCard"><h2>Send each list to your CRM (webhook)</h2>
  <p class="help">Paste a "catch hook" address from Zapier (Webhooks by Zapier → Catch Hook) or Make (Custom webhook), or your own HTTPS endpoint. Every week, right after the email, we POST the rows as JSON, 500 per request: <code>{"source","week","part","parts","rows":[{"Company","First Name","Phone","Email","NPI",…}]}</code>, the same columns as the CRM import file.</p>
  <form id="hookForm" novalidate><label for="hook">Webhook address (https://…)</label><input id="hook" type="url" placeholder="https://hooks.zapier.com/hooks/catch/…">
  <button class="cta" type="submit">Save webhook</button><div class="msg" id="hookMsg"></div></form>
</div>

<div class="card"><h2>Billing</h2>
  <p class="help">Payments go through PayPal and show as Avery Data Co. To change plans, pick the new one on the <a href="../#pricing">pricing section</a> with the same email, then cancel the old one. To cancel: PayPal → Settings → Payments → Manage automatic payments; your lists and this page continue to the end of the period you've paid for. Replying STOP to any email also cancels, and our emails stop right away. Questions: reply to any list email.</p>
</div>
<p class="note">Keep this page's link private: anyone with it can see your lists and change your settings. Changes are applied within the hour and confirmed by email. <span id="updated"></span></p>
</div>
</div>
<script>
(function(){
  var W = '__WORKER__';
  var NICE = __NICE__, NAMES = __NAMES__;
  var t = (location.hash.match(/[#&]t=([A-Za-z0-9_-]{20,64})/) || [])[1] || '';
  var $ = function(id){ return document.getElementById(id); };
  var show = function(id, on){ $(id).classList.toggle('hide', !on); };
  if (t) $('searchLink').href = '../search/#t=' + t;
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function msg(id, text, ok){ var m = $(id); m.textContent = text; m.className = 'msg ' + (ok ? 'ok' : 'err'); }
  function post(path, body, msgId, okText){
    msg(msgId, 'Saving…', true);
    fetch(W + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function(r){ return r.json(); })
      .then(function(j){ j.ok ? msg(msgId, okText, true) : msg(msgId, j.error || 'That didn\\'t work. Reply to any list email instead.', false); })
      .catch(function(){ msg(msgId, 'Couldn\\'t reach PanelReady. Try again, or reply to any list email.', false); });
  }
  var SAVED = 'Saved. It\\'s applied within the hour, and you\\'ll get an email confirming it.';
  $('linkForm').addEventListener('submit', function(e){
    e.preventDefault();
    var em = $('lkEmail').value.trim();
    if (!/^[^\\s@]+@[^\\s@]+\\.[a-z]{2,}$/i.test(em)) { msg('linkMsg', 'Please enter the email address your lists go to.', false); return; }
    post('/link', { email: em, website: $('lkHp').value }, 'linkMsg', 'If that address has an active subscription, a sign-in link is on its way (within the hour).');
  });
  if (!t) { $('hello').textContent = 'Sign in to your account'; $('planline').textContent = ''; show('needLink', true); return; }
  fetch(W + '/acct?t=' + encodeURIComponent(t), { cache: 'no-store' })
    .then(function(r){ return r.json(); })
    .then(function(a){
      if (a && a.locked) { locked(a); return; }
      if (!a || a.ok === false || !a.email) { $('planline').textContent = 'This link doesn\\'t open an account. Account pages are for active subscribers: if you just subscribed, your page appears within the hour. Or get a new sign-in link below.'; show('needLink', true); return; }
      render(a);
    })
    .catch(function(){ $('planline').textContent = 'Couldn\\'t load your account just now. Try again in a minute.'; });

  function locked(a){
    // trial, free digest, cancelled, unsubscribed and one-time buyers: no lists or settings here, just the way back in
    $('planline').textContent = 'Account pages are for active PanelReady subscribers.';
    var s = a.status || '', why;
    if (s === 'trial') why = 'You\\'re on the free trial: your two free lists come by email. Subscribe to open your account page, with past lists, Search & export, territory, teammates and Roster Watch.';
    else if (s === 'free') why = 'Your free trial has ended. Subscribe to open your account page and get the full lists every week.';
    else if (s === 'week_sent' || s === 'week_pending') why = 'Your one-time list comes by email. Subscribe to open your account page and get the full lists every week.';
    else why = 'Your subscription has ended. Subscribe again with the same email to reopen your account page: your territory and teammates are kept.';
    $('lockedText').textContent = why;
    show('lockedBox', true);
  }

  function render(a){
    show('acctBody', true);
    var first = (a.name || '').split(' ')[0];
    $('hello').textContent = first ? 'Hi ' + first + '.' : 'Your PanelReady account';
    var where = a.area ? a.area_label : (a.states.map(function(s){ return NAMES[s] || s; }).join(', ') || 'no state picked yet');
    var cats = a.area ? 'every category' : (a.categories.indexOf('all') >= 0 ? 'every category' : a.categories.map(function(c){ return NICE[c] || c; }).join(', '));
    var plan = a.status === 'paid' ? '<span class="badge">' + esc(a.plan_label) + (a.price ? ' · $' + a.price + '/mo' : '') + '</span>'
      : '<span class="badge">' + esc(a.plan_label) + '</span>';
    $('planline').innerHTML = plan + ' Lists go to <b>' + esc(a.email) + '</b>: ' + esc(where) + (cats ? ', ' + esc(cats) : '') + '.';
    if (a.ends) {
      var end = new Date(a.ends + 'T12:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
      $('planline').innerHTML += ' <b>Cancelled:</b> your lists and this page continue until ' + esc(end) + '. <a href="../#pricing">Subscribe again</a> to keep them coming.';
    }
    if (a.status !== 'paid') {
      show('upsell', true);
      var p = a.plans || {};
      $('upsellText').textContent = (a.status === 'free' ? 'You\\'re on the free weekly digest (the best new practices by name). ' : 'You\\'re on the free trial. ')
        + 'Plans: $' + (p.local||{}).price + '/mo for a local area, $' + (p.cat||{}).price + ' for one state and category, $' + (p.all||{}).price
        + ' for every category in a state, $' + (p.multi||{}).price + ' for three states. Yearly billing gets 2 months free.';
    }
    // downloads
    var rows = (a.deliveries || []).map(function(d){
      return '<tr><td>' + esc(d.week) + '</td><td class="muted">' + esc((d.files || []).join(', ')) + '</td><td class="r"><a href="' + W + '/dl?t=' + encodeURIComponent(t) + '&f=' + encodeURIComponent(d.file) + '">Download' + (d.bytes ? ' (' + Math.max(1, Math.round(d.bytes / 1024)) + ' KB)' : '') + '</a></td></tr>';
    });
    $('dlRows').innerHTML = rows.join('') || '<tr><td colspan="3" class="muted">Your first list appears here after it\\'s emailed.</td></tr>';
    // territory
    var local = a.plan === 'local' || !!a.area;
    show('areaBox', local); show('stateBox', !local);
    if (local) {
      var parts = (a.area || '').split(':');
      $('zip').value = parts[0] || ''; $('radius').value = parts[1] || 25;
      $('terrHelp').textContent = 'Every new practice within your radius of one ZIP code, every category (5 to 100 miles).';
    } else {
      var n = Math.max(1, a.max_states || 1), html = '';
      for (var i = 0; i < n; i++) {
        html += '<div><label for="st' + i + '">State' + (n > 1 ? ' ' + (i + 1) : '') + '</label><div class="sel"><select id="st' + i + '"><option value="">' + (i ? '(none)' : 'Pick a state') + '</option>'
          + a.states_all.slice().sort(function(x, y){ return (NAMES[x] || x) < (NAMES[y] || y) ? -1 : 1; }).map(function(s){ return '<option value="' + s + '"' + (a.states[i] === s ? ' selected' : '') + '>' + esc(NAMES[s] || s) + '</option>'; }).join('') + '</select></div></div>';
      }
      $('stateSels').innerHTML = html;
      var cs = (a.one_category ? [] : [['all', 'Every category']]).concat(a.categories_all.map(function(c){ return [c, NICE[c] || c]; }));
      if (a.one_category && a.status !== 'paid') cs = [['all', 'Every category']].concat(cs);
      $('cat').innerHTML = cs.map(function(c){ return '<option value="' + c[0] + '"' + (a.categories[0] === c[0] ? ' selected' : '') + '>' + esc(c[1]) + '</option>'; }).join('');
      show('catBox', !(a.status === 'paid' && !a.one_category));
      $('terrHelp').textContent = a.status === 'paid'
        ? 'Your plan covers ' + n + ' state' + (n > 1 ? 's' : '') + (a.one_category ? ' and one category.' : ', every category.')
        : 'The free plan covers one state.';
    }
    // team
    var room = Math.max(0, (a.seats || 1) - 1);
    $('team').value = (a.team || []).join('\\n');
    $('teamHelp').textContent = room ? 'Your plan includes ' + room + ' teammate' + (room > 1 ? 's' : '') + ': each gets a copy of every list email.'
      : 'Teammates come with the paid plans (2 to 10 people on one subscription).';
    $('team').disabled = !room;
    // roster
    $('roster').value = (a.roster || []).join('\\n');
    $('rosterLimit').textContent = a.roster_limit ? 'Your plan watches up to ' + a.roster_limit.toLocaleString() + ' providers.' : 'Roster Watch comes with the paid plans.';
    $('roster').disabled = !a.roster_limit;
    var rep = a.roster_report || [];
    if (rep.length) {
      show('rosterReport', true);
      $('rosterChecked').textContent = a.roster_checked ? '(checked ' + a.roster_checked + ')' : '';
      $('rosterRows').innerHTML = rep.map(function(r){ return '<tr><td>' + esc(r.npi) + '</td><td>' + esc(r.name) + '</td><td>' + esc(r.notes.join('; ')) + '</td></tr>'; }).join('');
    }
    // webhook
    $('hook').value = a.webhook || '';
    $('hook').disabled = a.status !== 'paid';
    if (a.status !== 'paid') $('hookCard').querySelector('.help').insertAdjacentText('beforeend', ' Comes with the paid plans.');
    $('updated').textContent = a.updated ? 'Page updated ' + a.updated.replace('T', ' ') + '.' : '';
  }

  $('terrForm').addEventListener('submit', function(e){
    e.preventDefault();
    if (!$('areaBox').classList.contains('hide')) {
      var z = $('zip').value.replace(/\\D/g, '');
      if (z.length !== 5) { msg('terrMsg', 'Please enter a 5-digit ZIP code.', false); return; }
      post('/change?t=' + encodeURIComponent(t), { change: { area: z + ':' + (parseInt($('radius').value, 10) || 25) } }, 'terrMsg', SAVED);
      return;
    }
    var states = [].slice.call(document.querySelectorAll('#stateSels select')).map(function(s){ return s.value; }).filter(Boolean);
    if (!states.length) { msg('terrMsg', 'Please pick a state.', false); return; }
    var cat = $('catBox').classList.contains('hide') ? 'all' : $('cat').value;
    post('/change?t=' + encodeURIComponent(t), { change: { states: states, categories: [cat] } }, 'terrMsg', SAVED);
  });
  $('teamForm').addEventListener('submit', function(e){
    e.preventDefault();
    var list = $('team').value.split(/[\\s,;]+/).filter(function(x){ return x.indexOf('@') > 0; });
    post('/change?t=' + encodeURIComponent(t), { change: { team: list } }, 'teamMsg', SAVED);
  });
  $('rosterForm').addEventListener('submit', function(e){
    e.preventDefault();
    var npis = ($('roster').value.match(/\\d{10}/g) || []);
    msg('rosterMsg', '', true);
    post('/change?t=' + encodeURIComponent(t), { change: { roster: npis } }, 'rosterMsg', SAVED.replace('Saved.', 'Saved ' + npis.length + ' NPI' + (npis.length === 1 ? '' : 's') + '.'));
  });
  $('hookForm').addEventListener('submit', function(e){
    e.preventDefault();
    var u = $('hook').value.trim();
    if (u && u.indexOf('https://') !== 0) { msg('hookMsg', 'The address must start with https://', false); return; }
    post('/change?t=' + encodeURIComponent(t), { change: { webhook: u } }, 'hookMsg', SAVED);
  });
})();
</script>
"""


SEARCH_CSS = """
.srch .tabs{display:flex;gap:8px;flex-wrap:wrap;margin:22px 0 14px}
.srch .tabs button{border:1.5px solid var(--line2);background:#fff;color:var(--ink);border-radius:999px;padding:9px 15px;font:600 14px Inter,sans-serif;cursor:pointer}
.srch .tabs button:hover{border-color:var(--teal)}
.srch .tabs button[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);color:#fff}
.srch .sighelp{color:var(--muted);font-size:14px;margin:0 0 14px;max-width:780px}
.srch .filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px 14px}
@media(max-width:860px){.srch .filters{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:520px){.srch .filters{grid-template-columns:1fr}}
.srch label{display:block;font-size:12.5px;color:var(--muted);font-weight:600;margin:0 0 6px}
.srch select,.srch input{width:100%;min-width:0;background:#fff;color:var(--ink);border:1.5px solid var(--line2);border-radius:10px;padding:10px 12px;font:500 15px Inter,sans-serif}
.srch select:focus,.srch input:focus,.srch .tabs button:focus-visible,.srch .trend div:focus-visible{outline:none;border-color:var(--teal);box-shadow:0 0 0 4px rgba(14,124,123,.16)}
.srch .zipbox{display:grid;grid-template-columns:1fr 92px;gap:8px}
.srch .hide{display:none!important}
.srch .result{margin-top:18px}
.srch .hero{display:flex;align-items:baseline;gap:6px 16px;flex-wrap:wrap}
.srch .hero b{font-family:"Source Serif 4",Georgia,serif;font-weight:600;font-size:clamp(44px,7vw,64px);line-height:1;color:var(--ink);font-variant-numeric:tabular-nums}
.srch .hero span{color:var(--muted);font-size:16px;max-width:620px}
.srch .sub{color:var(--muted);font-size:14px;margin:8px 0 0}
.srch .sub b{color:var(--ink)}
.srch .trend div{cursor:default;border-radius:6px}
.srch .trend i.off{opacity:.3}
.srch .trend b{min-height:15px}
.srch .bar{grid-template-columns:minmax(0,190px) 1fr 52px}
.srch .bar span.l{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
.srch .bar button.l{all:unset;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
.srch .bar button.l:hover,.srch .bar button.l:focus-visible{color:var(--teal);text-decoration:underline}
.srch .fill{background:linear-gradient(90deg,#14b8a6,var(--teal))}
.srch .tip{position:fixed;z-index:20;pointer-events:none;background:var(--ink);color:#fff;font-size:13px;line-height:1.35;padding:7px 10px;border-radius:8px;box-shadow:var(--shadow);max-width:260px}
.srch .state{padding:28px;text-align:center;color:var(--muted)}
.srch .mine{background:linear-gradient(135deg,rgba(14,124,123,.09),rgba(37,99,235,.04));border:1px solid rgba(14,124,123,.35)}
.srch .mine .cta{border:0;cursor:pointer}
.srch .empty{color:var(--dim);font-size:14px;padding:6px 0}
.srch details table td,.srch details table th{padding:6px 10px}
@media(max-width:480px){.srch .bar{grid-template-columns:minmax(0,120px) 1fr 44px}}
@media(max-width:600px){.srch .trend div:not(:nth-child(3n+1)) span{visibility:hidden}.srch .trend span{overflow:visible}}
"""

SEARCH_BODY = """
<div class="crumbs"><a href="../">PanelReady</a> › Live search</div>
<div class="srch">
<span class="kicker">Live search · free</span>
<h1>How many new practices are in <em>your</em> territory?</h1>
<p class="lead">Filter every new healthcare practice registered in the last 13 weeks, plus this month's <b>stuck in credentialing</b> and <b>Medicare revalidation</b> lists, by state, county, metro area, city, distance from a ZIP code, specialty and practice type. The counts change the moment you change a filter. <span id="asof"></span></p>

<div class="card mine hide" id="mineBox"><h2 style="margin:0 0 6px;font-size:21px">Your territory · export</h2>
  <p class="help" id="mineText" style="color:var(--muted);margin:0 0 4px">Loading your rows…</p>
  <button class="cta hide" type="button" id="exportBtn">Download these rows (CSV)</button>
</div>

<div class="tabs" role="group" aria-label="Which list" id="tabs"></div>
<p class="sighelp" id="sigHelp"></p>

<div class="card">
  <div class="filters">
    <div><label for="fSt">State</label><div class="sel"><select id="fSt"></select></div></div>
    <div><label for="fArea">Area</label><div class="sel"><select id="fArea"></select></div></div>
    <div id="boxCounty" class="hide"><label for="fCounty">County</label><div class="sel"><select id="fCounty"></select></div></div>
    <div id="boxMetro" class="hide"><label for="fMetro">Metro area</label><div class="sel"><select id="fMetro"></select></div></div>
    <div id="boxCity" class="hide"><label for="fCity">City</label><input id="fCity" list="cityList" placeholder="Start typing a city" autocomplete="off"><datalist id="cityList"></datalist></div>
    <div id="boxZip" class="hide"><label for="fZip">Within this distance of a ZIP</label><div class="zipbox"><input id="fZip" inputmode="numeric" maxlength="5" placeholder="ZIP code" autocomplete="postal-code"><div class="sel"><select id="fMiles" aria-label="Miles"></select></div></div></div>
    <div><label for="fCat">Category</label><div class="sel"><select id="fCat"></select></div></div>
    <div><label for="fSpec">Specialty</label><div class="sel"><select id="fSpec"></select></div></div>
    <div><label for="fEnt">Practice type</label><div class="sel"><select id="fEnt"><option value="">Organizations and sole proprietors</option><option value="0">Organizations (group practices, clinics, agencies)</option><option value="1">Sole proprietors</option></select></div></div>
    <div id="boxWeeks"><label for="fWeeks">Registered</label><div class="sel"><select id="fWeeks"><option value="13">In the last 13 weeks</option><option value="8">In the last 8 weeks</option><option value="4">In the last 4 weeks</option><option value="1">In the newest week</option></select></div></div>
  </div>
</div>

<div class="result" id="result" aria-live="polite">
  <div class="card state" id="loading">Loading the counts…</div>
  <div id="out" class="hide">
    <div class="card">
      <div class="hero"><b id="total">0</b><span id="totalText"></span></div>
      <p class="sub" id="totalSub"></p>
      <div class="btns" id="ctaRow"><a class="cta" id="cta" href="../#free">Get these as a free weekly list</a><a class="cta ghost" href="../#pricing">See plans</a></div>
    </div>
    <div class="card" id="weekCard" style="margin-top:16px"><h2 style="font-size:20px;margin:0">Week by week</h2>
      <div class="trend" id="weekBars" role="img"></div>
      <details><summary>The numbers</summary><div class="tscroll"><table><thead><tr><th>Week ending</th><th class="r">Count</th></tr></thead><tbody id="weekRows"></tbody></table></div></details>
    </div>
    <div class="grid2" style="margin-top:16px">
      <div class="card"><h2 style="font-size:20px" id="whereTitle">Where</h2><div id="whereBars"></div></div>
      <div class="card"><h2 style="font-size:20px">Top specialties</h2><div id="specBars"></div></div>
    </div>
  </div>
</div>

<section class="prose" style="margin-top:34px">
<h2>Where the numbers come from</h2>
<p>New practices come from the federal NPPES registry's weekly files (organizations and sole proprietors; employees and students who get an NPI only to work somewhere else are left out). <b>Moved</b> is a practice whose registered address changed to a new location. <b>Stuck in credentialing</b> is a practice that registered 2 to 12 months ago in a specialty that normally bills Medicare and still isn't on Medicare's public enrollment list. <b>Revalidation due</b> is Medicare's own list of enrollments due from 90 days ago through the next six months. Counts are rebuilt every week; the two monthly lists, every month.</p>
<p>This page shows counts only. The lists themselves come with the practice phone, the owner's name and own phone, the address, the specialty, a score and an opener for every row: <a href="../#free">two weekly lists are free</a>.</p>
</section>
<div class="tip hide" id="tip" role="tooltip"></div>
</div>
<script>
(function(){
  var W = '__WORKER__';
  var NICE = __NICE__, NAMES = __NAMES__, NEAR = __NEAR__;
  var CATS = ['behavioral', 'medical', 'dental', 'therapy', 'home_senior', 'dme_transport'];
  var SIG = {
    'new': { label: 'New practices', noun: 'new practices', weekly: true,
      help: 'Organizations and sole proprietors that registered an NPI, counted by the week they registered.' },
    'moved': { label: 'Moved', noun: 'practices that moved', weekly: true,
      help: 'Practices whose registered address changed to a new location, by the week the change was published.' },
    'stuck': { label: 'Stuck in credentialing', noun: 'practices stuck in credentialing', weekly: false,
      help: 'Registered 2 to 12 months ago and still not on Medicare\\u2019s public enrollment list: usually credentialing hasn\\u2019t started or has stalled. This month\\u2019s list.' },
    'reval': { label: 'Revalidation due', noun: 'Medicare revalidations due', weekly: false,
      help: 'Medicare enrollments due for revalidation, from 90 days overdue to six months out. This month\\u2019s list.' }
  };
  var ORDER = ['new', 'moved', 'stuck', 'reval'];
  var MILES = [5, 10, 15, 25, 50, 75, 100];
  var $ = function(id){ return document.getElementById(id); };
  var fmt = function(n){ return Math.round(n).toLocaleString('en-US'); };
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function shortDate(iso){ var p = iso.split('-'); return MON[+p[1] - 1] + ' ' + (+p[2]); }
  function longDate(iso){ var p = iso.split('-'); return MON[+p[1] - 1] + ' ' + (+p[2]) + ', ' + p[0]; }
  var token = (location.hash.match(/[#&]t=([A-Za-z0-9_-]{20,64})/) || [])[1] || '';

  // ---- filter state, kept in the address so a search can be shared or bookmarked
  var S = { sig: 'new', st: '', area: 'state', county: '', metro: '', city: '', zip: '', miles: 25, cat: '', spec: '', ent: '', weeks: 13 };
  (function readHash(){
    location.hash.replace(/^#/, '').split('&').forEach(function(kv){
      var i = kv.indexOf('='); if (i < 1) return; var k = kv.slice(0, i), v = decodeURIComponent(kv.slice(i + 1));
      if (k in S && k !== 't') S[k] = (k === 'miles' || k === 'weeks') ? (+v || S[k]) : v;
    });
    if (ORDER.indexOf(S.sig) < 0) S.sig = 'new';
  })();
  function writeHash(){
    var parts = token ? ['t=' + token] : [];
    var def = { sig: 'new', st: '', area: 'state', county: '', metro: '', city: '', zip: '', miles: 25, cat: '', spec: '', ent: '', weeks: 13 };
    Object.keys(S).forEach(function(k){ if (S[k] !== def[k] && S[k] !== '') parts.push(k + '=' + encodeURIComponent(S[k])); });
    try { history.replaceState(null, '', location.pathname + location.search + (parts.length ? '#' + parts.join('&') : '')); } catch (e) {}
  }

  // ---- data
  var INDEX = null, FILES = {}, MINE = null, MINE_ROWS = null, PENDING = {};
  function getJSON(url){ return fetch(url).then(function(r){ if (!r.ok) throw new Error(r.status); return r.json(); }); }
  function loadState(st){
    if (FILES[st]) return Promise.resolve(FILES[st]);
    if (PENDING[st]) return PENDING[st];
    PENDING[st] = getJSON(W + '/search?f=' + st).then(function(f){ prep(f); FILES[st] = f; return f; })
      .catch(function(){ FILES[st] = null; return null; });
    return PENDING[st];
  }
  function prep(f){                       // turn the compact arrays into rows the filters can read
    f.zmap = {}; f.zips.forEach(function(z, i){ f.zmap[z] = i; });
    f.cmap = {}; (f.zc || []).forEach(function(c){ f.cmap[c[0]] = [c[1], c[2]]; });
    f.rows = f.r.map(function(x){
      var g = f.zg[x[2]] || [null, null, -1, -1], c = g[2] >= 0 ? f.counties[g[2]] : null, sp = f.specs[x[3]];
      return { s: x[0], w: x[1], n: x[5], e: x[4], spec: sp[0], cat: sp[1], st: f.st, zip: f.zips[x[2]], lat: g[0], lon: g[1],
               county: c ? c[0] : '', countyName: c ? c[1] : '', metro: c && c[2] >= 0 ? f.metros[c[2]] : '', city: g[3] >= 0 ? f.cities[g[3]] : '' };
    });
  }
  function centre(zip){                   // [lat, lon] of a ZIP, from any loaded state file
    for (var st in FILES) { var f = FILES[st]; if (!f) continue;
      if (zip in f.zmap) { var g = f.zg[f.zmap[zip]]; if (g[0] != null) return [g[0], g[1]]; }
      if (f.cmap[zip]) return f.cmap[zip]; }
    return null;
  }
  function miles(a, b){
    var r = Math.PI / 180, dLat = (b[0] - a[0]) * r, dLon = (b[1] - a[1]) * r;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 3958.8 * 2 * Math.asin(Math.sqrt(h));
  }
  function zipState(zip){ return INDEX && INDEX.z3 ? INDEX.z3[zip.slice(0, 3)] || '' : ''; }

  // ---- the subscriber's own rows (from the account link): gzipped JSON with every column
  function loadMine(){
    $('mineBox').classList.remove('hide');
    if (!window.DecompressionStream) { $('mineText').textContent = 'This browser can\\u2019t open the export file. Try a current Chrome, Edge, Firefox or Safari.'; return Promise.resolve(); }
    return fetch(W + '/dl?t=' + token + '&f=search').then(function(r){
      if (!r.ok) throw new Error(r.status);
      return new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json();
    }).then(function(m){
      if (m && m.locked) throw new Error('locked');
      MINE = m; MINE_ROWS = [];
      ORDER.forEach(function(sig, s){
        var L = m.lists[sig]; if (!L) return;
        var h = {}; L.header.forEach(function(k, i){ h[k] = i; });
        L.rows.forEach(function(v, i){
          var cat = CATS.indexOf(v[h.category]);
          if (cat < 0) return;
          MINE_ROWS.push({ s: s, w: L.w[i], n: 1, e: v[h.entity] === 'practice/organization' ? 0 : 1, spec: v[h.specialty] || 'Other specialty',
                           cat: cat, st: v[h.state], zip: String(v[h.zip] || '').slice(0, 5), raw: v, sig: sig });
        });
      });
      var states = {}; MINE_ROWS.forEach(function(r){ states[r.st] = 1; });
      return Promise.all(Object.keys(states).slice(0, 12).map(loadState)).then(function(){
        MINE_ROWS.forEach(function(r){
          var f = FILES[r.st]; if (!f || !(r.zip in f.zmap)) return;
          var g = f.zg[f.zmap[r.zip]], c = g[2] >= 0 ? f.counties[g[2]] : null;
          r.lat = g[0]; r.lon = g[1]; r.county = c ? c[0] : ''; r.countyName = c ? c[1] : '';
          r.metro = c && c[2] >= 0 ? f.metros[c[2]] : ''; r.city = g[3] >= 0 ? f.cities[g[3]] : '';
        });
        $('exportBtn').classList.remove('hide');
      });
    }).catch(function(e){
      MINE = null; MINE_ROWS = null;
      $('mineText').textContent = (e && e.message === 'locked')
        ? 'Exporting your own rows is for active subscribers. If you just subscribed, they appear with your next weekly list. Until then this page shows public counts.'
        : 'Your export file isn\\u2019t ready yet: it\\u2019s built with each weekly list, so it appears after your next one. Until then this page shows public counts.';
    });
  }

  // ---- which rows answer the current filters
  function source(){
    if (MINE_ROWS) return { rows: MINE_ROWS, geo: true, mine: true };
    if (S.area === 'radius' && /^\\d{5}$/.test(S.zip)) {
      var home = zipState(S.zip) || S.st;
      var sts = [home].concat((NEAR[home] || '').split(' ')).filter(Boolean);
      var rows = []; sts.forEach(function(st){ if (FILES[st]) rows = rows.concat(FILES[st].rows); });
      return { rows: rows, geo: true, need: sts.filter(function(st){ return !(st in FILES); }) };
    }
    if (S.st) {
      if (!(S.st in FILES)) return { rows: [], need: [S.st] };
      if (FILES[S.st]) return { rows: FILES[S.st].rows, geo: true };
    }
    return { rows: INDEX ? INDEX.rows : [], geo: false };
  }
  function matcher(src){
    var s = ORDER.indexOf(S.sig), weekly = SIG[S.sig].weekly, w0 = (INDEX ? INDEX.weeks.length : 13) - S.weeks;
    var cat = S.cat ? CATS.indexOf(S.cat) : -1, ent = S.ent === '' ? -1 : +S.ent;
    var c = S.area === 'radius' && /^\\d{5}$/.test(S.zip) ? centre(S.zip) : null;
    return function(r, ignoreWeeks){
      if (r.s !== s) return false;
      if (weekly && !ignoreWeeks && r.w < w0) return false;
      if (cat >= 0 && r.cat !== cat) return false;
      if (S.spec && r.spec !== S.spec) return false;
      if (ent >= 0 && r.e !== ent) return false;
      if (S.area === 'radius') {
        if (!/^\\d{5}$/.test(S.zip)) return S.st ? r.st === S.st : true;
        if (!c || r.lat == null) return false;
        return miles(c, [r.lat, r.lon]) <= S.miles;
      }
      if (S.st && r.st !== S.st) return false;
      if (!src.geo) return true;
      if (S.area === 'county' && S.county) return r.county === S.county;
      if (S.area === 'metro' && S.metro) return r.metro === S.metro;
      if (S.area === 'city' && S.city) return r.city && r.city.toLowerCase() === S.city.toLowerCase();
      return true;
    };
  }

  // ---- controls
  function opt(sel, items, value){             // items: [[value, label]]
    sel.innerHTML = items.map(function(it){ return '<option value="' + esc(it[0]) + '">' + esc(it[1]) + '</option>'; }).join('');
    sel.value = value; if (sel.value !== String(value) && items.length) { sel.value = items[0][0]; }
    return sel.value;
  }
  function byName(a, b){ return a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0; }
  function paintTabs(){
    $('tabs').innerHTML = ORDER.map(function(k){ return '<button type="button" data-k="' + k + '" aria-pressed="' + (S.sig === k) + '">' + SIG[k].label + '</button>'; }).join('');
    $('sigHelp').textContent = SIG[S.sig].help + (S.sig === 'moved' && INDEX ? movedNote() : '');
  }
  function movedNote(){
    var first = null; INDEX.rows.forEach(function(r){ if (r.s === 1 && (first === null || r.w < first)) first = r.w; });
    return first === null ? '' : ' Tracked from the week ending ' + longDate(INDEX.weeks[first]) + '.';
  }
  function paintControls(){
    var missing = (INDEX && INDEX.geo_missing) || [];
    var states = (MINE_ROWS ? Object.keys(MINE_ROWS.reduce(function(a, r){ a[r.st] = 1; return a; }, {})) : (INDEX ? INDEX.states : []))
      .filter(function(st){ return NAMES[st]; }).map(function(st){ return [st, NAMES[st]]; }).sort(byName);
    S.st = opt($('fSt'), [['', MINE_ROWS ? 'All of my territory' : 'All states']].concat(states), S.st);
    var areas = S.st ? [['state', 'The whole state']] : [['state', MINE_ROWS ? 'All of it' : 'Everywhere']];
    var f = S.st ? FILES[S.st] : null;
    if (S.st && missing.indexOf('counties') < 0) areas.push(['county', 'One county']);
    if (S.st && missing.indexOf('metro areas') < 0 && missing.indexOf('counties') < 0) areas.push(['metro', 'One metro area']);
    if (S.st) areas.push(['city', 'One city']);
    if (missing.indexOf('zip centres') < 0) areas.push(['radius', 'Within a distance of a ZIP']);
    S.area = opt($('fArea'), areas, S.area);
    $('boxCounty').classList.toggle('hide', S.area !== 'county');
    $('boxMetro').classList.toggle('hide', S.area !== 'metro');
    $('boxCity').classList.toggle('hide', S.area !== 'city');
    $('boxZip').classList.toggle('hide', S.area !== 'radius');
    if (f && S.area === 'county') S.county = opt($('fCounty'), [['', 'Pick a county']].concat(f.counties.map(function(c){ return [c[0], c[1]]; }).sort(byName)), S.county);
    if (f && S.area === 'metro') {
      var ms = {}; f.counties.forEach(function(c){ if (c[2] >= 0) ms[f.metros[c[2]]] = 1; });
      S.metro = opt($('fMetro'), [['', 'Pick a metro area']].concat(Object.keys(ms).sort().map(function(m){ return [m, m]; })), S.metro);
    }
    if (f && S.area === 'city') { $('cityList').innerHTML = f.cities.slice().sort().map(function(c){ return '<option value="' + esc(c) + '">'; }).join(''); $('fCity').value = S.city; }
    if (S.area === 'radius') { $('fZip').value = S.zip; S.miles = +opt($('fMiles'), MILES.map(function(m){ return [m, m + ' miles']; }), S.miles); }
    S.cat = opt($('fCat'), [['', 'All six categories']].concat(CATS.map(function(c){ return [c, NICE[c]]; })), S.cat);
    var src = source(), counts = {}, s = ORDER.indexOf(S.sig), cat = S.cat ? CATS.indexOf(S.cat) : -1;
    src.rows.forEach(function(r){ if (r.s === s && (cat < 0 || r.cat === cat)) counts[r.spec] = (counts[r.spec] || 0) + r.n; });
    var specs = Object.keys(counts).sort().map(function(k){ return [k, k]; });
    if (S.spec && !counts[S.spec]) specs.unshift([S.spec, S.spec]);
    S.spec = opt($('fSpec'), [['', 'Every specialty']].concat(specs), S.spec);
    $('fEnt').value = S.ent;
    $('boxWeeks').classList.toggle('hide', !SIG[S.sig].weekly);
    $('fWeeks').value = String(S.weeks); if ($('fWeeks').value !== String(S.weeks)) { S.weeks = 13; $('fWeeks').value = '13'; }
  }

  // ---- results
  var tip = $('tip');
  function showTip(el, text){
    tip.textContent = text; tip.classList.remove('hide');
    var b = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
    tip.style.left = Math.max(8, Math.min(window.innerWidth - t.width - 8, b.left + b.width / 2 - t.width / 2)) + 'px';
    tip.style.top = Math.max(8, b.top - t.height - 8) + 'px';
  }
  function hideTip(){ tip.classList.add('hide'); }
  function barList(el, pairs, unit, onPick){
    if (!pairs.length) { el.innerHTML = '<div class="empty">Nothing matches.</div>'; return; }
    var max = Math.max.apply(null, pairs.map(function(p){ return p[1]; })) || 1;
    el.innerHTML = pairs.map(function(p, i){
      var label = onPick ? '<button class="l" type="button" data-i="' + i + '" title="' + esc(p[0]) + '">' + esc(p[0]) + '</button>' : '<span class="l" title="' + esc(p[0]) + '">' + esc(p[0]) + '</span>';
      return '<div class="bar">' + label + '<div class="trk"><div class="fill" style="width:' + Math.max(2, 100 * p[1] / max).toFixed(1) + '%"></div></div><div class="v">' + fmt(p[1]) + '</div></div>';
    }).join('');
    if (onPick) [].forEach.call(el.querySelectorAll('button.l'), function(b){ b.onclick = function(){ onPick(pairs[+b.getAttribute('data-i')]); }; });
  }
  function top(map, n){
    var unknown = function(k){ return / not known$/.test(k) ? 1 : 0; };
    return Object.keys(map).map(function(k){ return [k, map[k]]; })
      .sort(function(a, b){ return unknown(a[0]) - unknown(b[0]) || b[1] - a[1] || (a[0] < b[0] ? -1 : 1); }).slice(0, n);
  }
  function where(){                       // the place, with its preposition: "in Kings County, New York"
    if (S.area === 'radius' && /^\\d{5}$/.test(S.zip)) return 'within ' + S.miles + ' miles of ZIP ' + S.zip;
    if (!S.st) return MINE_ROWS ? 'in your territory' : 'in the US';
    var f = FILES[S.st], name = NAMES[S.st];
    if (S.area === 'county' && S.county && f) { var c = f.counties.filter(function(x){ return x[0] === S.county; })[0]; return 'in ' + (c ? c[1] : 'the county') + ', ' + name; }
    if (S.area === 'metro' && S.metro) return 'in the ' + S.metro + ' metro area';
    if (S.area === 'city' && S.city) return 'in ' + S.city + ', ' + name;
    return 'in ' + name;
  }
  function render(){
    var src = source();
    if (src.need && src.need.length) {
      $('loading').textContent = 'Loading ' + src.need.map(function(st){ return NAMES[st] || st; }).join(', ') + '…';
      $('loading').classList.remove('hide'); $('out').classList.add('hide');
      Promise.all(src.need.map(loadState)).then(function(){ paintControls(); render(); });
      return;
    }
    if (S.area === 'radius' && /^\\d{5}$/.test(S.zip) && !centre(S.zip)) {
      $('loading').textContent = 'We don\\u2019t have a location for ZIP ' + S.zip + ' (it may be a PO-box-only ZIP). Try a nearby one.';
      $('loading').classList.remove('hide'); $('out').classList.add('hide'); return;
    }
    $('loading').classList.add('hide'); $('out').classList.remove('hide');
    var m = matcher(src), weekly = SIG[S.sig].weekly, weeks = INDEX.weeks, total = 0, orgs = 0, byWeek = weeks.map(function(){ return 0; });
    var specs = {}, places = {}, mode = !S.st && !(S.area === 'radius' && /^\\d{5}$/.test(S.zip)) ? 'state'
      : S.area === 'city' && S.city ? 'zip' : S.area === 'state' && src.geo && (INDEX.geo_missing || []).indexOf('counties') < 0 ? 'county' : 'city';
    var picked = [];
    src.rows.forEach(function(r){
      if (weekly && r.w >= 0 && m(r, true)) byWeek[r.w] += r.n;
      if (!m(r)) return;
      total += r.n; if (r.e === 0) orgs += r.n;
      specs[r.spec] = (specs[r.spec] || 0) + r.n;
      var p = mode === 'state' ? (NAMES[r.st] || r.st) : mode === 'county' ? (r.countyName || 'County not known') : mode === 'zip' ? r.zip : (r.city || 'City not known');
      places[p] = (places[p] || 0) + r.n;
      if (src.mine) picked.push(r);
    });
    $('total').textContent = fmt(total);
    var noun = SIG[S.sig].noun;
    if (S.spec) noun = noun.replace('practices', S.spec.toLowerCase() + ' practices');
    else if (S.cat) noun = noun.replace('practices', NICE[S.cat].toLowerCase());
    var span = weekly ? (S.weeks === 1 ? ' in the week ending ' + longDate(weeks[weeks.length - 1]) : ' in the last ' + S.weeks + ' weeks') : '';
    $('totalText').textContent = noun + ' ' + where() + span + '.';
    var sub = [];
    if (total) sub.push('<b>' + Math.round(100 * orgs / total) + '%</b> organizations, ' + Math.round(100 * (total - orgs) / total) + '% sole proprietors');
    if (weekly && total && S.weeks > 1) sub.push('about <b>' + fmt(total / S.weeks) + '</b> a week');
    $('totalSub').innerHTML = sub.join(' · ');
    // call to action: the free list for this state and category (or the subscriber's export)
    $('ctaRow').classList.toggle('hide', !!src.mine);
    var q = []; var st = S.st || (S.area === 'radius' ? zipState(S.zip) : '');
    if (st) q.push('state=' + st); if (S.cat) q.push('cat=' + S.cat);
    if (S.area === 'radius' && /^\\d{5}$/.test(S.zip)) q.push('zip=' + S.zip, 'radius=' + S.miles);
    $('cta').href = '../' + (q.length ? '?' + q.join('&') : '') + '#free';
    $('cta').textContent = 'Get the full list free';
    // week by week
    $('weekCard').classList.toggle('hide', !weekly);
    if (weekly) {
      var max = Math.max.apply(null, byWeek) || 1, first = weeks.length - S.weeks, maxI = byWeek.indexOf(Math.max.apply(null, byWeek));
      $('weekBars').setAttribute('aria-label', noun + ' per week, ' + where());
      var PLOT = 104;                     // px: the bar area, below the value labels and above the dates
      $('weekBars').innerHTML = byWeek.map(function(n, i){
        var label = (i === weeks.length - 1 || i === maxI) ? fmt(n) : '';
        return '<div tabindex="0" data-t="Week ending ' + longDate(weeks[i]) + ': ' + fmt(n) + '"><b>' + label + '</b><i class="' + (i < first ? 'off' : '') + '" style="height:' + Math.max(n ? 3 : 1, PLOT * n / max).toFixed(0) + 'px"></i><span>' + shortDate(weeks[i]) + '</span></div>';
      }).join('');
      [].forEach.call($('weekBars').children, function(d){
        d.onmouseenter = d.onfocus = function(){ showTip(d, d.getAttribute('data-t')); };
        d.onmouseleave = d.onblur = hideTip;
      });
      $('weekRows').innerHTML = byWeek.map(function(n, i){ return '<tr><td>' + longDate(weeks[i]) + '</td><td class="r">' + fmt(n) + '</td></tr>'; }).reverse().join('');
    }
    // where and what
    $('whereTitle').textContent = { state: 'By state', county: 'By county', city: 'By city', zip: 'By ZIP code' }[mode];
    barList($('whereBars'), top(places, 12), '', mode === 'state' && !src.mine ? function(p){
      var code = Object.keys(NAMES).filter(function(k){ return NAMES[k] === p[0]; })[0]; if (code) { S.st = code; S.area = 'state'; update(); }
    } : mode === 'county' && FILES[S.st] ? function(p){
      var c = FILES[S.st].counties.filter(function(x){ return x[1] === p[0]; })[0]; if (c) { S.area = 'county'; S.county = c[0]; update(); }
    } : null);
    barList($('specBars'), top(specs, 10), '', function(p){ S.spec = p[0]; update(); });
    // subscriber export
    if (src.mine) {
      $('mineText').innerHTML = '<b>' + fmt(picked.length) + '</b> of your rows match these filters, with every column (phones, owners, openers). Updated with each weekly list (as of the week ending ' + longDate(MINE.asof) + ').';
      $('exportBtn').textContent = 'Download ' + fmt(picked.length) + ' rows (CSV)';
      $('exportBtn').disabled = !picked.length;
      $('exportBtn').onclick = function(){ download(picked); };
    }
  }
  function csvCell(v){ v = v == null ? '' : String(v); return /[",\\n\\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function download(rows){
    if (!rows.length) return;
    var L = MINE.lists[rows[0].sig], lines = [L.header.map(csvCell).join(',')];
    rows.forEach(function(r){ lines.push(r.raw.map(csvCell).join(',')); });
    var blob = new Blob(['\\ufeff' + lines.join('\\r\\n')], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = 'PanelReady_' + S.sig + '_' + where().replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '') + '_' + MINE.asof + '.csv';
    document.body.appendChild(a); a.click(); setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function update(){ paintTabs(); paintControls(); writeHash(); render(); }

  // ---- wiring
  $('tabs').onclick = function(e){ var b = e.target.closest('button'); if (!b) return; S.sig = b.getAttribute('data-k'); S.spec = ''; update(); };
  $('fSt').onchange = function(){ S.st = this.value; S.county = S.metro = S.city = ''; if (S.area !== 'radius') S.area = 'state'; update(); };
  $('fArea').onchange = function(){ S.area = this.value; update(); };
  $('fCounty').onchange = function(){ S.county = this.value; update(); };
  $('fMetro').onchange = function(){ S.metro = this.value; update(); };
  $('fCity').onchange = function(){ S.city = this.value.trim(); update(); };
  $('fZip').oninput = function(){ var z = this.value.replace(/\\D/g, '').slice(0, 5); if (z !== this.value) this.value = z; if (z.length === 5 || !z) { S.zip = z; update(); } };
  $('fMiles').onchange = function(){ S.miles = +this.value; update(); };
  $('fCat').onchange = function(){ S.cat = this.value; S.spec = ''; update(); };
  $('fSpec').onchange = function(){ S.spec = this.value; update(); };
  $('fEnt').onchange = function(){ S.ent = this.value; update(); };
  $('fWeeks').onchange = function(){ S.weeks = +this.value; update(); };

  getJSON(W + '/search?f=index').then(function(ix){
    ix.rows = ix.r.map(function(x){ var sp = ix.specs[x[3]]; return { s: x[0], w: x[1], st: ix.states[x[2]], spec: sp[0], cat: sp[1], e: x[4], n: x[5] }; });
    INDEX = ix;
    $('asof').textContent = 'Updated for the week ending ' + longDate(ix.asof) + '.';
    return token ? loadMine() : null;
  }).then(function(){
    if (MINE_ROWS && MINE) INDEX.weeks = MINE.weeks;
    update();
  }).catch(function(){
    $('loading').textContent = 'The counts are being refreshed. Please try again in a few minutes.';
  });
})();
</script>
"""


def search_page() -> str:
    body = (SEARCH_BODY.replace("__WORKER__", WORKER)
            .replace("__NICE__", json.dumps(CAT_TITLE))
            .replace("__NAMES__", json.dumps(STATES))
            .replace("__NEAR__", json.dumps(NEIGHBORS)))
    page = shell(f"Live search: new healthcare practices by county, metro and specialty | {BRAND}",
                 "Free live counts of new healthcare practices, practices stuck in credentialing and Medicare revalidations "
                 "due, by state, county, metro area, city, ZIP radius, specialty and practice type. For credentialing and "
                 "billing companies.", "search/", body)
    return page.replace("<style>", "<style>" + SEARCH_CSS, 1)


def write_search():
    d = HERE / "search"
    d.mkdir(exist_ok=True)
    (d / "index.html").write_text(search_page(), encoding="utf-8")


def account_page() -> str:
    body = (ACCOUNT_BODY.replace("__WORKER__", WORKER)
            .replace("__NICE__", json.dumps(CAT_TITLE))
            .replace("__NAMES__", json.dumps(STATES)))
    page = shell(f"Your account — {BRAND}", f"Your {BRAND} subscription: past lists, territory, teammates and Roster Watch.",
                 "account/", body)
    return page.replace("<style>", '<meta name="robots" content="noindex, nofollow">\n<style>' + ACCOUNT_CSS, 1)


def write_account():
    d = HERE / "account"
    d.mkdir(exist_ok=True)
    (d / "index.html").write_text(account_page(), encoding="utf-8")


def write_sample(data: dict) -> str | None:
    """sample/panelready-sample.csv: one small state's complete list for the newest week, every column, nothing masked.
    Written from the week ingested this run (PC or GitHub), else from output\\<week>\\leads_US_all.csv on the PC."""
    leads = LATEST_LEADS
    if not leads:
        src = ROOT / "output" / (data["latest"] or "") / "leads_US_all.csv"
        if not src.exists():
            return None                                  # nothing new this run and no local files: the existing sample stays
        with open(src, encoding="utf-8", newline="") as f:
            leads = list(csv.DictReader(f))
    week = data["counts"][data["latest"]]
    pick = next((st for st in SAMPLE_STATES if 8 <= sum(week.get(st, [0])) <= 25), None) or next((st for st in SAMPLE_STATES if week.get(st)), None)
    if not pick:
        return None
    rows = [r for r in leads if r["state"] == pick and r["category"] in CATS]
    header = N.LEAD_HEADER
    (HERE / "sample").mkdir(exist_ok=True)
    with open(HERE / "sample" / "panelready-sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    data["sample"] = {"state": pick, "week": data["latest"], "rows": len(rows)}
    return pick


# ------------------------------------------------------------------ landing page refresh

LANDING_WORDING = [
    ("Your first spreadsheet goes out with the next weekly federal file, the second one the week after. No call, no card.",
     "Your first spreadsheet arrives within minutes, the second with the following week's federal file. No call, no card."),
    ("Your first spreadsheet arrives by the next morning, the second with the following week's federal file. No call, no card.",
     "Your first spreadsheet arrives within minutes, the second with the following week's federal file. No call, no card."),
    ("Or use a ZIP code and a radius to get just the practices near you.</p>",
     "Or use a ZIP code and a radius to get just the practices near you. Free lists have the weekly spreadsheet, the practices "
     "that moved or changed, the CRM file and the outreach kit; the 90-day history, monthly lists and account page come with a "
     "subscription.</p>"),
    ("You'll get a confirmation by email within a day, then the lists on the next two federal files.",
     "You'll get a confirmation by email right away and your first list within minutes; the second follows a week later."),
    ("You'll get a confirmation by email within the hour and your first list by the next morning; the second follows a week later.",
     "You'll get a confirmation by email right away and your first list within minutes; the second follows a week later."),
    ("<b>1 · Next weekly file</b>Your first spreadsheet: every new practice in your state and category, sorted best-first",
     "<b>1 · Within minutes</b>Your first spreadsheet: every new practice in your state and category from the latest federal file, sorted best-first"),
    ("<b>1 · By the next morning</b>Your first spreadsheet:", "<b>1 · Within minutes</b>Your first spreadsheet:"),
    ("It's emailed to your PayPal address within the hour.</p>", "It's emailed to your PayPal address within minutes.</p>"),
    ("Every plan includes the full list, the monthly lists, Roster Watch, teammates and the 90-day guarantee.",
     "Every plan includes the full list, the last 90 days on day one, the monthly lists, Roster Watch, teammates, your account page and the 90-day guarantee."),
    ("Cancel from your PayPal account any time; the lists stop at the end of the paid month.",
     "Cancel from your PayPal account any time; your lists continue to the end of the period you've paid for."),
    ("One more thing so the right list goes out with the next weekly file: which state, and where to send it?",
     "One more thing so your first list (with the last 90 days) goes out right away: which state, and where to send it?"),
    ("One more thing so your first list (with the last 90 days) goes out tomorrow morning: which state, and where to send it?",
     "One more thing so your first list (with the last 90 days) goes out right away: which state, and where to send it?"),
    ("Your account page (link in every email) lets you change it later and add teammates.",
     "Your account page (the link in every list email, or Account at the top of this page) lets you change it later and add teammates."),
    ("Each email also carries a private link to your account page, where you can",
     "Each list email also carries a private link to your account page (or sign in from Account at the top of the page), where you can"),
    ("In your PayPal account under Subscriptions, any time, or reply STOP to any email. No calls, no forms.",
     "In your PayPal account under Subscriptions, any time: your lists and account page continue to the end of the period you've paid "
     "for. Or reply STOP to any email: our emails stop right away and we cancel the PayPal subscription for you. No calls, no forms."),
    ("Or subscribe above and your first list goes out with the next weekly file.",
     "Or subscribe above and your first list, with the last 90 days, arrives within minutes."),
    ("Or subscribe above and your first list, with the last 90 days, goes out the next morning.",
     "Or subscribe above and your first list, with the last 90 days, arrives within minutes."),
    ("Your first list includes the last 90 days. A private account page holds past weeks,",
     "Your first paid list includes the last 90 days. Subscribers get a private account page with past weeks,"),
    ("goes out with the next weekly federal file, usually Monday or Tuesday morning, from",
     "arrives within minutes, from"),
    ("goes out with the next weekly file, with the last 90 days attached.",
     "is on its way: it arrives within minutes, with the last 90 days attached."),
    ("goes out by tomorrow morning, with the last 90 days attached.", "is on its way: it arrives within minutes, with the last 90 days attached."),
    ("') arrives by tomorrow morning (around 7 AM Eastern), from matt@panelready.co.",
     "') ' + (function(){ if (body.zip) return 'arrives within minutes'; var d = DATA[String(body.state || '').split(',')[0]] || [], "
     "i = CATS.indexOf(body.category), n = i >= 0 ? (d[i] || 0) : d.reduce(function(a, x){ return a + x; }, 0); "
     "return n ? 'arrives within minutes' : 'goes out with the next weekly federal file (this week\\'s had no new practices for your pick)'; })()"
     " + ', from matt@panelready.co."),
    ("Do I get email addresses?</summary><p>For organizations, where we can find one.",
     "Do I get email addresses?</summary><p>For organizations, where we can find one (on the two free lists, for the top 25)."),
]


def refresh_landing(data: dict) -> list[str]:
    """Update the numbers baked into index.html (state picker, stats, dates). Each edit is skipped if its anchor isn't found."""
    p = HERE / "index.html"
    if not p.exists():
        return ["index.html not found"]
    s = p.read_text(encoding="utf-8")
    latest, week, nat = data["latest"], data["counts"][data["latest"]], data["national"]
    done, miss = [], []

    def sub(label, pattern, repl, flags=0):
        nonlocal s
        new, n = re.subn(pattern, repl, s, count=1, flags=flags)
        (done if n else miss).append(label)
        s = new
    js = json.dumps({k: week[k] for k in sorted(week) if k in STATES}, separators=(",", ":"))
    sub("DATA", r"(// counts per state for the week ending )\d{4}-\d{2}-\d{2}(.*\n\s*var DATA = )\{.*?\};", lambda m: f"{m.group(1)}{latest}{m.group(2)}{js};")
    sub("wk", r'(<span id="wk">week ending )[^<]+', lambda m: m.group(1) + short_date(latest))
    sub("stat total", r'(<b class="t" data-n=")\d+', lambda m: m.group(1) + str(nat["total"]))
    sub("stat orgs", r'(<b data-n=")\d+("\>0</b><span>of them brand-new organizations)', lambda m: m.group(1) + str(nat["orgs"]) + m.group(2))
    sub("picker sentence", r"(Real counts from the week ending )[A-Z][a-z]+ \d{1,2}, \d{4}", lambda m: m.group(1) + long_date(latest))
    sub("funnel kept", r'(<div class="k">)[\d,]+(<small>last week</small>)', lambda m: m.group(1) + fmt(nat["total"]) + m.group(2))
    ny = week.get("NY", [0] * 6)
    sub("funnel NY", r'(<span id="fnState">)[\d,]+', lambda m: m.group(1) + fmt(sum(ny)))
    sub("funnel NY cat", r'(<span id="fnCat">)[\d,]+', lambda m: m.group(1) + fmt(max(ny)))
    sub("sample caption", r"(week ending )[A-Z][a-z]{2} \d{1,2}( · )[\d,]+( rows · organizations first)", lambda m: m.group(1) + short_date(latest) + m.group(2) + fmt(sum(ny)) + m.group(3))
    for i, c in enumerate(CATS):
        sub(f"cat {c}", r'(<b>' + re.escape(html.escape(N.NICE[c])) + r'</b><span>[^<]*</span><i class="ct">)[\d,]+( last week)', lambda m, i=i: m.group(1) + fmt(nat["cats"][i]) + m.group(2))
    sub("updated", r'(<span class="upd" id="updated">Data updated for the week ending )[^.<]+', lambda m: m.group(1) + long_date(latest))
    s = re.sub(r'(<span class="wkiso">)\d{4}-\d{2}-\d{2}', lambda m: m.group(1) + latest, s)
    sub("mail card count", r'(- NY, Behavioral Health: <b>)[\d,]+', lambda m: m.group(1) + fmt(ny[0]))
    if data.get("sample"):
        sub("sample link", r'(<a href="sample/panelready-sample\.csv" id="sampleDl">)[^<]*(</a> \()[^)]*\)', lambda m: f'{m.group(1)}Download a full sample spreadsheet{m.group(2)}{STATES[data["sample"]["state"]]}, {fmt(data["sample"]["rows"])} rows, every column, nothing masked)')
    if '<a href="#state">Your state</a>' in s:                # one-time: the nav points at the state pages
        sub("nav", r'<a href="#state">Your state</a>', '<a href="states/">By state</a>')
    if 'href="account/"' not in s:                        # one-time: an Account link in the header (kept on phones)
        sub("nav account", r'<a class="mini" href="#free">', '<a class="signin" href="account/">Account</a><a class="mini" href="#free">')
        sub("nav account css", r"\.nav nav a:not\(\.mini\)\{display:none\}", ".nav nav a:not(.mini):not(.signin){display:none}")
        sub("nav account phone css", r"(\n\s*/\* hero \*/)", lambda m: "\n  @media (max-width:860px){.nav nav a.signin{margin-left:0;margin-right:14px}.nav nav a{white-space:nowrap}}"
            "\n  @media (max-width:420px){.logo{font-size:19px;gap:8px}.logo svg{width:26px;height:26px}.nav nav a.signin{margin-right:10px;font-size:13.5px}"
            ".nav .mini{padding:8px 11px;font-size:13px}}"
            "\n  @media (max-width:360px){.logo{font-size:16px;gap:6px}.logo svg{width:22px;height:22px}.nav nav a.signin{margin-right:8px;font-size:12px}"
            ".nav .mini{padding:6px 8px;font-size:12px}}" + m.group(1))
    for old, new in LANDING_WORDING:                     # one-time wording fixes (Oct 20: delivery timing, trial vs paid,
        if old in s:                                      # account page, cancelling); each is skipped once it's done
            s = s.replace(old, new, 1)
            done.append("wording")
    if "fromQuery" not in s:                              # one-time: let ?state=TX preselect the picker
        sub("preselect", r"sel\.value = 'NY'; sel\.onchange = function\(\)\{ setState\(sel\.value\); \}; setState\('NY'\);",
            "var fromQuery = (location.search.match(/[?&]state=([A-Za-z]{2})/) || [])[1]; fromQuery = fromQuery && NAMES[fromQuery.toUpperCase()] ? fromQuery.toUpperCase() : 'NY';\n"
            "  sel.value = fromQuery; sel.onchange = function(){ setState(sel.value); }; setState(fromQuery);")
    p.write_text(s, encoding="utf-8")
    return miss


# ------------------------------------------------------------------ main

def build(data: dict) -> list[str]:
    if not data["latest"]:
        raise RuntimeError("no weekly data yet (run pull_npi.py first, or use --fetch)")
    latest = data["latest"]
    week = data["counts"][latest]
    paths = []
    out = HERE / "states"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(hub_page(data), encoding="utf-8")
    paths.append("states/")
    for st in STATES:
        if st not in week:
            continue
        d = out / SLUG[st]
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(state_page(data, st), encoding="utf-8")
        paths.append(f"states/{SLUG[st]}/")
        for c in CATS:
            cd = d / CAT_SLUG[c]
            if week[st][CATS.index(c)] >= CAT_PAGE_MIN:
                cd.mkdir(exist_ok=True)
                (cd / "index.html").write_text(cat_page(data, st, c), encoding="utf-8")
                paths.append(f"states/{SLUG[st]}/{CAT_SLUG[c]}/")
            elif cd.exists():
                shutil.rmtree(cd)                        # a category page that no longer has enough rows goes away (sitemap drops it)
    info = info_pages(data)
    write_account()                                   # not in the sitemap: private, opened from the link in each email
    write_search()
    write_sample(data)
    urls = [f"  <url><loc>{SITE}/</loc><lastmod>{latest}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>"]
    urls += [f"  <url><loc>{SITE}/search/</loc><lastmod>{latest}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>"]
    urls += [f"  <url><loc>{SITE}/{p}</loc><lastmod>{latest}</lastmod><changefreq>weekly</changefreq><priority>{'0.8' if p.count('/') < 3 else '0.6'}</priority></url>" for p in paths]
    urls += [f"  <url><loc>{SITE}/{p}</loc><lastmod>{latest}</lastmod><changefreq>monthly</changefreq><priority>0.4</priority></url>" for p in info]
    paths = paths + info + ["search/"]
    (HERE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")
    (HERE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /account/\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    return paths


def copy_pr():
    """Keep a copy of pr/npi.py next to this script so the published folder can rebuild itself on GitHub."""
    src = ROOT / "pr" / "npi.py"
    if src.exists() and src.resolve() != (HERE / "pr" / "npi.py").resolve():
        (HERE / "pr").mkdir(exist_ok=True)
        shutil.copy2(src, HERE / "pr" / "npi.py")
        (HERE / "pr" / "__init__.py").write_text("", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download new weekly files from CMS (GitHub Actions)")
    ap.add_argument("--rebuild", action="store_true", help="rewrite the pages even if no new week arrived")
    args = ap.parse_args()
    data = load()
    say(f"{BRAND} pages: {len(data['weeks'])} week(s) on file" + (f", newest {data['latest']}" if data["latest"] else ""))
    new = fetch_weeks(data) if args.fetch else local_weeks(data)
    if new:
        save(data)
    moved = data.get("site") != SITE or data.get("build") != BUILD_VERSION   # address or layout changed: every page must be rewritten
    if not new and not moved and not args.rebuild and (HERE / "states" / "index.html").exists():
        say("  nothing new; pages left as they are")
        return
    copy_pr()
    paths = build(data)
    miss = refresh_landing(data)
    if moved or data.get("sample"):
        data["site"], data["build"] = SITE, BUILD_VERSION
        save(data)
    say(f"  wrote {len(paths)} pages for the week ending {data['latest']} -> {HERE / 'states'}" + (f" (landing page: couldn't find {', '.join(miss)})" if miss else ""))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:                               # noqa: BLE001
        print(f"\nStopped: {e}")
        sys.exit(1)
