"""PanelReady: turn the federal NPPES weekly file into lead lists of newly registered practices.

A "lead" is an organization (practice, clinic, agency, supplier) or a sole-proprietor individual that
registered for an NPI in the week covered by the file. Each is put in one category by its primary taxonomy
code, so a behavioral-health credentialing company gets only therapists and a dental billing company gets
only dentists. Pure functions; pull_npi.py does the downloading and file writing.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import zipfile

CATEGORIES = ["behavioral", "medical", "dental", "therapy", "home_senior", "dme_transport"]
NICE = {"behavioral": "Behavioral Health", "medical": "Medical Practices & Clinics", "dental": "Dental",
        "therapy": "Therapy & Rehab", "home_senior": "Home Care & Senior Living",
        "dme_transport": "DME, Pharmacy & Transport", "all": "All Categories"}

# taxonomy code prefixes -> category (first match wins, longest prefixes first)
_RULES = [
    ("261QM0801X", "behavioral"), ("261QM0850X", "behavioral"), ("261QM0855X", "behavioral"),
    ("261QR0405X", "behavioral"), ("2084P0800X", "behavioral"), ("2084P0804X", "behavioral"),
    ("363LP0808X", "behavioral"), ("251S", "behavioral"), ("3245", "behavioral"), ("101Y", "behavioral"),
    ("1041", "behavioral"), ("103T", "behavioral"), ("103K", "behavioral"), ("103G", "behavioral"),
    ("106H", "behavioral"), ("106S", "behavioral"), ("106E", "behavioral"), ("102L", "behavioral"),
    ("102X", "behavioral"), ("104100000X", "behavioral"),
    ("3208", "behavioral"),
    ("122", "dental"), ("124Q", "dental"), ("125", "dental"), ("126", "dental"),
    ("225", "therapy"), ("235Z", "therapy"), ("231H", "therapy"), ("237", "therapy"), ("111N", "therapy"),
    ("1711", "therapy"), ("133", "therapy"), ("213E", "therapy"), ("152W", "therapy"), ("224", "therapy"),
    ("2278", "therapy"), ("2279", "therapy"), ("222Z", "therapy"), ("226", "therapy"), ("175F", "therapy"),
    ("261QR0400X", "therapy"), ("261QP1100X", "therapy"), ("261QP2000X", "therapy"),
    ("251E", "home_senior"), ("253Z", "home_senior"), ("374", "home_senior"), ("376", "home_senior"),
    ("3104", "home_senior"), ("3140", "home_senior"), ("311", "home_senior"), ("313", "home_senior"),
    ("315", "home_senior"), ("3105", "home_senior"), ("385H", "home_senior"), ("3209", "home_senior"),
    ("251B", "home_senior"), ("251C", "home_senior"), ("251F", "home_senior"), ("251G", "home_senior"),
    ("251J", "home_senior"), ("251X", "home_senior"), ("252Y", "home_senior"), ("253J", "home_senior"),
    ("171M", "home_senior"),
    ("332", "dme_transport"), ("3336", "dme_transport"), ("3343", "dme_transport"), ("3416", "dme_transport"),
    ("3438", "dme_transport"), ("3439", "dme_transport"), ("344", "dme_transport"), ("347", "dme_transport"),
    ("183", "dme_transport"), ("335", "dme_transport"), ("333", "dme_transport"), ("3418", "dme_transport"),
    ("20", "medical"), ("363L", "medical"), ("363A", "medical"), ("367", "medical"), ("261Q", "medical"),
    ("282", "medical"), ("283", "medical"), ("29", "medical"), ("1223", "dental"), ("367A", "medical"),
    ("364S", "medical"), ("174", "medical"), ("1744", "medical"), ("1932", "medical"), ("1934", "medical"),
]
_RULES.sort(key=lambda r: -len(r[0]))

# common taxonomy names, used when the NUCC file isn't available (the full list has ~870 codes)
TAX_NAMES = {
    # behavioral
    "101Y00000X": "Counselor", "101YA0400X": "Addiction counselor", "101YM0800X": "Mental health counselor",
    "101YP1600X": "Pastoral counselor", "101YP2500X": "Professional counselor", "101YS0200X": "School counselor",
    "102L00000X": "Psychoanalyst", "103G00000X": "Clinical neuropsychologist", "103K00000X": "Behavior analyst",
    "103T00000X": "Psychologist", "103TC0700X": "Clinical psychologist",
    "103TC2200X": "Clinical child & adolescent psychologist", "103TB0200X": "Cognitive & behavioral psychologist",
    "103TH0004X": "Health psychologist", "103TS0200X": "School psychologist", "104100000X": "Social worker",
    "1041C0700X": "Clinical social worker", "1041S0200X": "School social worker",
    "106E00000X": "Assistant behavior analyst", "106H00000X": "Marriage & family therapist",
    "106S00000X": "Behavior technician", "2084P0800X": "Psychiatrist", "2084P0804X": "Child & adolescent psychiatrist",
    "2084P0802X": "Addiction psychiatrist", "2084A0401X": "Addiction medicine (psychiatry & neurology)",
    "363LP0808X": "Psychiatric nurse practitioner", "251S00000X": "Community/behavioral health agency",
    "261QM0801X": "Mental health clinic", "261QM0850X": "Adult mental health clinic",
    "261QM0855X": "Child & adolescent mental health clinic", "261QR0405X": "Substance use disorder rehab clinic",
    "324500000X": "Substance abuse rehabilitation facility",
    # medical
    "207Q00000X": "Family medicine", "207QG0300X": "Family medicine, geriatric", "207QS0010X": "Family medicine, sports",
    "207QH0002X": "Family medicine, hospice & palliative", "207R00000X": "Internal medicine",
    "207RC0000X": "Cardiovascular disease", "207RE0101X": "Endocrinology", "207RG0100X": "Gastroenterology",
    "207RG0300X": "Internal medicine, geriatric", "207RH0003X": "Hematology & oncology",
    "207RI0200X": "Infectious disease", "207RN0300X": "Nephrology", "207RP1001X": "Pulmonary disease",
    "207RR0500X": "Rheumatology", "207RS0012X": "Sleep medicine", "208D00000X": "General practice",
    "208000000X": "Pediatrics", "2080P0208X": "Pediatric infectious diseases", "2080P0006X": "Developmental-behavioral pediatrics",
    "207V00000X": "Obstetrics & gynecology", "207X00000X": "Orthopaedic surgery", "207Y00000X": "Otolaryngology",
    "207N00000X": "Dermatology", "207W00000X": "Ophthalmology", "207L00000X": "Anesthesiology",
    "207P00000X": "Emergency medicine", "207T00000X": "Neurological surgery", "2084N0400X": "Neurology",
    "208600000X": "Surgery", "2086S0122X": "Plastic & reconstructive surgery", "208200000X": "Plastic surgery",
    "208100000X": "Physical medicine & rehabilitation", "2081P2900X": "Pain medicine",
    "208VP0014X": "Interventional pain medicine", "2085R0202X": "Diagnostic radiology", "208800000X": "Urology",
    "207K00000X": "Allergy & immunology", "204E00000X": "Oral & maxillofacial surgery (physician)",
    "363L00000X": "Nurse practitioner", "363LF0000X": "Nurse practitioner, family",
    "363LA2200X": "Nurse practitioner, adult health", "363LA2100X": "Nurse practitioner, acute care",
    "363LG0600X": "Nurse practitioner, gerontology", "363LP0200X": "Nurse practitioner, pediatrics",
    "363LP2300X": "Nurse practitioner, primary care", "363LW0102X": "Nurse practitioner, women's health",
    "363LX0001X": "Nurse practitioner, OB/GYN", "363LN0000X": "Nurse practitioner, neonatal",
    "363LC1500X": "Nurse practitioner, community health", "363LC0200X": "Nurse practitioner, critical care",
    "363A00000X": "Physician assistant", "363AM0700X": "Physician assistant, medical",
    "363AS0400X": "Physician assistant, surgical", "367500000X": "Nurse anesthetist (CRNA)",
    "367A00000X": "Advanced practice midwife", "364S00000X": "Clinical nurse specialist", "163W00000X": "Registered nurse",
    "261Q00000X": "Clinic/center", "261QP2300X": "Primary care clinic", "261QU0200X": "Urgent care",
    "261QM1300X": "Multi-specialty clinic", "261QF0400X": "Federally qualified health center (FQHC)",
    "261QR1300X": "Rural health clinic", "261QA1903X": "Ambulatory surgical center", "261QE0002X": "Emergency care clinic",
    "261QC1500X": "Community health clinic", "261QH0100X": "Health service clinic", "261QX0200X": "Oncology clinic",
    "261QR0200X": "Radiology clinic", "261QM2500X": "Medical specialty clinic", "261QS1200X": "Sleep disorder clinic",
    "261QA0600X": "Adult day care clinic", "282N00000X": "General acute care hospital",
    "282NC0060X": "Critical access hospital", "283Q00000X": "Psychiatric hospital",
    "291U00000X": "Clinical medical laboratory", "293D00000X": "Physiological laboratory",
    "193200000X": "Multi-specialty group", "193400000X": "Single specialty group", "174400000X": "Specialist",
    "175F00000X": "Naturopath", "172V00000X": "Community health worker", "171100000X": "Acupuncturist",
    # dental
    "122300000X": "Dentist", "1223G0001X": "Dentist, general", "1223P0221X": "Pediatric dentist",
    "1223X0400X": "Orthodontist", "1223E0200X": "Endodontist", "1223P0300X": "Periodontist",
    "1223S0112X": "Oral & maxillofacial surgeon", "1223P0700X": "Prosthodontist", "1223D0001X": "Dental public health",
    "1223X0008X": "Oral & maxillofacial radiologist", "124Q00000X": "Dental hygienist", "126800000X": "Dental assistant",
    "126900000X": "Dental laboratory technician", "125J00000X": "Dental therapist", "261QD0000X": "Dental clinic",
    # therapy & rehab
    "225100000X": "Physical therapist", "2251X0800X": "Physical therapist, orthopedic",
    "225200000X": "Physical therapy assistant", "225X00000X": "Occupational therapist",
    "224Z00000X": "Occupational therapy assistant", "235Z00000X": "Speech-language pathologist",
    "231H00000X": "Audiologist", "237600000X": "Audiologist-hearing aid fitter", "111N00000X": "Chiropractor",
    "133V00000X": "Dietitian", "133VN1004X": "Dietitian, pediatric nutrition", "133N00000X": "Nutritionist",
    "152W00000X": "Optometrist", "152WC0802X": "Optometrist, contact lens", "213E00000X": "Podiatrist",
    "213ES0103X": "Podiatrist, foot & ankle surgery", "225700000X": "Massage therapist",
    "226300000X": "Kinesiotherapist", "224P00000X": "Prosthetist", "222Z00000X": "Orthotist",
    "2255A2300X": "Athletic trainer", "227800000X": "Respiratory therapist, certified",
    "227900000X": "Respiratory therapist, registered", "261QP1100X": "Podiatric clinic",
    "261QP2000X": "Physical therapy clinic", "261QR0400X": "Rehabilitation clinic",
    # home care & senior living
    "251E00000X": "Home health agency", "251B00000X": "Case management agency",
    "251C00000X": "Day training, developmental disabilities", "251G00000X": "Hospice care, community based",
    "251J00000X": "Nursing care agency", "251K00000X": "Public health or welfare agency",
    "251V00000X": "Voluntary or charitable agency", "251X00000X": "Supports brokerage", "251F00000X": "Home infusion",
    "252Y00000X": "Early intervention provider agency", "253J00000X": "Foster care agency",
    "253Z00000X": "In-home supportive care", "3747P1801X": "Personal care attendant",
    "3747A0650X": "Attendant care provider", "374U00000X": "Home health aide", "376J00000X": "Homemaker",
    "376K00000X": "Nurse's aide", "310400000X": "Assisted living", "3104A0625X": "Assisted living, mental illness",
    "3104A0630X": "Assisted living, behavioral disturbances", "314000000X": "Skilled nursing facility",
    "3140N1450X": "Skilled nursing facility, pediatric", "311500000X": "Alzheimer/dementia center",
    "311Z00000X": "Custodial care facility", "313M00000X": "Nursing facility / intermediate care",
    "315D00000X": "Hospice, inpatient", "315P00000X": "Intermediate care facility, intellectual disabilities",
    "385H00000X": "Respite care", "320800000X": "Residential treatment, mental illness",
    "320900000X": "Residential treatment, developmental disabilities", "171M00000X": "Case manager / care coordinator",
    # DME, pharmacy & transport
    "332B00000X": "DME & medical supplies", "332BC3200X": "DME, customized equipment",
    "332BX2000X": "DME, oxygen equipment", "332BP3500X": "DME, parenteral & enteral nutrition",
    "332BN1400X": "DME, nursing facility supplies", "332U00000X": "Home delivered meals",
    "333600000X": "Pharmacy", "3336C0003X": "Community/retail pharmacy", "3336C0004X": "Compounding pharmacy",
    "3336H0001X": "Home infusion therapy pharmacy", "3336I0012X": "Institutional pharmacy",
    "3336L0003X": "Long term care pharmacy", "3336M0002X": "Mail order pharmacy", "3336S0011X": "Specialty pharmacy",
    "335E00000X": "Prosthetic/orthotic supplier", "335V00000X": "Portable x-ray supplier",
    "335G00000X": "Medical foods supplier", "333300000X": "Emergency response system company",
    "341600000X": "Ambulance", "3416A0800X": "Ambulance, air", "3416L0300X": "Ambulance, land",
    "343900000X": "Non-emergency medical transport", "343800000X": "Secured medical transport",
    "344600000X": "Taxi", "344800000X": "Air carrier", "347B00000X": "Bus", "347C00000X": "Private vehicle",
    "183500000X": "Pharmacist", "1835P1200X": "Pharmacist, pharmacotherapy", "1835P1300X": "Pharmacist, psychiatric",
    "1835G0303X": "Pharmacist, geriatric", "1835C0205X": "Pharmacist, critical care",
    "1835P0018X": "Pharmacist clinician", "183700000X": "Pharmacy technician",
}


def category(taxonomy: str) -> str:
    t = (taxonomy or "").upper()
    for prefix, cat in _RULES:
        if t.startswith(prefix):
            return cat
    return "medical" if t[:1] == "2" else "other"


def _d(s: str):
    try:
        return dt.datetime.strptime(s, "%m/%d/%Y").date()
    except (ValueError, TypeError):
        return None


def _col(header, *needles):
    for n in needles:
        for h in header:
            if n.lower() == h.lower():
                return h
    for n in needles:
        for h in header:
            if n.lower() in h.lower():
                return h
    return None


LEAD_HEADER = ["registered", "category", "specialty", "name", "entity", "credential", "phone", "address", "city",
               "state", "zip", "npi", "taxonomy", "sole_proprietor", "authorized_official"]


def leads_from_weekly(zip_bytes: bytes, week_end: dt.date, names: dict | None = None, days: int = 9) -> list[dict]:
    """Rows from the weekly zip that are NEW registrations (not updates), as lead dicts."""
    names = names or {}
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    name = next((n for n in z.namelist() if n.lower().startswith("npidata_pfile") and n.lower().endswith(".csv")
                 and "fileheader" not in n.lower()), None)
    if not name:
        raise RuntimeError(f"no npidata CSV in the zip: {z.namelist()}")
    f = io.TextIOWrapper(z.open(name), encoding="utf-8", errors="replace")
    rd = csv.DictReader(f)
    H = rd.fieldnames or []
    c = {k: _col(H, v) for k, v in {
        "type": "Entity Type Code", "org": "Provider Organization Name (Legal Business Name)",
        "last": "Provider Last Name (Legal Name)", "first": "Provider First Name", "cred": "Provider Credential Text",
        "addr": "Provider First Line Business Practice Location Address",
        "city": "Provider Business Practice Location Address City Name",
        "state": "Provider Business Practice Location Address State Name",
        "zip": "Provider Business Practice Location Address Postal Code",
        "phone": "Provider Business Practice Location Address Telephone Number",
        "enum": "Provider Enumeration Date", "tax": "Healthcare Provider Taxonomy Code_1",
        "sole": "Is Sole Proprietor", "deact": "NPI Deactivation Date", "npi": "NPI",
        "aof": "Authorized Official Last Name", "aofirst": "Authorized Official First Name",
        "country": "Provider Business Practice Location Address Country Code (If outside U.S.)"}.items()}
    cutoff = week_end - dt.timedelta(days=days)
    out = []
    for r in rd:
        e = _d(r.get(c["enum"] or "", ""))
        if not e or e < cutoff or (r.get(c["deact"] or "") or "").strip():
            continue
        if (r.get(c["country"] or "") or "US").strip() not in ("", "US"):
            continue
        is_org = r.get(c["type"]) == "2"
        sole = (r.get(c["sole"] or "") or "").upper() == "Y"
        if not is_org and not sole:
            continue                                   # employees registering for an NPI are not practices
        tax = (r.get(c["tax"]) or "").strip()
        cat = category(tax)
        if cat == "other":
            continue
        if is_org:
            nm = (r.get(c["org"]) or "").strip()
        else:
            nm = f"{(r.get(c['first']) or '').strip()} {(r.get(c['last']) or '').strip()}".strip()
        if not nm:
            continue
        aof = f"{(r.get(c['aofirst']) or '').strip()} {(r.get(c['aof']) or '').strip()}".strip() if is_org else ""
        out.append({"registered": e.isoformat(), "category": cat, "specialty": names.get(tax) or TAX_NAMES.get(tax, tax),
                    "name": nm.title() if is_org else nm.title(), "entity": "practice/organization" if is_org else "sole proprietor",
                    "credential": (r.get(c["cred"]) or "").strip(), "phone": _phone(r.get(c["phone"])),
                    "address": (r.get(c["addr"]) or "").title(), "city": (r.get(c["city"]) or "").title(),
                    "state": (r.get(c["state"]) or "").upper(), "zip": (r.get(c["zip"]) or "")[:5],
                    "npi": r.get(c["npi"]) or "", "taxonomy": tax, "sole_proprietor": "yes" if sole else "",
                    "authorized_official": aof.title()})
    out.sort(key=lambda x: (x["state"], x["category"], x["entity"] != "practice/organization", x["name"]))
    return out


def _phone(p) -> str:
    d = re.sub(r"\D", "", str(p or ""))
    return f"({d[:3]}) {d[3:6]}-{d[6:10]}" if len(d) == 10 else (p or "")


def parse_nucc(csv_text: str) -> dict:
    """The NUCC taxonomy CSV -> {code: 'Classification, Specialization'}."""
    out = {}
    for r in csv.DictReader(io.StringIO(csv_text)):
        code = (r.get("Code") or "").strip()
        if not code:
            continue
        cls, spec = (r.get("Classification") or "").strip(), (r.get("Specialization") or "").strip()
        out[code] = f"{cls}, {spec}" if spec else cls
    return out
