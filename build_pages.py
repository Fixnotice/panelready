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
BUILD_VERSION = 5                                    # bump when the page layout changes, so the next run rewrites every page
COMPANY = "Avery Data Co."
SAMPLE_STATES = ["VT", "DE", "RI", "AK", "WY", "ND", "SD", "MT", "ME", "NH"]   # the free sample: the first of these with 8-25 rows this week
BRAND, MAIL = "PanelReady", "matt@panelready.co"
WEEKS = HERE / "data" / "weeks.json"
CAT_PAGE_MIN = 8                                     # a category page needs at least this many rows in the newest week
TREND_WEEKS = 12
CATS = N.CATEGORIES
CAT_TITLE = {"behavioral": "Behavioral health", "medical": "Medical practices & clinics", "dental": "Dental",
             "therapy": "Therapy & rehab", "home_senior": "Home care & senior living", "dme_transport": "DME, pharmacy & transport"}
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
@media(max-width:700px){.nav nav a:not(.mini){display:none}}
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
  <nav><a href="{root}states/">All states</a><a href="{root}#how">How it works</a><a href="{root}#pricing">Pricing</a><a class="mini" href="{root}#free">Get 2 lists free</a></nav>
</div></div>
<div class="wrap">
{body}
<footer><div class="flinks"><a href="{root}states/">New practices by state</a><a href="{root}about/">About</a><a href="{root}contact/">Contact</a><a href="{root}privacy/">Privacy</a><a href="{root}terms/">Terms</a><a href="{root}sample/panelready-sample.csv">Sample spreadsheet</a></div>
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


def offer(state_name: str, st: str, cat: str | None, root: str) -> str:
    """The subscribe block. st="" makes the generic version for the hub."""
    what = f"{CAT_TITLE[cat].lower()} practice" if cat else "practice"
    plan = "$89/month" if cat else "$199/month"
    sub = "one spreadsheet every Monday" if cat else "every category, one spreadsheet every Monday"
    which = f"the {CAT_TITLE[cat].lower()} category" if cat else "all categories"
    q = f"?state={st}&cat={cat or 'all'}" if st else ""
    where = f"in {esc(state_name)}" if st else "in your state"
    return (f'<section class="offer"><h2>Get every new {esc(what)} {where}, the week they register.</h2>'
            f'<p>This page shows a sample. Subscribers get the complete {esc(state_name) if st else "state"} list as a spreadsheet, {sub}: practice name, specialty, city, street address, phone, NPI and registration date, organizations first. '
            f'{plan} per state through PayPal (the charge shows as {COMPANY}, {BRAND}\'s parent company); cancel any time. Try the next two lists free first, no card needed.</p>'
            f'<div class="btns"><a class="cta" href="{root}{q}#free">Get two free {esc(state_name) if st else ""} lists</a><a class="cta ghost" href="{root}{q}#pricing">Subscribe · {plan}</a></div></section>')


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
<span class="kicker">New healthcare practices · {esc(name)}</span>
<h1><em>{fmt(total)}</em> new healthcare practices registered in {esc(name)} last week</h1>
<p class="lead">{p1}</p>
<div class="stats">
  <div class="stat"><b>{fmt(total)}</b><span>new practices &amp; sole proprietors, week ending {esc(short_date(latest))}</span></div>
  <div class="stat"><b>{fmt(avg4(series))}<small> /wk</small></b><span>average over the last {min(4, len(series))} week{'s' if min(4, len(series)) != 1 else ''} tracked</span></div>
  <div class="stat"><b>{fmt(orgs)}</b><span>brand-new organizations: practices, clinics, agencies</span></div>
  <div class="stat"><b>#{rank}<small> of {nstates}</small></b><span>among states and territories this week · {total / nat * 100:.1f}% of the U.S. total</span></div>
</div>
<section><p>{p2}</p><p>{p3}</p></section>

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

{offer(name, st, None, root)}

<section><h2>{esc(name)} by category</h2>
<p class="lead" style="font-size:16px">One state, one category is $89/month; every category is $199/month. {('Weekly pages for: ' + ', '.join(f'<a href="{cat_pages[c]}">{esc(CAT_TITLE[c])}</a>' for c in CATS if c in cat_pages) + '.') if cat_pages else 'Category pages appear once a category has ' + str(CAT_PAGE_MIN) + '+ new practices in a week.'}</p>
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
    title = f"New healthcare practices in {name} this week ({fmt(total)} registered) — {BRAND}"
    desc = (f"{fmt(total)} healthcare practices and sole proprietors registered for an NPI in {name} in the week ending {long_date(latest)}: "
            f"{', '.join(f'{fmt(n)} {CAT_TITLE[c].lower()}' for c, n in top[:3])}. Names, specialties, cities and a weekly trend from the federal NPPES file, updated every week.")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"New healthcare practices registered in {name}, by week",
          "description": desc, "url": f"{SITE}/states/{slug}/", "creator": {"@type": "Organization", "name": "Avery Data Co.", "url": SITE + "/"},
          "isBasedOn": "https://download.cms.gov/nppes/NPI_Files.html", "temporalCoverage": f"{data['weeks'][0]}/{latest}",
          "spatialCoverage": {"@type": "Place", "name": f"{name}, United States"}, "license": "https://www.cms.gov/about-cms/information-systems/privacy/privacy-statement",
          "variableMeasured": ["new NPI registrations by category", "new organizations", "busiest cities", "most common specialties"],
          "dateModified": latest}
    return shell(title, desc, f"states/{slug}/", body, ld)


def cat_row(data: dict, st: str, c: str, v: list, cat_pages: dict) -> str:
    label = f'<a href="{cat_pages[c]}">{esc(CAT_TITLE[c])}</a>' if c in cat_pages else esc(CAT_TITLE[c])
    return (f'<tr><td class="n">{label}</td><td style="color:var(--muted)">{esc(CAT_WHO[c])}</td><td class="r">{fmt(v[CATS.index(c)])}</td>'
            f'<td class="r">{fmt(avg4(state_series(data, st, c)))}</td></tr>')


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
<span class="kicker">{esc(ct)} · {esc(name)}</span>
<h1><em>{fmt(n)}</em> new {esc(ct.lower())} practices registered in {esc(name)} last week</h1>
<p class="lead">{p1}</p>
<div class="stats">
  <div class="stat"><b>{fmt(n)}</b><span>{esc(ct.lower())} registrations, week ending {esc(short_date(latest))}</span></div>
  <div class="stat"><b>{fmt(avg4(series))}<small> /wk</small></b><span>average over the last {min(4, len(series))} week{'s' if min(4, len(series)) != 1 else ''} tracked</span></div>
  <div class="stat"><b>{n / max(total, 1) * 100:.0f}%</b><span>of all new {esc(name)} practices this week ({fmt(total)})</span></div>
  <div class="stat"><b>{fmt(n * 52 / 12)}<small> /mo</small></b><span>new {esc(ct.lower())} practices a month at this pace</span></div>
</div>
<section><p>{p2}</p></section>
<section class="grid2">
  <div class="card"><h2>Most common specialties</h2>{bars([(s, k, None, CAT_COLOR[cat]) for s, k in specs]) if specs else '<p class="note">No specialty data this week.</p>'}</div>
  <div class="card"><h2>Week by week</h2>{trend(data, series, f"New {ct.lower()} practices in {name}")}</div>
</section>
<section><h2>A sample of this week's {esc(name)} {esc(ct.lower())} list</h2>
{sample_table(rows, f"leads_{st}_{cat}.csv · week ending {short_date(latest)} · {fmt(n)} rows · organizations first")}</section>
{offer(name, st, cat, root)}
<section><h2>Other {esc(name)} categories</h2>{links_row([(CAT_TITLE[c], f"../{CAT_SLUG[c]}/") for c in CATS if c != cat and v[CATS.index(c)] >= CAT_PAGE_MIN] + [(f"All of {name}", "../")])}</section>
<section><h2>{esc(ct)} in nearby states</h2>{links_row([(STATES[k], f"../../{SLUG[k]}/{CAT_SLUG[cat]}/") for k in NEIGHBORS.get(st, "").split() if k in STATES and data["counts"][latest].get(k, [0] * 6)[ci] >= CAT_PAGE_MIN] + [("All states", "../../")])}</section>
"""
    title = f"New {ct.lower()} practices in {name} this week ({fmt(n)} registered) — {BRAND}"
    desc = (f"{fmt(n)} {ct.lower()} practices and sole proprietors registered for an NPI in {name} in the week ending {long_date(latest)}"
            + (f", led by {specs[0][0].lower()}" if specs else "") + ". Names, specialties and cities from the federal NPPES file, updated weekly.")
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": f"New {ct.lower()} practices registered in {name}, by week", "description": desc,
          "url": f"{SITE}/states/{slug}/{CAT_SLUG[cat]}/", "creator": {"@type": "Organization", "name": "Avery Data Co.", "url": SITE + "/"},
          "isBasedOn": "https://download.cms.gov/nppes/NPI_Files.html", "temporalCoverage": f"{data['weeks'][0]}/{latest}", "dateModified": latest,
          "spatialCoverage": {"@type": "Place", "name": f"{name}, United States"}}
    return shell(title, desc, f"states/{slug}/{CAT_SLUG[cat]}/", body, ld)


def hub_page(data: dict) -> str:
    latest, week = data["latest"], data["counts"][data["latest"]]
    nat = data["national"]
    order = sorted(week, key=lambda k: -sum(week[k]))
    rows = "".join(f'<tr><td class="n"><a href="{SLUG[k]}/">{esc(STATES[k])}</a></td><td class="r">{fmt(sum(week[k]))}</td><td class="r">{fmt(avg4(state_series(data, k)))}</td>'
                   f'<td class="r">{fmt(data["orgs"].get(k, 0))}</td><td>{esc(CAT_TITLE[CATS[max(range(len(CATS)), key=lambda i: week[k][i])]])}</td></tr>' for k in order if k in STATES)
    body = f"""
<div class="crumbs"><a href="../">{BRAND}</a> › All states</div>
<span class="kicker">New healthcare practices by state</span>
<h1><em>{fmt(nat['total'])}</em> new healthcare practices registered across the U.S. last week</h1>
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
    title = f"New healthcare practices by state this week ({fmt(nat['total'])} registered) — {BRAND}"
    desc = f"{fmt(nat['total'])} healthcare practices and sole proprietors registered for an NPI in the week ending {long_date(latest)}. Weekly counts, trends, cities and specialties for every U.S. state from the federal NPPES registry."
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "New healthcare practices registered in the U.S., by state and week", "description": desc,
          "url": f"{SITE}/states/", "creator": {"@type": "Organization", "name": "Avery Data Co.", "url": SITE + "/"}, "isBasedOn": "https://download.cms.gov/nppes/NPI_Files.html",
          "temporalCoverage": f"{data['weeks'][0]}/{latest}", "dateModified": latest, "spatialCoverage": {"@type": "Place", "name": "United States"}}
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
<li><b>Cancelling:</b> from your PayPal account under Subscriptions, or reply STOP to any email. No forms.</li>
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
<li><b>When you email us:</b> the email and anything you put in it.</li>
<li><b>When you visit the site:</b> nothing we keep. The site has no analytics, no advertising pixels and sets no cookies of its own. It is hosted on GitHub Pages, whose servers keep standard access logs (IP address, pages requested) under <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>. Fonts load from Google Fonts, which sees your IP address when it serves them.</li>
</ul>
<h2>What we do with it</h2>
<p>We use your details to send you the lists you asked for, confirmations, and replies to your messages. We don't sell, rent or share them with anyone except the services that make the product work: PayPal for payments, our email provider for sending, and Cloudflare, which receives form submissions before we collect them. We don't use your data for advertising.</p>
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
<p>{BRAND} sends you a spreadsheet of healthcare practices and sole proprietors that registered for an NPI in the previous week, for the state(s) and category(ies) on your plan, on the morning CMS posts the weekly file (normally once a week; CMS occasionally skips or delays a week). The data comes from the public NPPES registry exactly as published. We sort and deliver it; we don't verify or add to it.</p>
<h2>Free lists</h2>
<p>New companies can receive two weekly lists free, no payment details required. After the second list nothing further is sent unless you subscribe. We may decline or limit free lists at our discretion, for example to one per company.</p>
<h2>Plans and payment</h2>
<ul>
<li><b>One state, one category:</b> $89 per month. <b>One state, every category:</b> $199 per month. Additional states are additional plans or a bundle by email.</li>
<li>Payment is by PayPal subscription, billed monthly in advance. Charges appear as <b>{COMPANY}</b>. Prices may change with at least 30 days' notice by email; your current month is never affected.</li>
<li>You can cancel at any time from your PayPal account or by replying STOP to any email. Lists continue to the end of the month already paid for, and no further charges are made. Partial months are not refunded, except that if your first paid list never arrives we'll refund the month in full.</li>
</ul>
<h2>What you may do with the lists</h2>
<p>Use them inside your own business to find and contact practices. You may not resell, republish or redistribute the lists, or use them to build a competing product. The lists are not exclusive: other subscribers to the same state and category receive the same data. You are responsible for your own outreach and for complying with the laws that apply to it, including telephone and email marketing rules.</p>
<h2>No warranty</h2>
<p>The data is public information provided as-is. We don't warrant that it is complete, current or accurate, that a given practice is still operating or wants to be contacted, or that using it will produce any result. Our total liability for any claim connected with the service is limited to the amount you paid us in the three months before the claim arose. We're not affiliated with CMS or any payer.</p>
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
    write_sample(data)
    urls = [f"  <url><loc>{SITE}/</loc><lastmod>{latest}</lastmod><changefreq>weekly</changefreq><priority>1.0</priority></url>"]
    urls += [f"  <url><loc>{SITE}/{p}</loc><lastmod>{latest}</lastmod><changefreq>weekly</changefreq><priority>{'0.8' if p.count('/') < 3 else '0.6'}</priority></url>" for p in paths]
    urls += [f"  <url><loc>{SITE}/{p}</loc><lastmod>{latest}</lastmod><changefreq>monthly</changefreq><priority>0.4</priority></url>" for p in info]
    paths = paths + info
    (HERE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")
    (HERE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
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
