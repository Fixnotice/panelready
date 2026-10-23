"""PanelReady list upgrades: what turns a raw registry export into a list a credentialing firm can work today.

    score / reasons   0-100 "how likely this practice needs credentialing and billing help soon", with the why
    TOP 25            the best 25 of each list, marked, and every list sorted best-first
    opener            a ready-to-say first line for each lead, plus the person to ask for
    website / email   for organizations: found on Google (inside the free monthly allowance) and on their own site
    oig_check         the federal OIG exclusion list (free, monthly): flags anyone barred from Medicare/Medicaid billing

Pure functions here; deliver.py writes the upgraded files, pr/boost.enrich() does the network lookups.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

EXTRA = ["score", "priority", "why", "contact_name", "opener", "website", "email", "google_rating", "oig_check"]
TOP_N = 25

# how much credentialing / payer-enrollment work a new practice in each category usually needs
CAT_POINTS = {"home_senior": 20, "dme_transport": 18, "medical": 16, "behavioral": 15, "therapy": 10, "dental": 6}
# specialties that almost always need multi-payer enrollment (Medicare certification, Medicaid, commercial)
HEAVY_TAX = ("363LP0808X", "2084P0800X", "103K", "251E", "251G", "251J", "3140", "311Z", "332B", "3416",
             "343", "261Q", "193", "207Q", "207R", "208D", "363L", "364S", "1041C", "101Y", "106H", "225100000X",
             "235Z", "261QR0400X", "152W")
GROUP_WORDS = re.compile(r"\b(GROUP|ASSOCIATES|CENTERS?|CENTRES?|CLINICS?|PARTNERS|HEALTHCARE|HEALTH CARE|MEDICAL CARE|"
                         r"SERVICES|AGENCY|HOME HEALTH|HOSPICE|INSTITUTE|NETWORK|SPECIALISTS|PHYSICIANS|THERAPIES|"
                         r"AMBULANCE)\b", re.I)
LIGHT_TAX = ("3336", "1223", "1224", "1225", "1226", "126800000X", "1835", "183500000X")   # pharmacies, hygienists/assistants: rarely buy credentialing
CODE_LIKE = re.compile(r"^\d{3}[0-9A-Z]{6}X$", re.I)
CAT_WORD = {"behavioral": "behavioral health", "medical": "medical", "dental": "dental", "therapy": "therapy",
            "home_senior": "home care", "dme_transport": "medical supply"}
SOLO_SUFFIX = re.compile(r"(^DR\b|\b(LCSW|LMSW|LMHC|LPC|LMFT|LCPC|PSYD|PHD|MD|DO|DDS|DMD|DPM|NP|PMHNP|FNP|PA|DPT|OTR|SLP|DC|OD|RD)\b)"
                         r"(?![A-Z])", re.I)
WEAK_CRED = re.compile(r"^(LMSW|RDA|CNA|MA|BA|BS|MS|MSW|STUDENT|INTERN|TRAINEE)\b", re.I)
DOCTOR_CREDS = {"MD", "DO", "DDS", "DMD", "DPM", "PHD", "PSYD", "DC", "OD", "DPT", "AUD", "DNP"}


# ---------------------------------------------------------------- score + why

def specialty(lead: dict) -> str:
    """The registry's specialty in words; a bare taxonomy code becomes the category ("medical supply")."""
    sp = (lead.get("specialty") or "").strip()
    if not sp or CODE_LIKE.match(sp):
        return CAT_WORD.get(lead.get("category", ""), "healthcare")
    return ACRONYMS.sub(lambda m: m.group(0).upper(), sp.lower())    # "dme & medical supplies" -> "DME & medical supplies"


ACRONYMS = re.compile(r"\b(dme|fqhc|aba|icf|iid|pace|cmhc|ems|hiv|aids|adhd|ent|ob|gyn|mri|ct|esrd|ltc|snf|"
                      r"rn|lpn|np|pa|ot|pt|slp)\b")


def score(lead: dict, week_end: Optional[dt.date] = None) -> tuple[int, str]:
    """0-100 and a short reason. Organizations beat sole proprietors (bigger contracts, more payers to enroll);
    categories and specialties that need Medicare/Medicaid enrollment beat ones that mostly don't; a name that
    reads like a multi-provider group beats one person's PLLC."""
    org = lead.get("entity") == "practice/organization"
    name = lead.get("name") or ""
    tax = (lead.get("taxonomy") or "").upper()
    cat = lead.get("category") or ""
    pts, why = (50 if org else 25), ["new organization" if org else "sole proprietor"]
    cp = CAT_POINTS.get(cat, 8)
    pts += cp
    if any(tax.startswith(t) for t in LIGHT_TAX):
        pts -= 12
        why.append(f"{specialty(lead)}: rarely outsources credentialing")
    elif any(tax.startswith(t) for t in HEAVY_TAX):
        pts += 8
        why.append(f"{specialty(lead)}: heavy payer enrollment")
    elif cp >= 15:
        why.append(specialty(lead))
    if org and GROUP_WORDS.search(name):
        pts += 8
        why.append("name suggests a multi-provider practice")
    elif org and SOLO_SUFFIX.search(name):
        pts -= 4
        why.append("looks like a one-person PLLC")
    if not org and WEAK_CRED.search(lead.get("credential") or ""):
        pts -= 10
        why.append(f"{lead.get('credential')} credential (often not billing independently yet)")
    size = int(lead.get("providers_at_practice") or 0)
    if org and 3 <= size < 200:
        pts += 8 if size >= 10 else 6
        why.append(f"{size} providers share its phone")
    elif org and size >= 200:
        why.append("phone shared by a large organization")
    if lead.get("phone"):
        pts += 4
    else:
        why.append("no phone listed")
    if org and lead.get("official_phone") and lead.get("official_phone") != lead.get("phone"):
        pts += 2
        why.append("owner's own phone listed")
    if week_end and lead.get("registered"):
        try:
            if (week_end - dt.date.fromisoformat(lead["registered"])).days <= 3:
                pts += 4
                why.append("registered in the last few days")
        except ValueError:
            pass
    return max(0, min(100, pts)), "; ".join(why)


def label(s: int) -> str:
    return "Hot" if s >= 80 else "Warm" if s >= 60 else "Cool"


# ---------------------------------------------------------------- opener + contact

def contact_name(lead: dict) -> str:
    return (lead.get("authorized_official") if lead.get("entity") == "practice/organization" else lead.get("name")) or ""


def _greeting(lead: dict) -> str:
    who = contact_name(lead).strip()
    if not who:
        return "there"
    parts = who.split()
    cred = lead.get("credential") or ""
    creds = set(re.split(r"[^A-Z]+", cred.upper().replace(".", "")))      # "M.D." -> MD, "Ph.D., LCSW" -> PHD, LCSW
    if lead.get("entity") != "practice/organization" and creds & DOCTOR_CREDS:
        return f"Dr. {parts[-1]}"
    return parts[0]


def _when(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(iso)
        return f"{d.strftime('%b')} {d.day}"
    except (ValueError, TypeError):
        return "recently"


def _month(iso: str) -> str:
    try:
        return dt.date.fromisoformat(iso).strftime("%B %Y")
    except (ValueError, TypeError):
        return "earlier this year"


UPPER_WORDS = {"LLC", "PLLC", "PC", "LLP", "LP", "PA", "PLC", "DDS", "DMD", "MD", "NP", "PT", "OT", "DPM", "PSYD", "PHD", "LCSW",
               "LMFT", "LMHC", "LPC", "LMSW", "ABA", "DME", "USA", "II", "III", "IV", "CRNA", "FNP", "PMHNP", "APRN", "RN",
               "LLC.", "PC.", "PA.", "INC.", "LHCSA", "CHHA", "FQHC", "NYC", "LCSW-R"}


def tidy_name(name: str) -> str:
    """'Smith'S Family Practice Llc' -> "Smith's Family Practice LLC" (the registry is upper case; title() overdoes it)."""
    out = []
    for w in (name or "").split():
        core = w.strip(",")
        if core.upper() in UPPER_WORDS:
            w = w.replace(core, core.upper() if core.upper() != "INC." else "Inc.")
        out.append(re.sub(r"'S\b", "'s", w))
    out = [w.lower() if 0 < i < len(out) - 1 and w in SMALL_WORDS else w for i, w in enumerate(out)]
    return " ".join(out)


SMALL_WORDS = {"And", "Of", "For", "In", "The", "At", "On", "To"}     # "Services For Children" -> "Services for Children"


def tidy_place(s: str) -> str:
    """The registry's title-cased addresses: '12 72Nd St' -> '12 72nd St', 'Mcclellan' -> 'McClellan', 'Po Box' -> 'PO Box'."""
    s = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s or "")
    s = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)
    s = re.sub(r"\b(Ne|Nw|Se|Sw)\b", lambda m: m.group(1).upper(), s)
    return re.sub(r"\bPo Box\b", "PO Box", s)


def opener(lead: dict) -> str:
    """A first line the buyer can say or paste. Facts only (name, city, date, specialty); no claims about them."""
    city = tidy_place((lead.get("city") or "").strip()) or "your area"
    spec = specialty(lead)
    hi = _greeting(lead)
    when = _when(lead.get("registered", ""))
    if lead.get("change_type") == "reactivated":
        whose = f"{lead.get('name') or 'your practice'}'s" if lead.get("entity") == "practice/organization" else "your"
        return (f"Hi {hi}, I saw {whose} NPI was reactivated on {_when(lead.get('changed_on', ''))} (federal NPI registry). "
                f"Getting back in network with Medicare and the plans takes a while: would help with re-credentialing "
                f"be useful?")
    if lead.get("change_type") == "new specialty":
        added = (lead.get("change_detail") or "").replace("added ", "", 1) or "a new specialty"
        who = lead.get("name") or "your practice" if lead.get("entity") == "practice/organization" else "you"
        return (f"Hi {hi}, I saw {who} added {added} to the NPI registration ({_when(lead.get('changed_on', ''))}). "
                f"A new service line means updating every payer enrollment and contract: would help with that be useful?")
    if lead.get("moved_from"):                      # the practice-moved list
        where = f"{tidy_place(lead.get('address') or '')}, {city}".strip(", ")
        if lead.get("entity") == "practice/organization":
            return (f"Hi {hi}, I saw {lead.get('name') or 'your practice'} moved to {where} (it's in the federal NPI "
                    f"registry as of {_when(lead.get('moved_on', ''))}). Medicare and every commercial plan need the new "
                    f"location on file to keep claims paying: would help with the address updates be useful?")
        return (f"Hi {hi}, I saw your practice moved to {where} (federal NPI registry, {_when(lead.get('moved_on', ''))}). "
                f"Medicare and each insurance plan need the new location on file: would help with the updates be useful?")
    if lead.get("medicare_pending") and lead.get("medicare_status"):
        return (f"Hi {hi}, I noticed {'your' if lead.get('entity') != 'practice/organization' else lead.get('name', 'your') + chr(39) + 's'} "
                f"Medicare application is still showing as pending on CMS's list. If it's been held up, or the commercial "
                f"plans still need doing, we can take it off your plate: who's handling it right now?")
    if lead.get("medicare_status"):                 # the stuck-in-credentialing list: registered months ago
        month = _month(lead.get("registered", ""))
        if lead.get("entity") == "practice/organization":
            return (f"Hi {hi}, I noticed {lead.get('name') or 'your practice'} in {city} registered its NPI in {month} but "
                    f"isn't on Medicare's public enrollment list yet. If credentialing has stalled or hasn't started, "
                    f"we can take it off your plate: is that being handled in-house right now?")
        return (f"Hi {hi}, I noticed you registered your {spec + ' ' if spec else ''}practice in {city} in {month} but "
                f"aren't on Medicare's public enrollment list yet. If insurance credentialing has stalled or is still on "
                f"the to-do list, would some help be useful?")
    if lead.get("entity") == "practice/organization":
        return (f"Hi {hi}, congratulations on registering {lead.get('name') or 'the new practice'} in {city} ({when}). "
                f"New {spec + ' ' if spec else ''}practices usually start payer credentialing in the first 60-90 days: "
                f"are you handling that in-house, or would help be useful?")
    return (f"Hi {hi}, congratulations on starting your own {spec + ' ' if spec else ''}practice in {city} ({when}). "
            f"Have you started getting credentialed with insurance plans yet, or is that still on the to-do list?")


KIT = """PanelReady outreach kit: how to work this week's list
=====================================================

1. Start with the rows marked TOP 25 (the list is sorted best-first). "score" is 0-100: how likely the practice
   needs credentialing and billing help soon; "why" says what drove it.
2. Ask for the person in "contact_name" (the practice's owner / authorized official, or the provider for a solo
   practice). "contact_phone" is their own number from the federal registry when it differs from the practice line:
   try it first. Then the practice phone, then email if there's an address in the "email" column.
3. Use the "opener" column as your first line. It only states facts from the public registration (name, city,
   date, specialty), so it never sounds like a guess.

Call script (60 seconds)
------------------------
  "Hi, is this {contact_name}? This is <you> from <your company>. {opener}
   We get new practices like yours credentialed with <Medicare / Medicaid / the big commercial plans> and billing
   within <N> weeks, so you're not waiting months on your first payments. Would a 10-minute call this week to see
   where you stand be worth it?"
  If they already have someone: "Good to hear. If anything stalls, mind if I check back in 60 days?"

Email template
--------------
  Subject: Credentialing for {practice name}
  {opener}
  We help new {specialty} practices in {state} get enrolled with payers and set up for billing, usually in <N> weeks.
  Want me to send a quick checklist of what you'll need, or set up a 10-minute call?
  <signature>

Notes
-----
- "oig_check" flags anyone on the federal OIG exclusion list (barred from Medicare/Medicaid billing). Don't take them
  on as clients without checking with your compliance contact.
- Websites and emails are found for organizations on Google and on the practice's own site; blank means none was found
  (yet). Phones and addresses come from the federal registry as filed.
- "practice_software": the practice-management, EHR, patient-portal or booking system its website links to
  (SimplePractice, athenahealth, Tebra, eClinicalWorks...). Lead with the systems you know. "Insurance platform"
  (Headway, Alma, Rula, Grow) means the practice is credentialed through that platform today: pitch going direct.
  "social" has its Facebook / LinkedIn / Instagram pages.
- "providers_at_practice": how many individual providers list the practice's phone number in the registry. Bigger
  groups mean more providers to enroll with every payer. 200+ usually means a hospital or health-system switchboard.
- "medicare_pending": the provider's first Medicare application is on CMS's public pending list (it's been filed,
  not yet approved). They're mid-credentialing: a good moment to offer help with the commercial plans too.
- Other attachments, when they apply to your states:
    moved_*.csv   practices that moved this week (Medicare and every plan need the new address on file)
    reval_*.csv   monthly: practices due (or overdue) for Medicare revalidation, soonest first
    stuck_*.csv   monthly: practices months in and still not on Medicare's enrollment list
  Each has its own opener. PanelReady_CRM_import.csv has every row in a format HubSpot and Salesforce import directly.
- The guarantee: sign at least one new client from your PanelReady lists in your first 90 days as a subscriber, or reply
  and tell us, and your next 3 months are free.
"""


# ---------------------------------------------------------------- OIG exclusion list

LEIE_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", "", re.sub(r"\s+", " ", (s or "").upper())).strip()


def load_leie(path: Path) -> dict:
    """{'npi': {npi: note}, 'person': {(LAST, FIRST, ST): note}, 'business': {(NAME, ST): note}} for exclusions
    still in force (not reinstated)."""
    out = {"npi": {}, "person": {}, "business": {}}
    if not path.exists():
        return out
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        rd = csv.DictReader(f)
        cols = {c.upper().strip(): c for c in (rd.fieldnames or [])}

        def g(r, k):
            return (r.get(cols.get(k, ""), "") or "").strip()
        for r in rd:
            rein = g(r, "REINDATE")
            if rein and rein.strip("0"):
                continue
            ed = g(r, "EXCLDATE")
            note = f"EXCLUDED: on the OIG exclusion list since {ed[4:6]}/{ed[:4]}" if len(ed) == 8 else "EXCLUDED: on the OIG exclusion list"
            npi = g(r, "NPI").strip("0") and g(r, "NPI")
            st = g(r, "STATE").upper()
            if npi:
                out["npi"][npi] = note
            if g(r, "BUSNAME"):
                out["business"][(_norm(g(r, "BUSNAME")), st)] = note
            if g(r, "LASTNAME"):
                out["person"][(_norm(g(r, "LASTNAME")), _norm(g(r, "FIRSTNAME")), st)] = note
    return out


def oig_note(lead: dict, leie: dict, as_of: str) -> str:
    if lead.get("npi") and lead["npi"] in leie["npi"]:
        return leie["npi"][lead["npi"]]
    st = (lead.get("state") or "").upper()
    if lead.get("entity") == "practice/organization":
        hit = leie["business"].get((_norm(lead.get("name", "")), st))
    else:
        parts = _norm(lead.get("name", "")).split()
        hit = leie["person"].get((parts[-1], parts[0], st)) if len(parts) >= 2 else None
        hit = hit and hit + " (name match: confirm)"
    return hit or (f"clear (OIG list {as_of})" if as_of else "")


def refresh_leie(path: Path, fetch: Callable[[str], bytes], max_age_days: int = 28) -> str:
    """Download the OIG list if ours is missing or a month old. Returns 'YYYY-MM' of the copy on disk, or ''."""
    meta = path.with_suffix(".json")
    info = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    fresh = path.exists() and info.get("fetched") and \
        (dt.date.today() - dt.date.fromisoformat(info["fetched"])).days < max_age_days
    if not fresh:
        try:
            data = fetch(LEIE_URL)
            if b"," not in data[:500]:
                raise ValueError("not a CSV")
            path.write_bytes(data)
            info = {"fetched": dt.date.today().isoformat()}
            meta.write_text(json.dumps(info), encoding="utf-8")
        except Exception:                                    # noqa: BLE001
            pass                                            # keep last month's copy; the column says how old it is
    return info.get("fetched", "")[:7] if path.exists() else ""


# ---------------------------------------------------------------- website + email (organizations)

STOP_TOKENS = {"LLC", "PLLC", "INC", "PC", "PA", "CORP", "CORPORATION", "CO", "LTD", "LP", "LLP", "THE", "OF", "AND", "&",
               "DBA", "A", "P", "L", "C", "COMPANY", "GROUP", "SERVICES", "SERVICE"}


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if t not in STOP_TOKENS and len(t) > 1}


def same_business(lead: dict, g_name: str, g_address: str) -> bool:
    """Google's top hit is only trusted when it's plainly the same practice: most of the registered name's words
    appear in Google's name and Google's address is in the same city or ZIP, or nearly all of them appear (two or
    more distinctive words) and it's in the same state (NPPES says 'New York', Google says 'Brooklyn')."""
    a, b = _tokens(lead.get("name", "")), _tokens(g_name)
    if not a or not b:
        return False
    overlap = len(a & b) / len(a)
    place = _norm(g_address)
    city = _norm(lead.get("city", ""))
    here = (city and city in place) or (lead.get("zip") and lead["zip"] in (g_address or ""))
    st = (lead.get("state") or "").upper()
    same_state = bool(st) and re.search(r",\s*" + st + r"(\s+\d{5}(-\d{4})?)?\s*(,|$)", g_address or "") is not None
    return (overlap >= 0.6 and bool(here)) or (overlap >= 0.85 and len(a) >= 2 and same_state) or \
        (same_state and _acronym_match(lead.get("name", ""), g_name))


ACRONYM_SKIP = {"FOR", "AND", "OF", "THE", "INC", "LLC", "PLLC", "PC", "PA", "CORP", "CORPORATION", "LTD", "CO", "DBA", "&"}


def _acronym_match(name: str, g_name: str) -> bool:
    """'Center For Alternative Sentencing And Employment Services, Inc.' is Google's 'CASES'."""
    g = _norm(re.sub(r"\(.*?\)", "", g_name or "")).split()
    if len(g) != 1 or len(g[0]) < 4:
        return False
    letters = "".join(w[0] for w in _norm(name).split() if w not in ACRONYM_SKIP)
    return letters == g[0]


CACHE_V = 2          # cache entries keep Google's own answer, so a smarter matcher never needs a second lookup


def enrich(leads: list[dict], cache: dict, lookup: Callable, scan: Callable, allowance: int, today: str,
           deadline: float, stats: Optional[dict] = None, may_look: Optional[Callable] = None) -> int:
    """Fill website/email/google_rating for organizations, best-scored first, from the cache or with at most
    `allowance` new Google lookups. Every answer (found or not) is cached by NPI so nobody is looked up twice;
    a lookup that errors isn't cached (tried again next run). `stats` gets found / not_on_google / different /
    errors counts, a few mismatch examples and the first error. may_look(lead) -> False means cache only for that
    lead, no new lookup (trial lists look up just their TOP 25). Returns the number of Google lookups used."""
    st = stats if stats is not None else {}
    for k in ("found", "not_on_google", "different", "errors", "rematched"):
        st.setdefault(k, 0)
    st.setdefault("examples", [])
    st.setdefault("error", "")
    used = 0
    orgs = [l for l in leads if l.get("entity") == "practice/organization" and l.get("npi")]
    orgs.sort(key=lambda l: -int(l.get("score") or 0))
    for l in orgs:
        hit = cache.get(l["npi"])
        if hit is not None and hit.get("v") != CACHE_V and not hit.get("website"):
            hit = None                                   # from before Google's answer was kept: look again once
        if hit is None:
            if used >= allowance or time.monotonic() > deadline or st["errors"] >= 3 or (may_look and not may_look(l)):
                continue
            used += 1
            q = f"{l.get('name')}, {l.get('city')}, {l.get('state')}"
            try:
                biz = lookup(q)
            except Exception as e:                       # noqa: BLE001
                st["errors"] += 1
                st["error"] = st["error"] or str(e)[:200]
                continue
            hit = {"v": CACHE_V, "checked": today, "website": "", "email": "", "rating": "",
                   "g_name": biz.name if biz else "", "g_address": biz.address if biz else "",
                   "g_website": (biz.website or "") if biz else "",
                   "g_rating": f"{biz.rating} ({biz.reviews} reviews)" if biz and biz.rating else ""}
            if biz is None:
                st["not_on_google"] += 1
            elif same_business(l, biz.name, biz.address):
                st["found"] += 1
                hit["website"], hit["rating"] = hit["g_website"], hit["g_rating"]
                if biz.website and time.monotonic() < deadline - 20:
                    try:
                        res = scan(biz.website)
                    except Exception:                    # noqa: BLE001
                        res = ([], [])
                    emails, sig = res[0], (res[2] if len(res) > 2 else {})
                    hit["email"] = emails[0] if emails else ""
                    hit["software"] = ", ".join(sig.get("software", []))
                    hit["social"] = " ".join(sig.get("social", [])[:3])
            else:
                st["different"] += 1
                if len(st["examples"]) < 5:
                    st["examples"].append(f"{l.get('name')} ({l.get('city')}) -> Google: {biz.name} ({biz.address})")
            cache[l["npi"]] = hit
        elif not hit.get("website") and hit.get("g_name") and same_business(l, hit["g_name"], hit.get("g_address", "")):
            hit["website"], hit["rating"] = hit.get("g_website", ""), hit.get("g_rating", "")
            st["rematched"] += 1
        l["website"], l["email"], l["google_rating"] = hit.get("website", ""), hit.get("email", ""), hit.get("rating", "")
        l["practice_software"], l["social"] = hit.get("software", ""), hit.get("social", "")
        if l["practice_software"] and "uses " not in (l.get("why") or ""):
            l["why"] = f"{l.get('why', '')}; uses {l['practice_software']}".strip("; ")
    return used


# ---------------------------------------------------------------- one file in, one upgraded file out

def contact_fields(r: dict):
    """contact_name / contact_title / contact_phone: the owner's own line when the registry lists one."""
    org = r.get("entity") == "practice/organization"
    r["contact_name"] = contact_name(r)
    r["contact_title"] = (r.get("official_title") or "") if org else ""
    own = r.get("official_phone") or ""
    r["contact_phone"] = own if org and own and own != r.get("phone") else ""


def upgrade(rows: list[dict], week_end: Optional[dt.date], leie: dict, leie_as_of: str,
            extras: Optional[dict] = None) -> list[dict]:
    """Score, reason, opener, contact, OIG check; sorted best-first with the top 25 marked. extras: 'phone_count'
    (phone -> providers sharing it, from the registry snapshot) and 'pending' ({npi: date} on CMS's pending list)."""
    extras = extras or {}
    count, pending, optout = extras.get("phone_count"), extras.get("pending") or {}, extras.get("optout") or {}
    out = []
    for r in rows:
        r = dict(r)
        r["name"] = tidy_name(r.get("name", ""))
        if r.get("entity") == "practice/organization":
            r["authorized_official"] = tidy_name(r.get("authorized_official", ""))
            if count and not r.get("providers_at_practice"):
                n = count(r.get("phone"))
                r["providers_at_practice"] = str(n) if n else ""
        if pending.get(r.get("npi", "")):
            r["medicare_pending"] = f"Medicare application pending (on CMS's pending list since {pending[r['npi']]})"
        if optout.get(r.get("npi", "")):
            r["medicare_optout"] = f"opted out of Medicare until {optout[r['npi']]}"
        s, why = score(r, week_end)
        r["score"], r["why"] = s, f"{label(s)}: {why}"
        contact_fields(r)
        r["opener"] = opener(r)
        r["oig_check"] = oig_note(r, leie, leie_as_of)
        for k in ("website", "email", "google_rating", "providers_at_practice", "medicare_pending", "practice_software",
                  "social", "medicare_optout"):
            r.setdefault(k, "")
        out.append(r)
    out.sort(key=lambda r: (-r["score"], r.get("entity") != "practice/organization", r.get("name", "")))
    for i, r in enumerate(out):
        r["priority"] = "TOP 25" if i < TOP_N else ""
    return out


def write(path: Path, rows: list[dict], base_header: list[str]):
    """Upgraded columns first (what a buyer reads), then the registry fields."""
    first = ["priority", "score", "name", "contact_name", "contact_title", "contact_phone", "phone", "email", "website",
             "opener", "why", "specialty", "city", "state", "registered"]
    last = ["practice_software", "social", "providers_at_practice", "medicare_pending", "medicare_optout", "google_rating",
            "oig_check"]
    header = first + [h for h in base_header if h not in first + last + ["official_title", "official_phone"]] + last
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig: Excel opens it with the right characters
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def http_get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (PanelReady; public data)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()
