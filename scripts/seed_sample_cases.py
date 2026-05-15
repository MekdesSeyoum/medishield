"""Seed the MediShield API with sample documents for demo purposes.

Usage (from the project root):
    python scripts/seed_sample_cases.py

The script uploads three synthetic documents — a claim form, a membership
card, and a medical report — and prints the resulting case IDs.  The
pipeline will process them asynchronously; check the dashboard at
http://localhost:3000 to watch their status change.
"""

import io
import struct
import zlib
import time
import sys

try:
    import requests
except ImportError:
    print("Install requests first:  pip install requests")
    sys.exit(1)

API_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Minimal valid PNG builder (1×1 pixel, coloured differently per document)
# ---------------------------------------------------------------------------

def _make_png(r: int, g: int, b: int) -> bytes:
    """Return a valid 1×1 RGB PNG with the given colour."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_row = b"\x00" + bytes([r, g, b])
    idat = chunk(b"IDAT", zlib.compress(raw_row))
    iend = chunk(b"IEND", b"")
    return header + ihdr + idat + iend


SAMPLES = [
    {
        "file_name": "claim_form_jane_doe.png",
        "mime_type": "image/png",
        "colour": (70, 130, 180),   # steel-blue
        "description": "Claim form — Jane Doe, CPT 99213",
    },
    {
        "file_name": "membership_card_john_smith.png",
        "mime_type": "image/png",
        "colour": (60, 179, 113),   # medium-sea-green
        "description": "Membership card — John Smith, POL-2024-005678",
    },
    {
        "file_name": "medical_report_alice_chen.png",
        "mime_type": "image/png",
        "colour": (220, 120, 60),   # burnt-orange
        "description": "Medical report — Alice Chen, ICD-10 J18.9",
    },
]


def upload(sample: dict) -> str:
    png_bytes = _make_png(*sample["colour"])
    resp = requests.post(
        f"{API_URL}/cases/upload",
        files={"file": (sample["file_name"], io.BytesIO(png_bytes), sample["mime_type"])},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["case_id"]


def main() -> None:
    print(f"Seeding {len(SAMPLES)} sample cases → {API_URL}\n")
    for sample in SAMPLES:
        try:
            case_id = upload(sample)
            print(f"  ✓  {sample['description']}")
            print(f"     case_id: {case_id}\n")
        except requests.RequestException as exc:
            print(f"  ✗  {sample['description']}")
            print(f"     error: {exc}\n")

    print("Done. Open http://localhost:3000 to watch the pipeline process them.")


if __name__ == "__main__":
    main()
