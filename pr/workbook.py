"""PanelReady's branded Excel workbook: what every list goes out as (weekly, first paid, one-time week, sample).

One .xlsx per delivery, built from the upgraded CSV files (pr/boost.py writes them):

  Overview        logo, the territory and week, the counts, the 10 hottest leads, how to work the list
  Top 25          the best leads with the owner's direct line and a ready-to-say opener (wrapped, easy to read)
  New practices   every new practice, sorted best-first, friendly column names, clickable NPI / website / email
  Moved, Changes, Last 90 days, Revalidation due, Stuck in credentialing   when the delivery has them
  How to use      call script, email template, and what every column means

Written with XlsxWriter (pure Python, no Excel needed). The logo is an image in the top-left of every tab; under
it, in the same cell, sits the word "PanelReady" in brand colors, so a viewer that leaves images out still shows
the name. Phones, ZIP codes and NPIs are stored as text (leading zeros kept) with Excel's "number stored as text"
warning switched off; dates are real dates.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import re
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets" if (HERE / "assets" / "logo_lockup.png").exists() else HERE   # (the website keeps them in pr/)
LOGO = ASSETS / "logo_lockup.png"            # mark + wordmark, white background, drawn 4x (shown at about 1/4.4)
LOGO_PX = (618, 136)
PRINT_LOGO = ASSETS / "logo_print.png"     # same image marked 400 dpi: prints about 1.5 inches wide
SITE = "https://panelready.co"
BRAND = "PanelReady"

# the website's palette (site/build_pages.py)
INK, TEAL, BODY, MUTED, DIM = "#0F2340", "#0E7C7B", "#334155", "#5B6B82", "#8A97A9"
LINE, BG, CARD2, TEAL_SOFT = "#E3E8EF", "#F6F8FB", "#F3F6FA", "#E3F3F2"
RED, RED_SOFT, AMBER_SOFT = "#B42318", "#FDECEA", "#FFF4DB"
FONT, SERIF = "Calibri", "Georgia"

NICE = {"behavioral": "Behavioral Health", "medical": "Medical Practices & Clinics", "dental": "Dental",
        "therapy": "Therapy & Rehab", "home_senior": "Home Care & Senior Living",
        "dme_transport": "DME, Pharmacy & Transport", "all": "All categories"}
STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
          "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
          "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
          "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
          "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
          "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
          "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
          "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
          "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
          "WI": "Wisconsin", "WY": "Wyoming"}

# ------------------------------------------------------------------ tidying the registry's text

UP = {"llc", "pllc", "pc", "pa", "lp", "llp", "md", "dds", "dmd", "np", "pmhnp", "lcsw", "lpc", "lmft", "bcba", "dpt",
      "fnp", "dba", "ii", "iii", "iv", "usa", "aba", "rn", "lmhc", "psyd", "phd", "slp", "ot", "pt", "fqhc", "dpm",
      "od", "aprn", "ceo", "cfo", "coo", "cmo", "cno", "cto", "vp", "svp", "evp", "hr", "lmsw", "lcpc", "lpcc",
      "lcsw-r", "mhc", "mhc-lp", "pmhnp-bc", "fnp-bc", "agpcnp", "crna", "otr", "ccc-slp", "rd", "do"}


def tidy_name(s: str) -> str:
    """'Roth Neuro & Mobility Pllc' -> 'Roth Neuro & Mobility PLLC', 'Mcdonald' -> 'McDonald'."""
    if not s:
        return ""
    s = re.sub(r"[A-Za-z][A-Za-z\-]*", lambda m: m.group(0).upper() if m.group(0).lower() in UP else m.group(0), s)
    s = re.sub(r"\bPHD\b", "PhD", s)
    s = re.sub(r"\bPSYD\b", "PsyD", s)
    s = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)
    s = re.sub(r"'S\b", "'s", s)
    s = re.sub(r"(?<=\w )(In|And|Of|For|The|At|On)\b(?= \w)", lambda m: m.group(1).lower(), s)
    return s.strip()


def tidy_city(s: str) -> str:
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s or "").strip()


def tidy_addr(s: str) -> str:
    """'10810 72Nd Ave' -> '10810 72nd Ave', 'Po Box' -> 'PO Box', 'Ne' -> 'NE'."""
    if not s:
        return ""
    s = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)
    s = re.sub(r"\b(Ne|Nw|Se|Sw)\b", lambda m: m.group(1).upper(), s)
    s = re.sub(r"\bPo Box\b", "PO Box", s)
    return tidy_city(s)


def blank(v) -> str:
    v = (v or "").strip()
    return "" if v.upper() in ("NULL", "NONE", "N/A", "NAN") else v


def as_date(v: str):
    try:
        return dt.date.fromisoformat((v or "")[:10])
    except ValueError:
        return None


def long_date(d) -> str:
    d = as_date(d) if isinstance(d, str) else d
    return f"{d:%B} {d.day}, {d.year}" if d else ""


def short_date(d) -> str:
    d = as_date(d) if isinstance(d, str) else d
    return f"{d:%b} {d.day}, {d.year}" if d else ""


def clean_url(u: str) -> str:
    """Drop tracking parameters (utm_*, gclid...) so links read cleanly; the page they open is the same."""
    u = (u or "").strip()
    if not u:
        return ""
    if not re.match(r"https?://", u, re.I):
        u = "https://" + u
    try:
        p = urllib.parse.urlsplit(u)
    except ValueError:
        return u
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not re.match(r"(utm_|gclid|fbclid|y_source|mc_)", k, re.I)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), ""))


def domain(u: str) -> str:
    try:
        host = urllib.parse.urlsplit(u).netloc.lower()
    except ValueError:
        return u
    return host[4:] if host.startswith("www.") else host


SOCIAL_JUNK = re.compile(r"squarespace|wix\.com|godaddy|wordpress|weebly|facebook\.com/(?:\d+|sharer|tr)\b|"
                         r"profile\.php$|/intent/|/share", re.I)
SOCIAL_NAMES = (("facebook", "Facebook"), ("instagram", "Instagram"), ("linkedin", "LinkedIn"), ("twitter", "X"),
                ("x.com", "X"), ("youtube", "YouTube"), ("tiktok", "TikTok"))


def social_links(v: str) -> list[tuple[str, str]]:
    """[(name, url)]: the practice's own pages, without website-builder defaults."""
    out, seen = [], set()
    for u in (v or "").split():
        if SOCIAL_JUNK.search(u):
            continue
        name = next((n for k, n in SOCIAL_NAMES if k in u.lower()), "")
        if name and name not in seen:
            seen.add(name)
            out.append((name, u))
    return out


ENTITY = {"practice/organization": "Organization", "sole proprietor": "Solo provider", "individual": "Individual"}


def oig_text(v: str) -> str:
    v = blank(v)
    m = re.match(r"clear \(OIG list (\d{4})-(\d{2})\)", v)
    if m:
        return f"Clear ({dt.date(int(m.group(1)), int(m.group(2)), 1):%b %Y} list)"
    return v[:1].upper() + v[1:] if v else ""


# ------------------------------------------------------------------ the columns

# key -> (header, width, kind). kinds: text, wrap, int, num, date, phone, zip, npi, url, email, social, upper
COLS = {
    "priority": ("Priority", 9, "text"),
    "score": ("Score", 7, "int"),
    "name": ("Practice / provider", 36, "text"),
    "contact_name": ("Contact", 22, "text"),
    "contact_title": ("Contact title", 20, "text"),
    "contact_phone": ("Direct phone", 14.5, "phone"),
    "phone": ("Practice phone", 14.5, "phone"),
    "email": ("Email", 26, "email"),
    "website": ("Website", 24, "url"),
    "opener": ("Suggested opener", 60, "text"),
    "why": ("Why it scored", 48, "text"),
    "specialty": ("Specialty", 28, "text"),
    "category": ("Category", 22, "category"),
    "entity": ("Type", 13, "entity"),
    "credential": ("Credential", 11, "text"),
    "address": ("Street address", 30, "addr"),
    "city": ("City", 16, "city"),
    "state": ("State", 6.5, "text"),
    "zip": ("ZIP", 7.5, "zip"),
    "registered": ("Registered", 12, "date"),
    "moved_on": ("Moved on", 12, "date"),
    "moved_from": ("Moved from", 36, "addr"),
    "change_type": ("Change", 15, "cap"),
    "change_detail": ("Details", 38, "cap"),
    "changed_on": ("Changed on", 12, "date"),
    "revalidation_due": ("Revalidation due", 14, "date"),
    "days_until_due": ("Days until due", 10, "int"),
    "medicare_enrollment": ("Medicare enrollment", 26, "cap"),
    "providers_reassigned": ("Providers billing under it", 12, "int"),
    "medicare_status": ("Medicare status", 48, "cap"),
    "providers_at_practice": ("Providers at practice", 11, "int"),
    "medicare_pending": ("Medicare pending", 30, "cap"),
    "medicare_optout": ("Medicare opt-out", 26, "cap"),
    "practice_software": ("Practice software", 20, "text"),
    "social": ("Social", 22, "social"),
    "google_rating": ("Google rating", 15, "text"),
    "oig_check": ("OIG exclusion check", 22, "oig"),
    "fax": ("Fax", 14.5, "phone"),
    "license": ("License #", 13, "text"),
    "license_state": ("License state", 8, "text"),
    "other_taxonomies": ("Other specialties", 30, "text"),
    "npi": ("NPI", 12, "npi"),
    "taxonomy": ("Taxonomy code", 13, "text"),
}
SKIP = {"registry_link", "authorized_official", "official_title", "official_phone", "sole_proprietor"}

FRONT = {   # what a caller reads first, per list kind; everything else follows in COLS order
    "leads": ["priority", "score", "name", "contact_name", "contact_title", "contact_phone", "phone", "email", "website",
              "opener", "specialty", "category", "city", "state", "zip", "registered", "why"],
    "moved": ["priority", "score", "name", "moved_on", "moved_from", "address", "city", "state", "zip", "contact_name",
              "contact_title", "contact_phone", "phone", "email", "website", "opener", "specialty", "category", "why"],
    "changes": ["priority", "score", "name", "change_type", "change_detail", "changed_on", "contact_name",
                "contact_title", "contact_phone", "phone", "email", "website", "opener", "specialty", "category", "city",
                "state", "zip", "why"],
    "reval": ["priority", "score", "name", "revalidation_due", "days_until_due", "medicare_enrollment",
              "providers_reassigned", "contact_name", "contact_title", "contact_phone", "phone", "email", "website",
              "opener", "specialty", "category", "city", "state", "zip", "why"],
    "stuck": ["priority", "score", "name", "medicare_status", "registered", "contact_name", "contact_title",
              "contact_phone", "phone", "email", "website", "opener", "specialty", "category", "city", "state", "zip",
              "why"],
}
FRONT["history"] = FRONT["leads"]
TOP_COLS = ["score", "name", "contact_name", "contact_title", "contact_phone", "phone", "email", "website", "opener",
            "specialty", "city", "state", "registered", "npi"]

KINDS = {   # file prefix -> (tab name, title, what it is)
    "leads": ("New practices", "New practices registered this week",
              "Every new practice in your territory, sorted best-first with the top 25 highlighted."),
    "moved": ("Moved", "Practices that moved this week",
              "Medicare and every commercial plan need the new address on file: paid work for you."),
    "changes": ("Changes", "Reactivated and new specialties",
                "NPIs that were reactivated or added a specialty this week. Both mean new enrollments."),
    "history": ("Last 90 days", "Every new practice from the last 90 days",
                "Your head start: the practices that registered before your first list, newest first."),
    "reval": ("Revalidation due", "Practices due for Medicare revalidation",
              "Monthly. Established practices that already bill, soonest due first; overdue ones flagged."),
    "stuck": ("Stuck in credentialing", "Practices that look stuck in credentialing",
              "Monthly. Registered 2-12 months ago and still not on Medicare's enrollment list."),
}
ORDER = ["leads", "moved", "changes", "history", "reval", "stuck"]


def kind_of(path: Path) -> str:
    return path.name.split("_", 1)[0]


def read_rows(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        rows = [{k: (v or "") for k, v in r.items() if k} for r in rd]
        return [h for h in (rd.fieldnames or []) if h], rows


KEEP = {"name", "contact_name", "contact_title", "contact_phone", "phone", "email", "website", "opener", "npi",
        "specialty", "city", "state", "zip", "score"}      # shown even when empty (blank says "none found")


def columns_for(kind: str, header: list[str], rows: list[dict] | None = None) -> list[str]:
    if rows is not None:                                  # a column with nothing in it this time is left out
        header = [h for h in header if h in KEEP or any(blank(r.get(h, "")) for r in rows)]
    front = [c for c in FRONT.get(kind, FRONT["leads"]) if c in header]
    rest = [c for c in COLS if c in header and c not in front]
    extra = [h for h in header if h not in COLS and h not in SKIP and h not in front]
    return front + rest + extra


# ------------------------------------------------------------------ the workbook

class Book:
    """A thin layer over XlsxWriter with PanelReady's formats."""

    def __init__(self, path: Path, title: str, subject: str):
        import xlsxwriter                            # py -m pip install XlsxWriter
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.wb = xlsxwriter.Workbook(str(self.path), {"strings_to_urls": False, "strings_to_numbers": False,
                                                       "strings_to_formulas": False})
        self.wb.set_properties({"title": title, "subject": subject, "author": BRAND, "company": BRAND,
                                "manager": "", "category": "Lead list", "keywords": "PanelReady, NPPES, new practices",
                                "comments": "Public data from the CMS NPPES registry. panelready.co"})
        self.wb.set_size(1500, 960)
        self.f = {}
        self._formats()
        self.links = 0

    def fmt(self, **k):
        base = {"font_name": FONT, "font_size": 10, "font_color": BODY, "valign": "vcenter"}
        base.update(k)
        return self.wb.add_format(base)

    def _formats(self):
        F = self.fmt
        self.f.update(
            brand=F(font_name=SERIF, font_size=13, bold=True, font_color=INK, indent=1),
            title=F(font_name=SERIF, font_size=14, bold=True, font_color=INK),
            sub=F(font_size=9.5, font_color=MUTED),
            head=F(bold=True, font_color="#FFFFFF", bg_color=INK, text_wrap=True, valign="vcenter", border=1,
                   border_color=INK),
            cell=F(), wrap=F(text_wrap=True), top=F(valign="top"),
            int=F(num_format="0", align="center"), num=F(num_format="0.0"),
            date=F(num_format="mmm d, yyyy", align="left"),
            score=F(num_format="0", bold=True, font_color=INK, align="center"),
            link=F(font_color=TEAL, underline=1), link_top=F(font_color=TEAL, underline=1, valign="top"),
            center=F(align="center"),
            # conditional formats (only the changed bits)
            zebra=self.wb.add_format({"bg_color": "#F7F9FC"}),
            top25=self.wb.add_format({"bg_color": TEAL_SOFT, "font_color": TEAL, "bold": True}),
            excluded=self.wb.add_format({"bg_color": RED_SOFT, "font_color": RED, "bold": True}),
            pending=self.wb.add_format({"bg_color": AMBER_SOFT}),
            # overview
            h1=F(font_name=SERIF, font_size=22, bold=True, font_color=INK),
            h2=F(font_name=SERIF, font_size=13, bold=True, font_color=INK),
            kicker=F(font_size=9, bold=True, font_color=TEAL),
            lead=F(font_size=12, font_color=TEAL, bold=True),
            muted=F(font_size=10, font_color=MUTED), small=F(font_size=8.5, italic=True, font_color=MUTED, text_wrap=True,
                                                            valign="top"),
            body=F(font_size=10.5, text_wrap=True, valign="top"),
            body_b=F(font_size=10.5, bold=True, font_color=INK, text_wrap=True, valign="top"),
            step=F(font_size=11, bold=True, font_color="#FFFFFF", bg_color=TEAL, align="center", valign="top"),
            tile_n=F(font_name=SERIF, font_size=24, bold=True, font_color=INK, bg_color=CARD2, align="left",
                     valign="bottom", indent=1),
            tile_l=F(font_size=9.5, font_color=MUTED, bg_color=CARD2, align="left", valign="top", indent=1),
            tile_link=F(font_size=9.5, font_color=TEAL, underline=1, bg_color=CARD2, align="left", valign="top", indent=1),
            mini_head=F(font_size=9, bold=True, font_color=MUTED, bottom=1, bottom_color=LINE),
            mini=F(font_size=10, bottom=1, bottom_color=LINE),
            mini_score=F(font_size=10, bold=True, font_color=TEAL, align="center", bottom=1, bottom_color=LINE),
            mini_link=F(font_size=10, font_color=TEAL, underline=1, bottom=1, bottom_color=LINE),
            cta=F(font_size=11, bold=True, font_color="#FFFFFF", bg_color=TEAL, align="center"),
            cta_note=F(font_size=10, font_color=BODY, text_wrap=True, valign="vcenter"),
            box=F(font_size=10.5, text_wrap=True, valign="top", bg_color=CARD2, indent=1),
            mono=F(font_name="Consolas", font_size=10, text_wrap=True, valign="top", bg_color=CARD2, font_color=INK,
                   indent=1),
            guide_k=F(font_size=10, bold=True, font_color=INK, valign="top", bottom=1, bottom_color=LINE, text_wrap=True),
            guide_v=F(font_size=10, text_wrap=True, valign="top", bottom=1, bottom_color=LINE),
        )

    # -------------------------------------------------------------- shared pieces
    def logo(self, ws, row: int = 0, col: int = 0, height_px: float = 30, x: int = 3, y: int = 7):
        """The logo image, with the brand name under it in the same cell for viewers that skip images."""
        ws.write_string(row, col, BRAND, self.f["brand"])
        if LOGO.exists():
            s = height_px / LOGO_PX[1]
            ws.insert_image(row, col, str(LOGO), {"x_scale": s, "y_scale": s, "x_offset": x, "y_offset": y,
                                                 "object_position": 3, "description": "PanelReady logo",
                                                 "url": SITE, "tip": "panelready.co"})

    def print_setup(self, ws, landscape: bool = True, repeat_row: int | None = None):
        ws.set_paper(1)                                     # Letter
        if landscape:
            ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.4, right=0.4, top=0.7, bottom=0.6)
        ws.center_horizontally()
        if repeat_row is not None:
            ws.repeat_rows(repeat_row)
        if PRINT_LOGO.exists():
            ws.set_header("&L&G&R&8&K5B6B82panelready.co", {"image_left": str(PRINT_LOGO)})
        ws.set_footer("&L&8&K5B6B82PanelReady  ·  public data from the CMS NPI registry&R&8&K5B6B82Page &P of &N")

    def url(self, ws, r, c, url, text, fmt):
        url = clean_url(url) if not url.startswith("mailto:") else url
        if url and len(url) < 2000 and self.links < 60000:
            ws.write_url(r, c, url, fmt, text, tip="")
            self.links += 1
        else:
            ws.write_string(r, c, text, self.f["cell"])

    # -------------------------------------------------------------- one cell, by kind
    def cell(self, ws, r: int, c: int, key: str, row: dict, wrap: bool = False):
        kind = COLS.get(key, ("", 0, "text"))[2]
        v = blank(row.get(key, ""))
        f = self.f["wrap"] if wrap else self.f["cell"]
        link = self.f["link"]
        if not v:
            ws.write_blank(r, c, None, f)
            return
        if kind in ("int",):
            try:
                ws.write_number(r, c, int(float(v)), self.f["score"] if key == "score" else self.f["int"])
            except ValueError:
                ws.write_string(r, c, v, f)
        elif kind == "date":
            d = as_date(v)
            ws.write_datetime(r, c, dt.datetime(d.year, d.month, d.day), self.f["date"]) if d else ws.write_string(r, c, v, f)
        elif kind == "url":
            u = clean_url(v)
            self.url(ws, r, c, u, domain(u) or v, link)
        elif kind == "email":
            e = v.split()[0].strip(";,")
            self.url(ws, r, c, "mailto:" + e, e, link)
        elif kind == "npi":
            reg = row.get("registry_link") or f"https://npiregistry.cms.hhs.gov/provider-view/{v}"
            self.url(ws, r, c, reg, v, link)
        elif kind == "social":
            links = social_links(v)
            if links:
                self.url(ws, r, c, links[0][1], " · ".join(n for n, _ in links), link)
            else:
                ws.write_blank(r, c, None, f)
        elif kind == "category":
            ws.write_string(r, c, NICE.get(v, v.replace("_", " ").title()), f)
        elif kind == "entity":
            ws.write_string(r, c, ENTITY.get(v, v.capitalize()), f)
        elif kind == "addr":
            ws.write_string(r, c, tidy_addr(v), f)
        elif kind == "city":
            ws.write_string(r, c, tidy_city(v), f)
        elif kind == "oig":
            ws.write_string(r, c, oig_text(v), f)
        elif kind == "cap":
            ws.write_string(r, c, v[:1].upper() + v[1:], f)
        elif key == "priority":
            ws.write_string(r, c, "Top 25" if v.upper().startswith("TOP") else v, self.f["center"])
        elif key in ("name", "contact_name", "contact_title"):
            ws.write_string(r, c, tidy_name(v), f)
        elif key == "why":
            ws.write_string(r, c, v[:1].upper() + v[1:], f)
        else:
            ws.write_string(r, c, v, f)

    # -------------------------------------------------------------- a list tab
    def table(self, tab: str, title: str, sub: str, cols: list[str], rows: list[dict], wrap: set | None = None,
              tab_color: str | None = None, heights: bool = False):
        ws = self.wb.add_worksheet(tab[:31])
        ws.hide_gridlines(2)
        if tab_color:
            ws.set_tab_color(tab_color)
        wrap = wrap or set()
        ws.set_row(0, 36)
        self.logo(ws, 0, 0, height_px=30, x=3, y=8)
        ws.write_string(1, 0, title, self.f["title"])
        ws.set_row(1, 22)
        ws.write_string(2, 0, sub, self.f["sub"])
        ws.set_row(2, 17)
        hr = 3
        ws.set_row(hr, 30)
        for i, key in enumerate(cols):
            head, width, _ = COLS.get(key, (key.replace("_", " ").capitalize(), 18, "text"))
            ws.write_string(hr, i, head, self.f["head"])
            ws.set_column(i, i, width)
        for j, row in enumerate(rows, start=hr + 1):
            for i, key in enumerate(cols):
                self.cell(ws, j, i, key, row, wrap=key in wrap)
            if heights and wrap:     # Calibri 10 fits about 1.15 characters per unit of column width
                lines = max((math.ceil(len(blank(row.get(k, ""))) / (COLS.get(k, ("", 20))[1] * 1.12))
                             for k in wrap), default=1)
                ws.set_row(j, max(18, 13.2 * max(lines, 1) + 6))
        last = hr + max(len(rows), 1)
        n = len(cols) - 1
        if rows:
            ws.autofilter(hr, 0, last, n)
            if "priority" in cols:
                c = cols.index("priority")
                ws.conditional_format(hr + 1, c, last, c, {"type": "cell", "criteria": "==", "value": '"Top 25"',
                                                           "format": self.f["top25"]})
            if "oig_check" in cols:
                c = cols.index("oig_check")
                ws.conditional_format(hr + 1, c, last, c, {"type": "text", "criteria": "begins with",
                                                           "value": "EXCLUDED", "format": self.f["excluded"]})
            if "medicare_pending" in cols:
                c = cols.index("medicare_pending")
                ws.conditional_format(hr + 1, c, last, c, {"type": "no_blanks", "format": self.f["pending"]})
            # zebra stripes last: the highlights above take precedence on the striped rows
            ws.conditional_format(hr + 1, 0, last, n, {"type": "formula", "criteria": "=MOD(ROW(),2)=0",
                                                       "format": self.f["zebra"]})
        else:
            ws.write_string(hr + 1, 0, "Nothing on this list this time.", self.f["muted"])
        freeze_col = cols.index("name") + 1 if "name" in cols else 0
        ws.freeze_panes(hr + 1, freeze_col)
        ws.ignore_errors({"number_stored_as_text": f"A1:{_col(n)}{last + 1}"})
        self.print_setup(ws, landscape=True, repeat_row=hr)
        stop = cols.index("zip") if "zip" in cols else n
        ws.print_area(0, 0, last, min(stop, n))
        return ws

    def close(self) -> Path:
        self.wb.close()
        return self.path


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# ------------------------------------------------------------------ Overview + How to use

GUIDE_STEPS = [
    ("Start with the Top 25.", "The list is sorted best-first. Score (0-100) is how likely the practice needs "
     "credentialing and billing help soon; \"Why it scored\" says what drove it."),
    ("Ask for the contact by name.", "That's the owner or authorized official (the provider, for a solo practice). "
     "Try the Direct phone first when there is one, then the practice phone, then email."),
    ("Open with the suggested opener.", "It only states facts from the public registration (name, city, date, "
     "specialty), so it never sounds like a guess."),
]
CALL_SCRIPT = ('"Hi, is this {contact}? This is <you> from <your company>. {opener} We get new practices like yours '
               'credentialed with <Medicare / Medicaid / the big commercial plans> and billing within <N> weeks, so '
               'you\'re not waiting months on your first payments. Would a 10-minute call this week to see where you '
               'stand be worth it?"')
CALL_OBJECTION = 'If they already have someone: "Good to hear. If anything stalls, mind if I check back in 60 days?"'
EMAIL_TEMPLATE = ("Subject: Credentialing for {practice}\n\n{opener}\n\nWe help new {specialty} practices in {state} "
                  "get enrolled with payers and set up for billing, usually in <N> weeks. Want me to send a quick "
                  "checklist of what you'll need, or set up a 10-minute call?\n\n<signature>")
COLUMN_GUIDE = [
    ("Priority / Score", "Top 25 marks the 25 best leads in each state's list. Score is 0-100: how likely the practice "
     "needs credentialing and billing help soon."),
    ("Why it scored", "What drove the score: a new organization, a specialty with heavy payer enrollment, a "
     "multi-provider name, the owner's own phone, a very recent registration."),
    ("Contact, Contact title", "The owner or authorized official on the registration (the provider, for a solo practice)."),
    ("Direct phone", "The contact's own number from the registry, when it's different from the practice line. Try it first."),
    ("Practice phone, Fax, Street address", "As the practice filed them with the federal NPI registry."),
    ("Email, Website, Google rating", "Found for organizations on Google and on the practice's own website (on free "
     "lists, for the top 25). Blank means none was found yet."),
    ("Suggested opener", "A ready-to-say first line built only from facts in the public registration."),
    ("Practice software", "The EHR, practice-management, booking or patient-portal system the practice's website "
     "links to (SimplePractice, athenahealth, Tebra...). \"Insurance platform\" (Headway, Alma, Rula, Grow) means "
     "they're credentialed through a platform today: pitch going direct."),
    ("Social", "The practice's own Facebook, Instagram or LinkedIn pages (click to open the first)."),
    ("Providers at practice", "How many providers list the same phone number in the registry. Bigger groups mean more "
     "providers to enroll with every payer; 200+ is usually a hospital or health-system switchboard."),
    ("Medicare pending", "The provider's first Medicare application is on CMS's public pending list: they're "
     "mid-credentialing, a good moment to offer help with the commercial plans. Highlighted."),
    ("Medicare opt-out", "The provider has opted out of Medicare (they bill patients or commercial plans only)."),
    ("OIG exclusion check", "Checked against the federal OIG exclusion list. Anyone excluded (barred from Medicare and "
     "Medicaid billing) is flagged in red: check with your compliance contact before taking them on."),
    ("License #, License state, Other specialties, Taxonomy code", "From the practice's registry record."),
    ("NPI", "The practice's National Provider Identifier. Click it to open the official CMS registry record."),
    ("Moved on, Moved from", "Moved tab: when the practice changed its address in the registry, and where it was before."),
    ("Change, Details, Changed on", "Changes tab: an NPI that was reactivated or added a specialty, and when."),
    ("Revalidation due, Days until due", "Revalidation tab (monthly): when Medicare needs the practice to revalidate "
     "its enrollment. Negative days means overdue."),
    ("Medicare status", "Stuck tab (monthly): how long the practice has been registered without appearing on "
     "Medicare's enrollment list."),
]
GUARANTEE = ("The PanelReady guarantee: sign at least one new client from your lists in your first 90 days as a "
             "subscriber, or reply and tell us, and your next 3 months are free.")
SOURCE_NOTE = ("Every record comes from the public NPPES file published weekly by CMS (the federal NPI registry), as "
               "the provider filed it, and is provided as-is. Websites, emails and ratings are found on Google and "
               "the practice's own site. Click any NPI to see the official record.")


def overview(book: Book, info: dict, counts: list[tuple[str, int, str]], hot: list[dict]):
    """The cover tab. info: kicker, title, lead, prepared, note, tabs [(tab, what)], cta (label, url), cta_note.
    Grid: a margin column, then eight 13-wide columns (B-I)."""
    f, F = book.f, book.fmt
    ws = book.wb.add_worksheet("Overview")
    ws.hide_gridlines(2)
    ws.set_tab_color(INK)
    ws.set_column(0, 0, 2.5)
    ws.set_column(1, 8, 13)
    ws.set_column(9, 9, 2.5)
    ws.set_row(0, 10)
    ws.set_row(1, 44)
    book.logo(ws, 1, 1, height_px=36, x=2, y=10)
    ws.merge_range(1, 7, 1, 8, "", F(font_size=10, font_color=MUTED, align="right"))
    ws.write_url(1, 7, SITE, F(font_size=10, font_color=MUTED, align="right"), "panelready.co")
    r = 3
    ws.write_string(r, 1, info.get("kicker", "").upper(), f["kicker"]); r += 1
    ws.set_row(r, 34)
    ws.write_string(r, 1, info["title"], f["h1"]); r += 1
    ws.set_row(r, 20)
    ws.write_string(r, 1, info.get("lead", ""), f["lead"]); r += 1
    if info.get("prepared"):
        ws.write_string(r, 1, info["prepared"], f["muted"])
    r += 2
    gap = {"left": 5, "left_color": "#FFFFFF", "right": 5, "right_color": "#FFFFFF"}
    num = F(font_name=SERIF, font_size=24, bold=True, font_color=INK, bg_color=CARD2, num_format="#,##0",
            align="left", valign="bottom", indent=1, top=5, top_color="#FFFFFF", **gap)
    lab = F(font_size=9.5, font_color=TEAL, underline=1, bg_color=CARD2, align="left", valign="top", indent=1,
            bottom=5, bottom_color="#FFFFFF", **gap)
    for k in range(0, len(counts), 4):
        ws.set_row(r, 36)
        ws.set_row(r + 1, 20)
        for t, (label, n, tab) in enumerate(counts[k:k + 4]):
            c = 1 + 2 * t
            ws.merge_range(r, c, r, c + 1, "", num)
            ws.write_number(r, c, n, num)
            ws.merge_range(r + 1, c, r + 1, c + 1, "", lab)
            ws.write_url(r + 1, c, f"internal:'{tab}'!A1", lab, label + "  ›")
        r += 2
    r += 1
    if info.get("note"):
        ws.merge_range(r, 1, r, 8, info["note"], f["body"])
        ws.set_row(r, 15 * max(1, math.ceil(len(info["note"]) / 110)) + 4)
        r += 2
    if hot:
        ws.set_row(r, 22)
        ws.write_string(r, 1, "Hottest leads", f["h2"]); r += 1
        for c1, c2, h in ((1, 1, "Score"), (2, 4, "Practice"), (5, 6, "Specialty"), (7, 7, "City"), (8, 8, "NPI")):
            if c1 == c2:
                ws.write_string(r, c1, h, f["mini_head"])
            else:
                ws.merge_range(r, c1, r, c2, h, f["mini_head"])
        r += 1
        left_score = F(font_size=10, bold=True, font_color=TEAL, align="left", indent=1, bottom=1, bottom_color=LINE)
        for row in hot[:10]:
            ws.set_row(r, 18)
            try:
                ws.write_number(r, 1, int(float(row.get("score") or 0)), left_score)
            except ValueError:
                ws.write_string(r, 1, "", left_score)
            ws.merge_range(r, 2, r, 4, tidy_name(row.get("name", "")), f["mini"])
            ws.merge_range(r, 5, r, 6, blank(row.get("specialty", "")), f["mini"])
            ws.write_string(r, 7, tidy_city(row.get("city", "")) + (", " + row["state"] if row.get("state") else ""), f["mini"])
            npi = blank(row.get("npi", ""))
            if npi:
                ws.write_url(r, 8, row.get("registry_link") or f"https://npiregistry.cms.hhs.gov/provider-view/{npi}",
                             f["mini_link"], npi)
            else:
                ws.write_string(r, 8, "", f["mini"])
            r += 1
        r += 1
    ws.set_row(r, 22)
    ws.write_string(r, 1, "How to work this list", f["h2"]); r += 1
    step_n = F(font_name=SERIF, font_size=14, bold=True, font_color=TEAL, align="center", valign="top")
    for n, (head, text) in enumerate(GUIDE_STEPS, 1):
        ws.write_number(r, 1, n, step_n)
        ws.merge_range(r, 2, r, 8, "", f["body"])
        ws.write_rich_string(r, 2, f["body_b"], head + " ", f["body"], text, f["body"])
        ws.set_row(r, 15 * max(1, math.ceil((len(head) + len(text)) / 98)) + 6)
        r += 1
    r += 1
    if info.get("tabs"):
        ws.set_row(r, 22)
        ws.write_string(r, 1, "In this workbook", f["h2"]); r += 1
        tab_f = F(font_size=10.5, bold=True, font_color=TEAL, underline=1, valign="top")
        for tab, what in info["tabs"]:
            ws.merge_range(r, 1, r, 2, "", tab_f)
            ws.write_url(r, 1, f"internal:'{tab}'!A1", tab_f, tab)
            ws.merge_range(r, 3, r, 8, what, f["body"])
            ws.set_row(r, 15 * max(1, math.ceil(len(what) / 82)) + 4)
            r += 1
        r += 1
    if info.get("cta"):
        label, link = info["cta"]
        ws.set_row(r, 28)
        ws.merge_range(r, 1, r, 2, "", f["cta"])
        ws.write_url(r, 1, link, f["cta"], label)
        if info.get("cta_note"):
            ws.merge_range(r, 3, r, 8, info["cta_note"], F(font_size=10, font_color=BODY, text_wrap=True, indent=1))
        r += 2
    ws.merge_range(r, 1, r + 1, 8, SOURCE_NOTE, f["small"])
    ws.set_row(r, 18); ws.set_row(r + 1, 18)
    ws.ignore_errors({"number_stored_as_text": f"A1:J{r + 2}"})     # the NPIs in "Hottest leads"
    ws.set_paper(1)
    ws.fit_to_pages(1, 1)
    ws.set_margins(left=0.5, right=0.5, top=0.5, bottom=0.6)
    ws.center_horizontally()
    ws.set_footer("&L&8&K5B6B82PanelReady  ·  panelready.co&R&8&K5B6B82Page &P of &N")
    ws.activate()
    return ws


def how_to(book: Book):
    f = book.f
    ws = book.wb.add_worksheet("How to use")
    ws.hide_gridlines(2)
    ws.set_column(0, 0, 2.5)
    ws.set_column(1, 1, 30)
    ws.set_column(2, 2, 78)
    ws.set_column(3, 3, 2.5)
    ws.set_row(0, 10)
    ws.set_row(1, 44)
    book.logo(ws, 1, 1, height_px=36, x=2, y=10)
    r = 3
    ws.set_row(r, 30)
    ws.write_string(r, 1, "How to use your list", f["h1"]); r += 2
    ws.write_string(r, 1, "Work the list in three steps", f["h2"]); ws.set_row(r, 22); r += 1
    for n, (head, text) in enumerate(GUIDE_STEPS, 1):
        ws.write_string(r, 1, f"{n}.  {head}", f["body_b"])
        ws.write_string(r, 2, text, f["body"])
        ws.set_row(r, 15 * max(1, math.ceil(len(text) / 92)) + 4)
        r += 1
    r += 1
    ws.write_string(r, 1, "Call script (60 seconds)", f["h2"]); ws.set_row(r, 22); r += 1
    ws.merge_range(r, 1, r, 2, CALL_SCRIPT.replace("{contact}", "<Contact>").replace("{opener}", "<Suggested opener>"),
                   f["box"])
    ws.set_row(r, 62); r += 1
    ws.merge_range(r, 1, r, 2, CALL_OBJECTION, f["muted"]); r += 2
    ws.write_string(r, 1, "Email template", f["h2"]); ws.set_row(r, 22); r += 1
    ws.merge_range(r, 1, r, 2, EMAIL_TEMPLATE.replace("{practice}", "<Practice>").replace("{opener}", "<Suggested opener>")
                   .replace("{specialty}", "<specialty>").replace("{state}", "<state>"), f["mono"])
    ws.set_row(r, 120); r += 2
    ws.write_string(r, 1, "What every column means", f["h2"]); ws.set_row(r, 22); r += 1
    for k, v in COLUMN_GUIDE:
        ws.write_string(r, 1, k, f["guide_k"])
        ws.write_string(r, 2, v, f["guide_v"])
        ws.set_row(r, 14.5 * max(1, math.ceil(len(v) / 96), math.ceil(len(k) / 32)) + 5)
        r += 1
    r += 1
    ws.merge_range(r, 1, r, 2, GUARANTEE, f["body_b"]); ws.set_row(r, 30); r += 2
    ws.merge_range(r, 1, r + 1, 2, SOURCE_NOTE, f["small"])
    ws.set_row(r, 15); ws.set_row(r + 1, 15)
    ws.set_paper(1)
    ws.fit_to_pages(1, 0)
    ws.set_margins(left=0.5, right=0.5, top=0.5, bottom=0.6)
    ws.set_footer("&L&8&K5B6B82PanelReady  ·  panelready.co&R&8&K5B6B82Page &P of &N")
    return ws


# ------------------------------------------------------------------ one delivery

def territory_words(states: list[str], cats: list[str], area: str = "") -> str:
    if area:
        z, _, miles = area.partition(":")
        return f"Within {miles or 25} miles of {z}"
    names = [STATES.get(s, s) for s in states]
    where = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else "Your territory"
    if not cats or "all" in cats:
        return where
    return f"{where} · " + ", ".join(NICE.get(c, c) for c in cats)


def file_tag(states: list[str], area: str = "") -> str:
    if area:
        z, _, miles = area.partition(":")
        return f"{z}_{miles or 25}mi"
    return "-".join(states) or "list"


def build_delivery(files: list[Path], out_dir: Path, *, week: str, states: list[str], cats: list[str],
                   area: str = "", name: str = "", status: str = "paid", n_list: int = 1, trial_lists: int = 2,
                   plans_url: str = f"{SITE}/#pricing", one_time: bool = False, sample: bool = False,
                   note: str = "", fname: str = "", since: str = "", note_only: bool = False) -> Path:
    """The workbook for one delivery. `files`: the upgraded CSVs (leads / moved / changes / history / reval / stuck),
    in any order; anything else (the CRM file, the kit) is ignored."""
    by_kind: dict[str, list[Path]] = {}
    for p in files:
        if p and p.suffix == ".csv" and kind_of(p) in KINDS:
            by_kind.setdefault(kind_of(p), []).append(p)
    wk = as_date(week)
    where = territory_words(states, cats, area)
    label = "Sample list" if sample else ("One-time list" if one_time else
                                          (f"Free list {n_list} of {trial_lists}" if status == "trial" else "Weekly list"))
    override = fname
    fname = f"PanelReady_{file_tag(states, area)}_week_of_{wk:%b}_{wk.day}_{wk.year}.xlsx" if wk else "PanelReady_list.xlsx"
    if sample:
        fname = fname.replace("PanelReady_", "PanelReady_Sample_", 1)
    fname = override or fname
    book = Book(out_dir / fname, f"PanelReady: {where}, week ending {long_date(wk)}",
                f"New healthcare practices, {where}")
    tabs: list[tuple[str, list[str], list[dict], str, str, str]] = []
    leads_rows: list[dict] = []
    for kind in ORDER:
        header, rows = [], []
        for p in by_kind.get(kind, []):
            h, rs = read_rows(p)
            header += [x for x in h if x not in header]
            rows += rs
        if not header:
            continue
        if kind in ("leads", "moved", "changes", "reval", "stuck") and any(r.get("score") for r in rows):
            rows.sort(key=lambda r: -int(float(r.get("score") or 0)))
        if kind == "reval":
            rows.sort(key=lambda r: int(float(r.get("days_until_due") or 9999)))
        if kind == "history":
            rows.sort(key=lambda r: r.get("registered", ""), reverse=True)
        if kind == "leads":
            leads_rows = rows
        tab, title, sub = KINDS[kind]
        days = ""
        if kind == "leads" and wk:
            start = as_date(since) or (wk - dt.timedelta(days=6))
            days = f" ({start:%b} {start.day}-{wk:%b} {wk.day})"
            if as_date(since):
                title = f"New practices registered in the last {max(1, round(((wk - start).days + 1) / 7))} weeks"
        title = f"{title}: {where}" if kind != "leads" else f"{title}{days}: {where}"
        tabs.append((tab, columns_for(kind, header, rows), rows, title, f"{len(rows):,} {'row' if len(rows) == 1 else 'rows'}. {sub} "
                     f"Click an NPI to open the official CMS record.", kind))
    top = [] if sample else [r for r in leads_rows if (r.get("priority") or "").upper().startswith("TOP")]
    counts = []
    for tab, cols, rows, *_ , kind in tabs:
        counts.append(({"leads": "New practices", "moved": "Practices that moved", "changes": "Reactivated / new specialty",
                        "history": "New in the last 90 days", "reval": "Due for revalidation",
                        "stuck": "Stuck in credentialing"}[kind], len(rows), tab))
        if kind == "leads" and top:
            counts.insert(1, ("Top picks to call first", len(top), "Top 25"))
    tab_list = []
    if top:
        tab_list.append(("Top 25", "The best leads to call first, with the owner's direct line and a ready-to-say opener."))
    for tab, _, rows, _, _, kind in tabs:
        tab_list.append((tab, KINDS[kind][2]))
    tab_list.append(("How to use", "The call script, an email template, and what every column means."))
    first = (name or "").split()[0] if name else ""
    info = {"kicker": f"{BRAND} · {label}",
            "title": where,
            "lead": (f"New healthcare practices, {short_date(since)} to {short_date(wk)}" if as_date(since) and wk else
                     f"New healthcare practices, week ending {long_date(wk)}" if wk else "New healthcare practices"),
            "prepared": "  ·  ".join(x for x in (f"Prepared for {name}" if name else "",
                                                 f"{dt.date.today():%B} {dt.date.today().day}, {dt.date.today().year}") if x),
            "tabs": tab_list}
    if sample and note_only:
        info["note"] = note
        info["cta"] = ("Get 2 lists free", f"{SITE}/#free")
        info["cta_note"] = "Your own state and specialties, two weekly lists free. No card, no call."
    elif sample:
        info["note"] = (note + " " if note else "") + ("This sample has a handful of practices from this week's lists. A subscriber's list has every "
                        "new practice in their territory, every week, with websites and emails we find for "
                        "organizations, plus the practices that moved or added a specialty.")
        info["cta"] = ("Get 2 lists free", f"{SITE}/#free")
        info["cta_note"] = "Tell us your states and specialties and your first two weekly lists are free. No card."
    elif status == "trial":
        info["note"] = (f"Free list {n_list} of {trial_lists}. Websites and emails are looked up for the Top 25 on free "
                        f"lists; subscribers get them for every organization we can find, plus the last 90 days of new "
                        f"practices with their first list and two monthly lists (revalidation due, stuck in "
                        f"credentialing).")
        info["cta"] = ("See plans", plans_url)
        info["cta_note"] = "Keep the full list coming every week. Cancel any time from PayPal."
    elif one_time:
        info["cta"] = ("Get it every week", plans_url)
        info["cta_note"] = "The same list every Monday, plus the practices that moved and the monthly lists."
    else:
        info["cta"] = ("Your account", f"{SITE}/account/")
        info["cta_note"] = ("Past lists, Search & export, territory, teammates and Roster Watch. Sign in with the email "
                            "your lists go to.")
    overview(book, info, counts, (top or leads_rows)[:10])
    if top:
        book.table("Top 25", f"Top picks to call first: {where}",
                   f"{len(top)} best leads{' (25 per state)' if len(states) > 1 else ''}, highest score first. "
                   f"Start with the Direct phone when there is one.",
                   [c for c in TOP_COLS if c in (tabs[0][1] if tabs else [])], top,
                   wrap={"opener", "name", "specialty", "contact_title"}, tab_color=TEAL,
                   heights=True)
    for tab, cols, rows, title, sub, kind in tabs:
        book.table(tab, title, sub, cols, rows)
    how_to(book)
    return book.close()
