"""
Seed mock intelligence-layer reference data into Supabase.

Run from repo root:
    python scripts/seed_mock_data.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.services.supabase_client import supabase  # noqa: E402


def _normalize_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def _table_has_rows(table: str) -> bool:
    response = supabase.table(table).select("id").limit(1).execute()
    return bool(response.data)


def _upsert(table: str, rows: list[dict[str, Any]], conflict_col: str) -> None:
    if not rows:
        return
    supabase.table(table).upsert(rows, on_conflict=conflict_col).execute()


def _seed_company_registry() -> None:
    base_rows: list[dict[str, Any]] = [
        {
            "name": "Al Baraka Manpower Services",
            "registered_city": "Hyderabad",
            "registered_state": "Telangana",
            "emigrate_registered": True,
            "emigrate_raps_id": "R1234567",
            "placement_countries": ["UAE", "Qatar", "Saudi Arabia"],
            "allowed_job_categories": ["Security Guard", "Driver", "Cleaner"],
            "primary_phone": "+91-9849000001",
            "website": "https://albarakamanpower.co.in",
            "is_blacklisted": False,
        },
        {
            "name": "Gulf Vision Recruitment",
            "registered_city": "Mumbai",
            "registered_state": "Maharashtra",
            "emigrate_registered": True,
            "emigrate_raps_id": "R2345678",
            "placement_countries": ["UAE", "Bahrain"],
            "allowed_job_categories": ["Cook", "Housekeeping", "Waiter"],
            "primary_phone": "+91-9892000002",
            "website": "https://gulfvisionjobs.in",
            "is_blacklisted": False,
        },
        {
            "name": "Krishna International Placement",
            "registered_city": "Lucknow",
            "registered_state": "Uttar Pradesh",
            "emigrate_registered": True,
            "emigrate_raps_id": "R3456789",
            "placement_countries": ["Saudi Arabia", "Oman"],
            "allowed_job_categories": ["Construction Worker", "Mason", "Helper"],
            "primary_phone": "+91-9956000003",
            "website": "https://krishnaplacement.in",
            "is_blacklisted": False,
        },
        {
            "name": "Apex HR Solutions Pvt Ltd",
            "registered_city": "Delhi",
            "registered_state": "Delhi",
            "emigrate_registered": False,
            "emigrate_raps_id": None,
            "placement_countries": ["India"],
            "allowed_job_categories": ["Telecaller", "Warehouse Associate", "Sales Executive"],
            "primary_phone": "+91-9811000004",
            "website": "https://apexhr.in",
            "is_blacklisted": False,
        },
        {
            "name": "Global Career Solutions",
            "registered_city": "Kolkata",
            "registered_state": "West Bengal",
            "emigrate_registered": False,
            "emigrate_raps_id": None,
            "placement_countries": [],
            "allowed_job_categories": ["BPO", "Data Entry"],
            "primary_phone": "+91-9831000005",
            "website": "https://globalcareersolution.in",
            "is_blacklisted": True,
        },
        {
            "name": "URGENT JOBS INTERNATIONAL",
            "registered_city": None,
            "registered_state": None,
            "emigrate_registered": False,
            "emigrate_raps_id": None,
            "placement_countries": [],
            "allowed_job_categories": [],
            "primary_phone": "+91-9700000006",
            "website": None,
            "is_blacklisted": True,
        },
        {
            "name": "Al Baraka Recruitment LLC",
            "registered_city": "Hyderabad",
            "registered_state": "Telangana",
            "emigrate_registered": False,
            "emigrate_raps_id": None,
            "placement_countries": ["India"],
            "allowed_job_categories": ["Domestic Placement"],
            "primary_phone": "+91-9949000007",
            "website": "https://albarakarecruitment.in",
            "is_blacklisted": False,
        },
        {
            "name": "Safa Overseas Placement",
            "registered_city": "Kozhikode",
            "registered_state": "Kerala",
            "emigrate_registered": True,
            "emigrate_raps_id": "R4567001",
            "placement_countries": ["UAE", "Oman", "Qatar"],
            "allowed_job_categories": ["Plumber", "Electrician", "AC Technician"],
            "primary_phone": "+91-9847000008",
            "website": "https://safaoverseas.com",
            "is_blacklisted": False,
        },
        {
            "name": "BluePalm Recruitment Services",
            "registered_city": "Kochi",
            "registered_state": "Kerala",
            "emigrate_registered": True,
            "emigrate_raps_id": "R4567002",
            "placement_countries": ["UAE", "Kuwait"],
            "allowed_job_categories": ["Nurse", "Caregiver", "Lab Technician"],
            "primary_phone": "+91-9895000009",
            "website": "https://bluepalmjobs.in",
            "is_blacklisted": False,
        },
        {
            "name": "Desert Link Staffing",
            "registered_city": "Jaipur",
            "registered_state": "Rajasthan",
            "emigrate_registered": True,
            "emigrate_raps_id": "R4567003",
            "placement_countries": ["Saudi Arabia", "Bahrain"],
            "allowed_job_categories": ["Driver", "Heavy Driver", "Forklift Operator"],
            "primary_phone": "+91-9829000010",
            "website": "https://desertlinkstaffing.com",
            "is_blacklisted": False,
        },
    ]

    template_rows = [
        ("Shakti", "Pune", "Maharashtra", ["UAE", "Qatar"], ["Cleaner", "Housekeeping", "Waiter"]),
        ("Noble", "Patna", "Bihar", ["Saudi Arabia", "Oman"], ["Mason", "Carpenter", "Helper"]),
        ("Eastern", "Bhubaneswar", "Odisha", ["UAE"], ["Security Guard", "Driver"]),
        ("Prime", "Chennai", "Tamil Nadu", ["Qatar", "Bahrain"], ["Cook", "Housekeeping"]),
        ("Vikas", "Kanpur", "Uttar Pradesh", ["Saudi Arabia"], ["Construction Worker", "Welder"]),
        ("Elite", "Surat", "Gujarat", ["UAE", "Kuwait"], ["Salesman", "Storekeeper"]),
        ("Reliable", "Indore", "Madhya Pradesh", ["Oman"], ["Helper", "Cleaner"]),
        ("Orbit", "Noida", "Uttar Pradesh", ["UAE"], ["Electrician", "Plumber"]),
        ("Silver", "Nagpur", "Maharashtra", ["Qatar"], ["Security Guard", "Driver"]),
        ("Unity", "Ahmedabad", "Gujarat", ["Saudi Arabia"], ["Mason", "Steel Fixer"]),
        ("Fortune", "Ludhiana", "Punjab", ["UAE", "Bahrain"], ["Cook", "Waiter"]),
        ("Metro", "Delhi", "Delhi", ["India"], ["Telecaller", "Field Executive"]),
        ("Rapid", "Hyderabad", "Telangana", ["UAE"], ["Electrician", "AC Technician"]),
        ("Sunrise", "Guwahati", "Assam", ["Qatar"], ["Cleaner", "Housekeeping"]),
        ("Harbor", "Mangalore", "Karnataka", ["Kuwait"], ["Driver", "Helper"]),
        ("Skyline", "Visakhapatnam", "Andhra Pradesh", ["Saudi Arabia"], ["Welder", "Fabricator"]),
        ("Zenith", "Navi Mumbai", "Maharashtra", ["UAE", "Oman"], ["Security Guard", "Cleaner"]),
        ("Shree", "Varanasi", "Uttar Pradesh", ["Saudi Arabia"], ["Mason", "Carpenter"]),
        ("Compass", "Bhopal", "Madhya Pradesh", ["Qatar"], ["Storekeeper", "Warehouse Assistant"]),
        ("Aarav", "Vadodara", "Gujarat", ["UAE"], ["Driver", "Forklift Operator"]),
        ("Digi", "Bengaluru", "Karnataka", ["India"], ["Data Entry", "Back Office"]),
        ("Sundar", "Madurai", "Tamil Nadu", ["Oman"], ["Cook", "Housekeeping"]),
        ("Greenline", "Ranchi", "Jharkhand", ["Saudi Arabia"], ["Helper", "Cleaner"]),
        ("Vision", "Thane", "Maharashtra", ["UAE"], ["Security Guard", "Plumber"]),
        ("PrimeWay", "Jalandhar", "Punjab", ["Bahrain"], ["Driver", "Cleaner"]),
        ("Mars", "Raipur", "Chhattisgarh", ["Qatar"], ["Mason", "Welder"]),
        ("PeopleFirst", "Coimbatore", "Tamil Nadu", ["UAE"], ["Nurse", "Caregiver"]),
        ("Nimbus", "Kota", "Rajasthan", ["Saudi Arabia"], ["Steel Fixer", "Helper"]),
        ("WestBridge", "Agra", "Uttar Pradesh", ["Oman"], ["Cook", "Waiter"]),
        ("BrightPath", "Srinagar", "Jammu and Kashmir", ["UAE"], ["Cleaner", "Housekeeping"]),
        ("SafeHands", "Meerut", "Uttar Pradesh", ["Kuwait"], ["Driver", "Security Guard"]),
        ("Arise", "Amritsar", "Punjab", ["Saudi Arabia"], ["Mason", "Carpenter"]),
        ("Crown", "Dehradun", "Uttarakhand", ["Qatar"], ["Helper", "Plumber"]),
        ("Delta", "Jabalpur", "Madhya Pradesh", ["UAE"], ["Electrician", "AC Technician"]),
        ("Royal", "Mysuru", "Karnataka", ["Bahrain"], ["Housekeeping", "Cleaner"]),
        ("OrbitPro", "Nashik", "Maharashtra", ["Oman"], ["Welder", "Fabricator"]),
        ("Peak", "Trichy", "Tamil Nadu", ["UAE"], ["Storekeeper", "Driver"]),
        ("TrueLine", "Aligarh", "Uttar Pradesh", ["Saudi Arabia"], ["Helper", "Cleaner"]),
        ("Nova", "Rajkot", "Gujarat", ["Qatar"], ["Security Guard", "Driver"]),
        ("Samarth", "Prayagraj", "Uttar Pradesh", ["UAE"], ["Cook", "Waiter"]),
    ]

    generated_rows: list[dict[str, Any]] = []
    for idx, (prefix, city, state, countries, categories) in enumerate(template_rows, start=11):
        generated_rows.append(
            {
                "name": f"{prefix} Global Placement Services",
                "registered_city": city,
                "registered_state": state,
                "emigrate_registered": "India" not in countries,
                "emigrate_raps_id": f"R45{idx:05d}" if "India" not in countries else None,
                "placement_countries": countries,
                "allowed_job_categories": categories,
                "primary_phone": f"+91-98{idx:08d}"[:14],
                "website": f"https://{prefix.lower()}placement.in",
                "is_blacklisted": False,
            }
        )

    rows = base_rows + generated_rows
    for row in rows:
        row["name_normalized"] = _normalize_name(row["name"])

    _upsert("company_registry", rows, "name_normalized")
    print(f"Seeded company_registry rows: {len(rows)}")


def _seed_phone_prefixes() -> None:
    rows = [
        {"prefix": "+971-4", "country": "UAE", "region": "Dubai", "is_mobile": False},
        {"prefix": "+971-50", "country": "UAE", "region": "UAE Mobile", "is_mobile": True},
        {"prefix": "+971-52", "country": "UAE", "region": "UAE Mobile", "is_mobile": True},
        {"prefix": "+971-54", "country": "UAE", "region": "UAE Mobile", "is_mobile": True},
        {"prefix": "+971-55", "country": "UAE", "region": "UAE Mobile", "is_mobile": True},
        {"prefix": "+974", "country": "Qatar", "region": "Doha", "is_mobile": False},
        {"prefix": "+966", "country": "Saudi Arabia", "region": "KSA", "is_mobile": False},
        {"prefix": "+968", "country": "Oman", "region": "Muscat", "is_mobile": False},
        {"prefix": "+973", "country": "Bahrain", "region": "Bahrain", "is_mobile": False},
        {"prefix": "+965", "country": "Kuwait", "region": "Kuwait City", "is_mobile": False},
        {"prefix": "+91-60", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-61", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-62", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-63", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-70", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-71", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-72", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-73", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-74", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-75", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-76", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-77", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-78", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-79", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-80", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-81", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-82", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-83", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-84", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-85", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-86", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-87", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-88", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-89", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-90", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-91", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-92", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-93", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-94", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-95", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-96", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-97", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-98", "country": "India", "region": "India Mobile", "is_mobile": True},
        {"prefix": "+91-99", "country": "India", "region": "India Mobile", "is_mobile": True},
    ]
    _upsert("phone_prefix_location", rows, "prefix")
    print(f"Seeded phone_prefix_location rows: {len(rows)}")


def _seed_embedding_corpora() -> None:
    legitimate_samples = [
        "Al Baraka Manpower Services hiring Security Guards for UAE. Salary AED 1400/month. RAPS R1234567. No recruitment fee.",
        "Gulf Vision Recruitment seeks Housekeeping staff for Bahrain hotels. Company interview in Mumbai office. No placement charges.",
        "Krishna International Placement requires Mason helpers for Riyadh project. Valid passport required. eMigrate process via registered office.",
        "BluePalm Recruitment Services hiring nurses for Kuwait. IELTS preferred. Official contract issued after verification.",
        "Safa Overseas Placement inviting Electrician applications for Doha. Salary AED 1800 equivalent. Contact registered office in Kozhikode.",
        "Apex HR Solutions hiring warehouse associates in Delhi NCR with PF and ESIC benefits. Walk-in interview at office address.",
        "Metro Global Placement Services opening for telecallers in Delhi. Fixed salary plus incentives. HR email and office website provided.",
        "Prime Global Placement Services requires cooks for UAE catering company. Employer pays visa and ticket. No fee to candidate.",
        "Reliable Global Placement Services recruiting drivers for Oman logistics. License verification mandatory and official agreement issued.",
        "PeopleFirst Global Placement Services hiring caregivers for Dubai clinic. Medical insurance and accommodation provided by employer.",
    ]

    scam_samples = [
        "URGENT Dubai job security guard salary 80000 INR monthly. Registration fee 8000 now. Send payment on UPI immediately.",
        "Limited seats Gulf vacancy apply today only. Processing charges 6500 and visa fee 12000 required before interview.",
        "Direct joining in Qatar no documents needed. Pay token amount now to confirm seat. Contact only on WhatsApp.",
        "Fast job in Saudi, salary 95000, no interview. Deposit refundable fee to upi id right now.",
        "Immediate placement in Dubai airport, last 2 seats, send Aadhaar and advance amount today.",
        "Housekeeping job abroad urgent. Medical and file charges must be paid tonight for visa approval.",
        "Great offer Bahrain driver post. Pay security deposit 10000 then ticket will be issued.",
        "Work permit ready for Kuwait, transfer money quickly otherwise profile rejected.",
        "Overseas helper job guaranteed. Call now and pay registration to private account.",
        "Abhi apply karo, Gulf job pakka. Fee bhejo aur kal flight ticket milega.",
    ]

    if not _table_has_rows("job_postings_legitimate"):
        rows = [{"text": text, "source": "mock-seed"} for text in legitimate_samples]
        supabase.table("job_postings_legitimate").insert(rows).execute()
        print(f"Seeded job_postings_legitimate rows: {len(rows)}")
    else:
        print("Skipped job_postings_legitimate (already has data)")

    if not _table_has_rows("job_postings_scam"):
        rows = [{"text": text, "source": "mock-seed"} for text in scam_samples]
        supabase.table("job_postings_scam").insert(rows).execute()
        print(f"Seeded job_postings_scam rows: {len(rows)}")
    else:
        print("Skipped job_postings_scam (already has data)")


def main() -> None:
    _seed_company_registry()
    _seed_phone_prefixes()
    _seed_embedding_corpora()
    print("Mock intelligence data seeding complete.")


if __name__ == "__main__":
    main()

