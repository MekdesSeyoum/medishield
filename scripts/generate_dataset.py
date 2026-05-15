"""Generate the MediShield synthetic document dataset.

Creates 20 PNG images in /dataset with realistic-looking insurance
document layouts and writes ground_truth.json alongside them.

Usage (from the project root):
    python scripts/generate_dataset.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Output location
# ---------------------------------------------------------------------------

DATASET_DIR = Path(__file__).parent.parent / "dataset"
DATASET_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

WHITE       = (255, 255, 255)
NEAR_BLACK  = (30,  30,  40)
LIGHT_GRAY  = (230, 232, 235)
MID_GRAY    = (160, 165, 175)

BRAND_BLUE  = (30,  90,  180)
BRAND_GREEN = (25, 140,  90)
BRAND_RED   = (190,  40,  40)
BRAND_AMBER = (200, 130,  20)
BRAND_PURPLE= (100,  50, 160)
BRAND_TEAL  = (20,  140, 150)

# ---------------------------------------------------------------------------
# Font helpers (uses default PIL bitmap font as fallback)
# ---------------------------------------------------------------------------

def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


FONT_TITLE   = _font(22)
FONT_HEADING = _font(16)
FONT_BODY    = _font(13)
FONT_SMALL   = _font(11)

# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

W, H = 794, 1123  # A4 at 96 dpi


def _new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    return img, draw


def _header(draw: ImageDraw.ImageDraw, title: str, subtitle: str, colour: tuple) -> None:
    draw.rectangle([(0, 0), (W, 100)], fill=colour)
    draw.text((30, 18), "MediShield Health Insurance", font=FONT_HEADING, fill=WHITE)
    draw.text((30, 42), title, font=FONT_TITLE, fill=WHITE)
    draw.text((30, 72), subtitle, font=FONT_SMALL, fill=(220, 230, 255))


def _divider(draw: ImageDraw.ImageDraw, y: int, colour: tuple = LIGHT_GRAY) -> None:
    draw.line([(30, y), (W - 30, y)], fill=colour, width=1)


def _field(draw: ImageDraw.ImageDraw, y: int, label: str, value: str) -> int:
    draw.text((30, y), label, font=FONT_SMALL, fill=MID_GRAY)
    draw.text((220, y), value, font=FONT_BODY, fill=NEAR_BLACK)
    return y + 26


def _section(draw: ImageDraw.ImageDraw, y: int, title: str) -> int:
    draw.text((30, y), title.upper(), font=FONT_SMALL, fill=MID_GRAY)
    _divider(draw, y + 18)
    return y + 30


def _stamp(draw: ImageDraw.ImageDraw, text: str, colour: tuple) -> None:
    draw.rectangle([(W - 220, H - 120), (W - 30, H - 50)], outline=colour, width=3)
    draw.text((W - 200, H - 100), text, font=FONT_HEADING, fill=colour)


def _watermark(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.text((150, 500), text, font=_font(48), fill=(230, 210, 210))


# ===========================================================================
# Document generators
# ===========================================================================

class DocSpec(NamedTuple):
    file_name:         str
    doc_type:          str
    expected_decision: str
    description:       str


def _claim_form(file_name: str, patient: str, dob: str, member_id: str,
                policy: str, icd10: str, cpt: str, amount: str,
                provider: str, service_date: str, colour=BRAND_BLUE,
                stamp: str | None = None, watermark: str | None = None) -> None:
    img, draw = _new_canvas()
    _header(draw, "CLAIM FORM", f"Submitted: {service_date}", colour)

    y = 120
    y = _section(draw, y, "Member Information")
    y = _field(draw, y, "Patient Name",   patient)
    y = _field(draw, y, "Date of Birth",  dob)
    y = _field(draw, y, "Member ID",      member_id)
    y = _field(draw, y, "Policy Number",  policy)

    y += 10
    y = _section(draw, y, "Diagnosis")
    y = _field(draw, y, "ICD-10 Code",    icd10)

    y += 10
    y = _section(draw, y, "Procedure")
    y = _field(draw, y, "CPT Code",       cpt)
    y = _field(draw, y, "Service Date",   service_date)
    y = _field(draw, y, "Provider NPI",   provider)
    y = _field(draw, y, "Billed Amount",  amount)

    y += 20
    _divider(draw, y, BRAND_BLUE)
    draw.text((30, y + 10), "Provider certification: Information above is accurate and complete.",
              font=FONT_SMALL, fill=MID_GRAY)

    if stamp:
        _stamp(draw, stamp, BRAND_RED)
    if watermark:
        _watermark(draw, watermark)

    img.save(DATASET_DIR / file_name)


def _id_document(file_name: str, name: str, dob: str, member_id: str,
                 policy: str, plan: str, expiry: str, colour=BRAND_GREEN,
                 watermark: str | None = None, tampered: bool = False) -> None:
    img, draw = _new_canvas()
    _header(draw, "MEMBERSHIP CARD", "Official Identity Document", colour)

    # Card body
    card_y = 140
    draw.rounded_rectangle([(40, card_y), (W - 40, card_y + 340)],
                            radius=18, outline=colour, width=2)

    y = card_y + 20
    draw.text((60, y), "MEMBER", font=FONT_SMALL, fill=MID_GRAY)
    draw.text((60, y + 18), name, font=_font(24), fill=NEAR_BLACK)

    y += 70
    y = _field(draw, y, "Member ID",      member_id)
    y = _field(draw, y, "Date of Birth",  dob)
    y = _field(draw, y, "Policy Number",  policy)
    y = _field(draw, y, "Plan Type",      plan)
    y = _field(draw, y, "Valid Through",  expiry)

    # Photo placeholder
    draw.rectangle([(W - 200, card_y + 20), (W - 70, card_y + 140)],
                   fill=LIGHT_GRAY, outline=MID_GRAY)
    draw.text((W - 175, card_y + 65), "PHOTO", font=FONT_SMALL, fill=MID_GRAY)

    if tampered:
        draw.rectangle([(W - 200, card_y + 20), (W - 70, card_y + 140)],
                       fill=(200, 180, 180), outline=BRAND_RED, width=3)
        draw.text((W - 195, card_y + 55), "ALTERED", font=FONT_SMALL, fill=BRAND_RED)
        _watermark(draw, "TAMPERED")

    if watermark and not tampered:
        _watermark(draw, watermark)

    img.save(DATASET_DIR / file_name)


def _medical_report(file_name: str, patient: str, dob: str, admission: str,
                    discharge: str, diagnosis: str, icd10: str,
                    attending: str, colour=BRAND_TEAL) -> None:
    img, draw = _new_canvas()
    _header(draw, "DISCHARGE SUMMARY", f"Admission: {admission}  Discharge: {discharge}", colour)

    y = 120
    y = _section(draw, y, "Patient Information")
    y = _field(draw, y, "Patient Name",    patient)
    y = _field(draw, y, "Date of Birth",   dob)
    y = _field(draw, y, "Attending MD",    attending)

    y += 10
    y = _section(draw, y, "Clinical Information")
    y = _field(draw, y, "Primary Diagnosis", diagnosis)
    y = _field(draw, y, "ICD-10 Code",       icd10)

    y += 10
    y = _section(draw, y, "Discharge Notes")
    notes = [
        "Patient presented with acute onset of symptoms.",
        "Treated with appropriate pharmacological intervention.",
        "Discharged in stable condition with follow-up in 2 weeks.",
        "Instructions provided regarding medication and activity restrictions.",
    ]
    for note in notes:
        draw.text((30, y), f"• {note}", font=FONT_BODY, fill=NEAR_BLACK)
        y += 24

    img.save(DATASET_DIR / file_name)


def _prescription(file_name: str, patient: str, dob: str, rx_date: str,
                  drug: str, strength: str, sig: str, quantity: str,
                  prescriber: str, npi: str, colour=BRAND_PURPLE) -> None:
    img, draw = _new_canvas()
    _header(draw, "PRESCRIPTION", f"Date: {rx_date}", colour)

    y = 120
    y = _section(draw, y, "Patient")
    y = _field(draw, y, "Patient Name",  patient)
    y = _field(draw, y, "Date of Birth", dob)

    y += 10
    y = _section(draw, y, "Medication")
    y = _field(draw, y, "Drug",          drug)
    y = _field(draw, y, "Strength",      strength)
    y = _field(draw, y, "Sig",           sig)
    y = _field(draw, y, "Quantity",      quantity)
    y = _field(draw, y, "Refills",       "0")

    y += 10
    y = _section(draw, y, "Prescriber")
    y = _field(draw, y, "Prescriber",    prescriber)
    y = _field(draw, y, "NPI",           npi)
    y = _field(draw, y, "License",       "MD-" + npi[:6])

    # Sig box
    y += 20
    draw.rectangle([(30, y), (W - 30, y + 60)], outline=colour, width=1)
    draw.text((40, y + 10), "Prescriber Signature: ___________________________", font=FONT_BODY, fill=NEAR_BLACK)
    draw.text((40, y + 36), "DEA Number: _______________", font=FONT_SMALL, fill=MID_GRAY)

    img.save(DATASET_DIR / file_name)


def _unknown_document(file_name: str, content: str, colour=BRAND_AMBER) -> None:
    img, draw = _new_canvas()
    _header(draw, "UNIDENTIFIED DOCUMENT", "Source: external submission", colour)
    y = 140
    for line in content.splitlines():
        draw.text((30, y), line, font=FONT_BODY, fill=NEAR_BLACK)
        y += 22
    img.save(DATASET_DIR / file_name)


# ===========================================================================
# Dataset definition
# ===========================================================================

def generate_all() -> list[DocSpec]:
    specs: list[DocSpec] = []

    # -----------------------------------------------------------------------
    # 5 × CLAIM FORM — valid, expected APPROVE
    # -----------------------------------------------------------------------
    _claim_form("claim_form_001.png",
                patient="Jane Doe", dob="1985-03-15", member_id="M001234",
                policy="POL-2024-001234", icd10="J18.9 (Pneumonia)",
                cpt="99213 (Office Visit)", amount="$450.00",
                provider="1234567890", service_date="2024-03-15")
    specs.append(DocSpec("claim_form_001.png", "CLAIM_FORM", "APPROVE",
                         "Office visit — pneumonia, covered CPT 99213"))

    _claim_form("claim_form_002.png",
                patient="John Smith", dob="1970-07-22", member_id="M005678",
                policy="POL-2024-005678", icd10="I10 (Hypertension)",
                cpt="71046 (Chest X-Ray)", amount="$280.00",
                provider="9876543210", service_date="2024-04-10")
    specs.append(DocSpec("claim_form_002.png", "CLAIM_FORM", "APPROVE",
                         "Chest X-ray for hypertension follow-up, covered CPT 71046"))

    _claim_form("claim_form_003.png",
                patient="Maria Garcia", dob="1992-11-05", member_id="M009012",
                policy="POL-2024-009012", icd10="Z00.00 (Routine Exam)",
                cpt="99395 (Preventive Care)", amount="$200.00",
                provider="1122334455", service_date="2024-05-02")
    specs.append(DocSpec("claim_form_003.png", "CLAIM_FORM", "APPROVE",
                         "Annual preventive care exam, covered at 100%"))

    _claim_form("claim_form_004.png",
                patient="Robert Lee", dob="1958-01-30", member_id="M003456",
                policy="POL-2024-003456", icd10="R00.0 (Tachycardia)",
                cpt="93000 (ECG)", amount="$175.00",
                provider="5566778899", service_date="2024-04-22")
    specs.append(DocSpec("claim_form_004.png", "CLAIM_FORM", "APPROVE",
                         "ECG for cardiac evaluation, covered diagnostic test"))

    _claim_form("claim_form_005.png",
                patient="Sarah Johnson", dob="1988-06-18", member_id="M007890",
                policy="POL-2024-007890", icd10="M54.5 (Low Back Pain)",
                cpt="99214 (Office Visit L4)", amount="$520.00",
                provider="3344556677", service_date="2024-05-08")
    specs.append(DocSpec("claim_form_005.png", "CLAIM_FORM", "APPROVE",
                         "Level-4 office visit for back pain, covered CPT 99214"))

    # -----------------------------------------------------------------------
    # 4 × ID DOCUMENT — valid, expected APPROVE
    # -----------------------------------------------------------------------
    _id_document("id_document_001.png",
                 name="Jane Doe", dob="1985-03-15", member_id="M001234",
                 policy="POL-2024-001234", plan="GOLD", expiry="2027-01-01")
    specs.append(DocSpec("id_document_001.png", "ID_DOCUMENT", "APPROVE",
                         "Valid membership card — Jane Doe, GOLD plan"))

    _id_document("id_document_002.png",
                 name="John Smith", dob="1970-07-22", member_id="M005678",
                 policy="POL-2024-005678", plan="SILVER", expiry="2026-06-30")
    specs.append(DocSpec("id_document_002.png", "ID_DOCUMENT", "APPROVE",
                         "Valid membership card — John Smith, SILVER plan"))

    _id_document("id_document_003.png",
                 name="Maria Garcia", dob="1992-11-05", member_id="M009012",
                 policy="POL-2024-009012", plan="PLATINUM", expiry="2027-12-31")
    specs.append(DocSpec("id_document_003.png", "ID_DOCUMENT", "APPROVE",
                         "Valid membership card — Maria Garcia, PLATINUM plan"))

    _id_document("id_document_004.png",
                 name="Robert Lee", dob="1958-01-30", member_id="M003456",
                 policy="POL-2024-003456", plan="GOLD", expiry="2026-12-31")
    specs.append(DocSpec("id_document_004.png", "ID_DOCUMENT", "APPROVE",
                         "Valid membership card — Robert Lee, GOLD plan"))

    # -----------------------------------------------------------------------
    # 3 × DISCHARGE SUMMARY — valid, expected APPROVE
    # -----------------------------------------------------------------------
    _medical_report("medical_report_001.png",
                    patient="Jane Doe", dob="1985-03-15",
                    admission="2024-03-12", discharge="2024-03-15",
                    diagnosis="Community-acquired pneumonia",
                    icd10="J18.9", attending="Dr. A. Patel")
    specs.append(DocSpec("medical_report_001.png", "MEDICAL_REPORT", "APPROVE",
                         "Pneumonia inpatient stay 3 days — covered"))

    _medical_report("medical_report_002.png",
                    patient="John Smith", dob="1970-07-22",
                    admission="2024-04-09", discharge="2024-04-10",
                    diagnosis="Hypertensive urgency",
                    icd10="I10", attending="Dr. M. Nguyen")
    specs.append(DocSpec("medical_report_002.png", "MEDICAL_REPORT", "APPROVE",
                         "Hypertension 1-day observation — covered"))

    _medical_report("medical_report_003.png",
                    patient="Sarah Johnson", dob="1988-06-18",
                    admission="2024-05-05", discharge="2024-05-07",
                    diagnosis="Closed fracture of distal radius",
                    icd10="S52.501A", attending="Dr. L. Kim")
    specs.append(DocSpec("medical_report_003.png", "MEDICAL_REPORT", "APPROVE",
                         "Wrist fracture 2-day stay — covered"))

    # -----------------------------------------------------------------------
    # 3 × PRESCRIPTION — valid, expected APPROVE
    # -----------------------------------------------------------------------
    _prescription("prescription_001.png",
                  patient="Jane Doe", dob="1985-03-15", rx_date="2024-03-15",
                  drug="Amoxicillin", strength="500 mg", sig="1 cap TID × 10d",
                  quantity="#30", prescriber="Dr. A. Patel", npi="1234567890")
    specs.append(DocSpec("prescription_001.png", "PRESCRIPTION", "APPROVE",
                         "Antibiotic for pneumonia — covered"))

    _prescription("prescription_002.png",
                  patient="John Smith", dob="1970-07-22", rx_date="2024-04-10",
                  drug="Lisinopril", strength="10 mg", sig="1 tab QD",
                  quantity="#30", prescriber="Dr. M. Nguyen", npi="9876543210")
    specs.append(DocSpec("prescription_002.png", "PRESCRIPTION", "APPROVE",
                         "ACE inhibitor for hypertension — covered"))

    _prescription("prescription_003.png",
                  patient="Robert Lee", dob="1958-01-30", rx_date="2024-04-22",
                  drug="Metformin", strength="1000 mg", sig="1 tab BID with meals",
                  quantity="#60", prescriber="Dr. L. Kim", npi="5566778899")
    specs.append(DocSpec("prescription_003.png", "PRESCRIPTION", "APPROVE",
                         "Diabetes medication — covered"))

    # -----------------------------------------------------------------------
    # 3 × FRAUDULENT / INVALID — expected REJECT or ESCALATE
    # -----------------------------------------------------------------------

    # Duplicate claim (same as claim_form_001 — triggers fraud detection)
    _claim_form("fraud_duplicate_claim.png",
                patient="Jane Doe", dob="1985-03-15", member_id="M001234",
                policy="POL-2024-001234", icd10="J18.9 (Pneumonia)",
                cpt="99213 (Office Visit)", amount="$450.00",
                provider="1234567890", service_date="2024-03-15",
                colour=BRAND_RED,
                stamp="DUPLICATE",
                watermark="DUPLICATE CLAIM")
    specs.append(DocSpec("fraud_duplicate_claim.png", "CLAIM_FORM", "ESCALATE",
                         "Exact duplicate of claim_form_001 — fraud score HIGH"))

    # Tampered ID card
    _id_document("fraud_tampered_id.png",
                 name="Jane Doe", dob="1985-03-15", member_id="M001234",
                 policy="POL-2024-001234", plan="PLATINUM",
                 expiry="2030-01-01", colour=BRAND_RED, tampered=True)
    specs.append(DocSpec("fraud_tampered_id.png", "ID_DOCUMENT", "REJECT",
                         "Tampered membership card — photo and expiry altered"))

    # Excluded procedure (cosmetic)
    _claim_form("fraud_excluded_procedure.png",
                patient="Alice Chen", dob="1995-08-20", member_id="M002468",
                policy="POL-2024-002468", icd10="H02.01 (Blepharoptosis)",
                cpt="15820 (Blepharoplasty — COSMETIC)", amount="$3,200.00",
                provider="7788990011", service_date="2024-05-10",
                colour=BRAND_AMBER,
                stamp="EXCLUDED")
    specs.append(DocSpec("fraud_excluded_procedure.png", "CLAIM_FORM", "REJECT",
                         "Cosmetic blepharoplasty — excluded under Section 9.1"))

    # -----------------------------------------------------------------------
    # 2 × REJECT — KYC failure
    # -----------------------------------------------------------------------

    # Expired membership card
    _id_document("reject_expired_card.png",
                 name="Tom Walker", dob="1975-04-12", member_id="M006543",
                 policy="POL-2021-006543", plan="SILVER", expiry="2022-12-31",
                 colour=BRAND_RED)
    specs.append(DocSpec("reject_expired_card.png", "ID_DOCUMENT", "REJECT",
                         "Expired membership card (2022-12-31) — DOCUMENT_EXPIRED → KYC fails"))

    # Member not in registry
    _id_document("reject_unknown_member.png",
                 name="Ghost User", dob="1980-01-01", member_id="M999999",
                 policy="POL-9999-000000", plan="GOLD", expiry="2027-01-01",
                 colour=BRAND_RED)
    specs.append(DocSpec("reject_unknown_member.png", "ID_DOCUMENT", "REJECT",
                         "Member ID M999999 not in registry — MEMBER_NOT_FOUND → KYC fails"))

    # -----------------------------------------------------------------------
    # 2 × ESCALATE — fraud detection
    # -----------------------------------------------------------------------

    # Amount outlier — provider 3333333333 history mean $200, σ≈$14.7; threshold ≈$229
    _claim_form("escalate_amount_outlier.png",
                patient="David Kim", dob="1982-09-10", member_id="M008765",
                policy="POL-2024-008765", icd10="M51.16 (Disc degeneration)",
                cpt="27447 (Total Knee Replacement)", amount="$1,500.00",
                provider="3333333333", service_date="2026-05-10",
                colour=BRAND_AMBER,
                stamp="REVIEW")
    specs.append(DocSpec("escalate_amount_outlier.png", "CLAIM_FORM", "ESCALATE",
                         "Amount $1,500 far exceeds provider 3333333333 2σ threshold (~$229) → fraud ESCALATE"))

    # High-frequency provider — 4444444444 has 6 claims in the past 7 days
    _claim_form("escalate_high_freq_provider.png",
                patient="Nina Patel", dob="1993-03-27", member_id="M001122",
                policy="POL-2024-001122", icd10="J06.9 (Upper respiratory infection)",
                cpt="99213 (Office Visit)", amount="$210.00",
                provider="4444444444", service_date="2026-05-15",
                colour=BRAND_AMBER,
                stamp="REVIEW")
    specs.append(DocSpec("escalate_high_freq_provider.png", "CLAIM_FORM", "ESCALATE",
                         "Provider 4444444444 submitted 6 claims in past 7 days → high-frequency fraud ESCALATE"))

    # -----------------------------------------------------------------------
    # 2 × AMBIGUOUS / UNKNOWN
    # -----------------------------------------------------------------------
    _unknown_document("unknown_document_001.png",
                      content=(
                          "DOKUMENT-NR: 2024-DE-00912\n"
                          "Versicherungsnehmer: Klaus Müller\n"
                          "Geburtsdatum: 15.08.1966\n"
                          "Diagnose: Bandscheibenvorfall L4/L5\n"
                          "Behandlungsdauer: 10 Tage\n"
                          "Gesamtbetrag: 4.850,00 EUR\n"
                          "\n"
                          "Bitte leiten Sie dieses Dokument an die\n"
                          "zuständige Abteilung weiter."
                      ))
    specs.append(DocSpec("unknown_document_001.png", "UNKNOWN", "ESCALATE",
                         "German-language insurance document — cannot auto-classify"))

    _unknown_document("unknown_document_002.png",
                      content=(
                          "DOCUMENT TYPE: UNCLEAR\n"
                          "Ref #: 2024-MISC-88712\n"
                          "--- Page appears to be partial scan ---\n"
                          "[Section 1 missing]\n"
                          "...\n"
                          "Amount:  $??? .??\n"
                          "Codes:   [ILLEGIBLE]\n"
                          "Member:  [ILLEGIBLE]\n"
                          "\n"
                          "Note: This document requires manual review\n"
                          "due to incomplete scan quality."
                      ))
    specs.append(DocSpec("unknown_document_002.png", "UNKNOWN", "ESCALATE",
                         "Partial/corrupted scan — insufficient data to classify"))

    return specs


# ===========================================================================
# Ground-truth JSON
# ===========================================================================

def write_ground_truth(specs: list[DocSpec]) -> None:
    records = [
        {
            "file_name": s.file_name,
            "doc_type": s.doc_type,
            "expected_decision": s.expected_decision,
            "description": s.description,
        }
        for s in specs
    ]
    path = DATASET_DIR / "ground_truth.json"
    path.write_text(json.dumps(records, indent=2))
    print(f"  ground_truth.json  ({len(records)} entries)")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    print(f"Generating dataset in:  {DATASET_DIR}\n")

    specs = generate_all()

    totals: dict[str, int] = {}
    for s in specs:
        totals[s.doc_type] = totals.get(s.doc_type, 0) + 1
        print(f"  {s.file_name:<38}  {s.doc_type:<16}  {s.expected_decision}")

    write_ground_truth(specs)

    print(f"\nDone — {len(specs)} images")
    for dtype, count in sorted(totals.items()):
        print(f"  {dtype:<20} {count}")
